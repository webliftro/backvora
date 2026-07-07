"""
Backlinks API router - competitor backlink analysis.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Domain, Backlink, DomainStatus
from ..services import adult_classifier
from ..services.ahrefs import AhrefsService
from ..utils.domains import extract_root_domain

router = APIRouter()


@router.get("/{domain_id}")
async def list_backlinks(
    domain_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List backlinks for a domain."""
    query = db.query(Backlink).filter(Backlink.source_domain_id == domain_id)
    
    total = query.count()
    backlinks = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return {
        "items": backlinks,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("/fetch/{competitor_domain}")
async def fetch_competitor_backlinks(
    competitor_domain: str,
    limit: int = Query(100, ge=1, le=1000),
    save: bool = Query(True, description="Save to database (False = preview only)"),
    db: Session = Depends(get_db),
):
    """
    Fetch backlinks pointing to a competitor domain from Ahrefs.
    Returns domains sorted by traffic (descending), one per domain.
    """
    try:
        ahrefs = AhrefsService()
        backlinks_data = await ahrefs.get_backlinks(competitor_domain, limit=limit)
        
        # Dedupe: keep only first link per ROOT domain (already sorted by traffic_domain from API)
        # blog.domain.com and domain.com are the same publisher
        domain_best: dict[str, dict] = {}
        root_seen: dict[str, str] = {}  # root_domain → first referring_domain seen
        for bl in backlinks_data:
            referring_domain = bl.get("name_source")
            if not referring_domain:
                continue
            
            root = extract_root_domain(referring_domain)
            
            # Keep first occurrence per root domain (highest traffic since API sorted)
            if root not in root_seen:
                root_seen[root] = referring_domain
                domain_best[referring_domain] = bl
        
        # Already sorted by API, but ensure order is preserved
        sorted_domains = list(domain_best.values())
        
        # Preview mode - just return the data
        if not save:
            return {
                "success": True,
                "competitor": competitor_domain,
                "total_fetched": len(backlinks_data),
                "unique_domains": len(sorted_domains),
                "domains": [
                    {
                        "domain": d.get("name_source"),
                        "traffic": d.get("traffic_domain"),
                        "dr": d.get("domain_rating_source"),
                        "url": d.get("url_from"),
                        "anchor": d.get("anchor"),
                    }
                    for d in sorted_domains
                ],
            }
        
        # Save mode
        added_domains = []
        added_backlinks = []

        # Pre-load all existing domains for root-domain dedup
        all_existing = {d.domain: d for d in db.query(Domain).filter(Domain.deleted_at.is_(None)).all()}
        existing_roots = {}
        for d_name in all_existing:
            r = extract_root_domain(d_name)
            if r not in existing_roots:
                existing_roots[r] = d_name

        overrides = adult_classifier.load_adult_overrides(db)
        fetch_candidates: list[tuple[Domain, Optional[list[str]]]] = []

        for bl in sorted_domains:
            referring_domain = bl.get("name_source")
            root = extract_root_domain(referring_domain)

            # Check if root domain already exists (blog.x.com matches x.com)
            domain = None
            if referring_domain in all_existing:
                domain = all_existing[referring_domain]
            elif root in existing_roots:
                domain = all_existing[existing_roots[root]]

            if not domain:
                domain = Domain(
                    domain=referring_domain,
                    is_competitor=False,
                    domain_rating=bl.get("domain_rating_source"),
                    organic_traffic=bl.get("traffic_domain"),
                )
                db.add(domain)
                db.flush()
                added_domains.append({
                    "domain": referring_domain,
                    "traffic": bl.get("traffic_domain"),
                    "dr": bl.get("domain_rating_source"),
                })
            anchors = [bl.get("anchor")] if bl.get("anchor") else None
            if adult_classifier.apply_import_verdict(domain, overrides, anchor_texts=anchors):
                fetch_candidates.append((domain, anchors))

            # Check if backlink already exists
            existing = db.query(Backlink).filter(
                Backlink.source_domain_id == domain.id,
                Backlink.target_domain == competitor_domain,
            ).first()
            
            if existing:
                continue
            
            # Create backlink record
            backlink = Backlink(
                source_domain_id=domain.id,
                source_url=bl.get("url_from"),
                target_domain=competitor_domain,
                target_url=bl.get("url_to"),
                anchor_text=bl.get("anchor"),
                is_dofollow=bl.get("is_dofollow", True),
                domain_rating=bl.get("domain_rating_source"),
                url_rating=bl.get("url_rating_source"),
                traffic=bl.get("traffic_domain"),
            )
            db.add(backlink)
            added_backlinks.append(referring_domain)

        # Bounded homepage fallback for domains signals couldn't decide
        adult_scan = await adult_classifier.run_import_fetch_pass(fetch_candidates)
        db.commit()

        return {
            "success": True,
            "competitor": competitor_domain,
            "total_fetched": len(backlinks_data),
            "unique_domains": len(sorted_domains),
            "domains_added": len(added_domains),
            "backlinks_added": len(added_backlinks),
            "adult_scan": adult_scan,
            "domains": added_domains,  # Return with traffic for review
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refdomains/{competitor_domain}")
async def fetch_referring_domains(
    competitor_domain: str,
    limit: int = Query(100, ge=1, le=1000),
    save: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    Fetch referring domains (one per domain, sorted by traffic).
    Uses the refdomains endpoint which is naturally deduplicated.
    """
    try:
        ahrefs = AhrefsService()
        refdomains = await ahrefs.get_referring_domains(competitor_domain, limit=limit)
        
        if not save:
            return {
                "success": True,
                "competitor": competitor_domain,
                "total": len(refdomains),
                "domains": [
                    {
                        "domain": d.get("name_source"),
                        "traffic": d.get("traffic_domain"),
                        "dr": d.get("domain_rating_source"),
                        "url": d.get("url_from"),
                        "anchor": d.get("anchor"),
                    }
                    for d in refdomains
                ],
            }
        
        added_domains = []

        # Pre-load for root-domain dedup
        all_existing = {d.domain: d for d in db.query(Domain).filter(Domain.deleted_at.is_(None)).all()}
        existing_roots = {}
        for d_name in all_existing:
            r = extract_root_domain(d_name)
            if r not in existing_roots:
                existing_roots[r] = d_name

        overrides = adult_classifier.load_adult_overrides(db)
        fetch_candidates: list[tuple[Domain, Optional[list[str]]]] = []

        root_seen_this_batch: set[str] = set()

        for rd in refdomains:
            referring_domain = rd.get("name_source")
            if not referring_domain:
                continue

            root = extract_root_domain(referring_domain)

            # Skip if root domain already in this batch
            if root in root_seen_this_batch:
                continue
            root_seen_this_batch.add(root)

            # Find existing by exact match or root domain match
            domain = None
            if referring_domain in all_existing:
                domain = all_existing[referring_domain]
            elif root in existing_roots:
                domain = all_existing[existing_roots[root]]

            if not domain:
                domain = Domain(
                    domain=referring_domain,
                    is_competitor=False,
                    domain_rating=rd.get("domain_rating_source"),
                    organic_traffic=rd.get("traffic_domain"),
                )
                db.add(domain)
                added_domains.append({
                    "domain": referring_domain,
                    "traffic": rd.get("traffic_domain"),
                    "dr": rd.get("domain_rating_source"),
                })
            anchors = [rd.get("anchor")] if rd.get("anchor") else None
            if adult_classifier.apply_import_verdict(domain, overrides, anchor_texts=anchors):
                fetch_candidates.append((domain, anchors))

        # Bounded homepage fallback for domains signals couldn't decide
        adult_scan = await adult_classifier.run_import_fetch_pass(fetch_candidates)
        db.commit()

        return {
            "success": True,
            "competitor": competitor_domain,
            "total": len(refdomains),
            "domains_added": len(added_domains),
            "adult_scan": adult_scan,
            "domains": added_domains,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis/{competitor_domain}")
async def analyze_competitor_backlinks(
    competitor_domain: str,
    db: Session = Depends(get_db),
):
    """
    Analyze backlink profile of a competitor.
    Returns anchor distribution, link velocity, etc.
    """
    backlinks = db.query(Backlink).filter(
        Backlink.target_domain == competitor_domain
    ).all()
    
    if not backlinks:
        raise HTTPException(status_code=404, detail="No backlinks found for this competitor")
    
    # Anchor text distribution
    anchor_counts: dict[str, int] = {}
    dofollow_count = 0
    total_dr = 0
    dr_count = 0
    
    for bl in backlinks:
        anchor = bl.anchor_text or "(no anchor)"
        anchor_counts[anchor] = anchor_counts.get(anchor, 0) + 1
        
        if bl.is_dofollow:
            dofollow_count += 1
        
        if bl.domain_rating:
            total_dr += bl.domain_rating
            dr_count += 1
    
    # Sort anchors by count
    anchor_distribution = sorted(
        [{"anchor": k, "count": v, "percent": round(v / len(backlinks) * 100, 1)} 
         for k, v in anchor_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:20]  # Top 20
    
    return {
        "competitor": competitor_domain,
        "total_backlinks": len(backlinks),
        "dofollow_count": dofollow_count,
        "nofollow_count": len(backlinks) - dofollow_count,
        "dofollow_percent": round(dofollow_count / len(backlinks) * 100, 1),
        "avg_domain_rating": round(total_dr / dr_count, 1) if dr_count > 0 else None,
        "anchor_distribution": anchor_distribution,
    }
