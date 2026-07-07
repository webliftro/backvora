"""
Domains API router - CRUD operations for domains.
"""

from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import Domain, DomainStatus, Backlink, LinkPrice, DomainPaymentMethod, Contact, ContactForm
from ..schemas.domain import (
    AdultOverrideRequest, DomainCreate, DomainUpdate, DomainResponse, DomainList,
    BulkDeleteRequest, BulkUpdateRequest,
)
from ..services import adult_classifier
from ..services.ahrefs import AhrefsService
from ..utils.domains import normalize_domain

router = APIRouter()

@router.get("", response_model=None)  # Custom response, not using DomainList
async def list_domains(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=10000),
    status: Optional[DomainStatus] = None,
    is_competitor: Optional[bool] = None,
    search: Optional[str] = None,
    target_domain: Optional[str] = None,  # Filter by competitor they link to
    db: Session = Depends(get_db),
):
    """List all domains with filtering, pagination, and backlink info."""
    query = db.query(Domain).filter(Domain.deleted_at.is_(None))
    
    if status:
        query = query.filter(Domain.status == status)
    if is_competitor is not None:
        query = query.filter(Domain.is_competitor == is_competitor)
    if search:
        query = query.filter(Domain.domain.ilike(f"%{search}%"))
    
    total = query.count()
    domains = query.offset((page - 1) * per_page).limit(per_page).all()
    
    if not domains:
        return {"items": [], "total": total, "page": page, "per_page": per_page, "pages": 0}
    
    domain_ids = [d.id for d in domains]
    
    # Batch: backlink counts per domain
    bl_counts = dict(
        db.query(Backlink.source_domain_id, func.count(Backlink.id))
        .filter(Backlink.source_domain_id.in_(domain_ids))
        .group_by(Backlink.source_domain_id)
        .all()
    )
    
    # Batch: first backlink per domain (for flat view)
    first_bls = {}
    if bl_counts:
        from sqlalchemy import distinct
        bl_rows = db.query(Backlink).filter(
            Backlink.source_domain_id.in_(list(bl_counts.keys()))
        ).all()
        for bl in bl_rows:
            if bl.source_domain_id not in first_bls:
                first_bls[bl.source_domain_id] = bl
    
    # Batch: link types per domain
    lt_rows = (
        db.query(LinkPrice.domain_id, LinkPrice.link_type)
        .filter(LinkPrice.domain_id.in_(domain_ids))
        .distinct()
        .all()
    )
    link_types_map = {}
    for did, lt in lt_rows:
        link_types_map.setdefault(did, []).append(lt)
    
    # Batch: contact stats per domain
    contact_counts = dict(
        db.query(Contact.domain_id, func.count(Contact.id))
        .filter(
            Contact.domain_id.in_(domain_ids),
            Contact.deleted_at.is_(None)
        )
        .group_by(Contact.domain_id)
        .all()
    )
    
    # Batch: has primary contact per domain
    has_primary = set(
        row[0] for row in db.query(Contact.domain_id)
        .filter(
            Contact.domain_id.in_(domain_ids),
            Contact.is_primary == True,
            Contact.deleted_at.is_(None)
        )
        .distinct()
        .all()
    )
    
    # Batch: has email contact per domain
    has_email = set(
        row[0] for row in db.query(Contact.domain_id)
        .filter(
            Contact.domain_id.in_(domain_ids),
            Contact.email.isnot(None),
            Contact.deleted_at.is_(None)
        )
        .distinct()
        .all()
    )
    
    # Batch: has form per domain
    has_form = set(
        row[0] for row in db.query(ContactForm.domain_id)
        .filter(ContactForm.domain_id.in_(domain_ids))
        .distinct()
        .all()
    )
    
    # Batch: has captcha form per domain
    has_captcha = set(
        row[0] for row in db.query(ContactForm.domain_id)
        .filter(
            ContactForm.domain_id.in_(domain_ids),
            ContactForm.has_captcha == True
        )
        .distinct()
        .all()
    )
    
    items = []
    for domain in domains:
        domain_dict = {
            "id": domain.id,
            "domain": domain.domain,
            "domain_rating": domain.domain_rating,
            "organic_traffic": domain.organic_traffic,
            "referring_domains": domain.referring_domains,
            "backlinks_count": domain.backlinks_count,
            "is_competitor": domain.is_competitor,
            "is_adult": domain.is_adult,
            "domain_niche": domain.domain_niche,
            "adult_method": domain.adult_method,
            "is_adult_overridden": domain.is_adult_overridden,
            "category": domain.category,
            "tags": domain.tags,
            "status": domain.status.value if domain.status else "new",
            "notes": domain.notes,
            "created_at": domain.created_at.isoformat() if domain.created_at else None,
            "updated_at": domain.updated_at.isoformat() if domain.updated_at else None,
        }

        count = bl_counts.get(domain.id, 0)
        first = first_bls.get(domain.id)
        domain_dict["backlink_count"] = count
        domain_dict["backlink_url"] = first.source_url if first else None
        domain_dict["backlink_target"] = first.target_domain if first else None
        domain_dict["backlink_anchor"] = first.anchor_text if first else None
        domain_dict["backlinks"] = []
        domain_dict["link_types"] = link_types_map.get(domain.id, [])
        
        # Add contact stats
        saved_contacts = contact_counts.get(domain.id, 0)
        has_domain_contact_info = bool(domain.owner or domain.email or domain.telegram)
        domain_dict["contacts_count"] = saved_contacts
        domain_dict["has_contact_info"] = saved_contacts > 0 or has_domain_contact_info or domain.id in has_form
        domain_dict["has_primary_contact"] = domain.id in has_primary
        domain_dict["has_email"] = domain.id in has_email or bool(domain.email)
        domain_dict["has_form"] = domain.id in has_form
        domain_dict["has_captcha"] = domain.id in has_captcha
        
        items.append(domain_dict)
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.post("", response_model=DomainResponse)
async def create_domain(
    data: DomainCreate,
    db: Session = Depends(get_db),
):
    """Add a new domain to track."""
    # Check if domain already exists (including soft-deleted)
    existing = db.query(Domain).filter(Domain.domain == data.domain).first()
    if existing:
        if existing.deleted_at:
            # Un-delete it
            existing.deleted_at = None
            db.commit()
            db.refresh(existing)
            return existing
        raise HTTPException(status_code=400, detail="Domain already exists")
    
    domain = Domain(**data.model_dump())
    db.add(domain)
    db.commit()
    db.refresh(domain)
    return domain


@router.get("/{domain_id}", response_model=None)
async def get_domain(
    domain_id: str,
    db: Session = Depends(get_db),
):
    """Get a specific domain by ID with full details."""
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    
    # Get backlinks
    backlinks = db.query(Backlink).filter(
        Backlink.source_domain_id == domain.id
    ).all()
    
    # Get link prices
    link_prices = db.query(LinkPrice).filter(
        LinkPrice.domain_id == domain.id,
        LinkPrice.deleted_at.is_(None),
    ).all()
    
    # Get payment methods
    payment_methods = db.query(DomainPaymentMethod).filter(
        DomainPaymentMethod.domain_id == domain.id,
        DomainPaymentMethod.deleted_at.is_(None),
    ).order_by(DomainPaymentMethod.is_preferred.desc()).all()

    override = adult_classifier.get_adult_override(db, domain.domain)

    return {
        "id": domain.id,
        "domain": domain.domain,
        "domain_rating": domain.domain_rating,
        "organic_traffic": domain.organic_traffic,
        "referring_domains": domain.referring_domains,
        "backlinks_count": domain.backlinks_count,
        "is_competitor": domain.is_competitor,
        "is_adult": domain.is_adult,
        "domain_niche": domain.domain_niche,
        "adult_method": domain.adult_method,
        "adult_confidence": domain.adult_confidence,
        "adult_detail": domain.adult_detail,
        "adult_classified_at": domain.adult_classified_at.isoformat() if domain.adult_classified_at else None,
        "is_adult_overridden": override is not None,
        "adult_override": {
            "verdict": override.verdict,
            "note": override.note,
            "root_domain": override.root_domain,
        } if override else None,
        "category": domain.category,
        "tags": domain.tags,
        "status": domain.status.value if domain.status else "new",
        "owner": domain.owner,
        "email": domain.email,
        "telegram": domain.telegram,
        "notes": domain.notes,
        "created_at": domain.created_at.isoformat() if domain.created_at else None,
        "updated_at": domain.updated_at.isoformat() if domain.updated_at else None,
        "last_analyzed_at": domain.last_analyzed_at.isoformat() if domain.last_analyzed_at else None,
        "backlinks": [
            {
                "target_domain": bl.target_domain,
                "source_url": bl.source_url,
                "target_url": bl.target_url,
                "anchor_text": bl.anchor_text,
                "is_dofollow": bl.is_dofollow,
                "domain_rating": bl.domain_rating,
                "traffic": bl.traffic,
            }
            for bl in backlinks
        ],
        "link_prices": [
            {
                "id": lp.id,
                "link_type": lp.link_type,
                "price": lp.price,
                "currency": lp.currency,
                "duration_months": lp.duration_months,
                "is_permanent": lp.is_permanent,
                "notes": lp.notes,
            }
            for lp in link_prices
        ],
        "payment_methods": [
            {
                "id": pm.id,
                "method": pm.method,
                "details": __import__('json').loads(pm.details) if pm.details and pm.details.startswith('{') else ({"note": pm.details} if pm.details else {}),
                "is_preferred": pm.is_preferred,
            }
            for pm in payment_methods
        ],
    }


@router.put("/{domain_id}", response_model=DomainResponse)
async def update_domain(
    domain_id: str,
    data: DomainUpdate,
    db: Session = Depends(get_db),
):
    """Update a domain.

    An explicit is_adult change is a manual decision: it is stored as a
    durable root-domain override so imports/reclassification can't undo it.
    """
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    payload = data.model_dump(exclude_unset=True)
    is_adult_value = payload.pop("is_adult", None)

    for key, value in payload.items():
        setattr(domain, key, value)

    if is_adult_value is not None:
        verdict = adult_classifier.NICHE_ADULT if is_adult_value else adult_classifier.NICHE_NON_ADULT
        adult_classifier.set_adult_override(db, domain.domain, verdict, note="set via domain edit")

    db.commit()
    db.refresh(domain)
    return domain


@router.put("/{domain_id}/adult-override")
async def set_domain_adult_override(
    domain_id: str,
    data: AdultOverrideRequest,
    db: Session = Depends(get_db),
):
    """Set a manual adult verdict override for this domain's root domain."""
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    override, affected = adult_classifier.set_adult_override(db, domain.domain, data.verdict, data.note)
    db.commit()
    return {
        "success": True,
        "root_domain": override.root_domain,
        "verdict": override.verdict,
        "note": override.note,
        "domains_updated": affected,
    }


@router.delete("/{domain_id}/adult-override")
async def clear_domain_adult_override(
    domain_id: str,
    db: Session = Depends(get_db),
):
    """Clear the manual override; the domain returns to classifier behavior
    on the next classification (verdict cache is reset)."""
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    affected = adult_classifier.clear_adult_override(db, domain.domain)
    db.commit()
    return {"success": True, "domains_reset": affected}


@router.delete("/{domain_id}")
async def delete_domain(
    domain_id: str,
    db: Session = Depends(get_db),
):
    """Soft delete a domain."""
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    
    from datetime import datetime
    domain.deleted_at = datetime.utcnow()
    db.commit()
    return {"success": True, "message": "Domain deleted"}


@router.post("/check-metrics")
async def check_metrics(
    domain: str = Query(..., description="Domain to check (e.g. example.com)"),
):
    """Check Ahrefs metrics for any domain without adding it to the database."""
    try:
        ahrefs = AhrefsService()
        metrics = await ahrefs.get_domain_metrics(domain.strip().lower())
        return {"success": True, "metrics": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{domain_id}/save-metrics")
async def save_metrics(
    domain_id: str,
    metrics: dict = Body(...),
    db: Session = Depends(get_db),
):
    """Save pre-fetched metrics to a domain (from check-metrics)."""
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    from datetime import datetime
    domain.domain_rating = metrics.get("domain_rating")
    domain.organic_traffic = metrics.get("organic_traffic")
    domain.referring_domains = metrics.get("referring_domains")
    domain.backlinks_count = metrics.get("backlinks_count")
    domain.status = DomainStatus.ANALYZED
    domain.last_analyzed_at = datetime.utcnow()
    db.commit()
    return {"success": True}


@router.post("/{domain_id}/analyze")
async def analyze_domain(
    domain_id: str,
    db: Session = Depends(get_db),
):
    """Fetch Ahrefs metrics for a domain."""
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    
    # Update status
    domain.status = DomainStatus.ANALYZING
    db.commit()
    
    try:
        ahrefs = AhrefsService()
        metrics = await ahrefs.get_domain_metrics(domain.domain)
        
        # Update domain with metrics
        domain.domain_rating = metrics.get("domain_rating")
        domain.organic_traffic = metrics.get("organic_traffic")
        domain.referring_domains = metrics.get("referring_domains")
        domain.backlinks_count = metrics.get("backlinks_count")
        domain.status = DomainStatus.ANALYZED
        
        from datetime import datetime
        domain.last_analyzed_at = datetime.utcnow()
        
        db.commit()
        db.refresh(domain)
        
        return {"success": True, "domain": domain, "metrics": metrics}
        
    except Exception as e:
        domain.status = DomainStatus.NEW
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-analyze")
async def batch_analyze_domains(
    limit: int = Query(10, ge=1, le=50),
    max_age_days: int = Query(7, ge=1),
    db: Session = Depends(get_db),
):
    """Analyze the most stale domains (older than max_age_days or never analyzed). Max 10 per call."""
    import asyncio
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    domains = db.query(Domain).filter(
        Domain.deleted_at.is_(None),
        Domain.is_competitor == False,
        (Domain.last_analyzed_at.is_(None)) | (Domain.last_analyzed_at < cutoff),
    ).order_by(
        Domain.last_analyzed_at.asc().nullsfirst()
    ).limit(limit).all()

    # Count remaining stale domains
    remaining = db.query(Domain).filter(
        Domain.deleted_at.is_(None),
        Domain.is_competitor == False,
        (Domain.last_analyzed_at.is_(None)) | (Domain.last_analyzed_at < cutoff),
    ).count() - len(domains)

    if not domains:
        return {"success": True, "analyzed": 0, "results": []}

    ahrefs = AhrefsService()
    results = []
    for domain in domains:
        try:
            metrics = await ahrefs.get_domain_metrics(domain.domain)
            domain.domain_rating = metrics.get("domain_rating")
            domain.organic_traffic = metrics.get("organic_traffic")
            domain.referring_domains = metrics.get("referring_domains")
            domain.backlinks_count = metrics.get("backlinks_count")
            domain.status = DomainStatus.ANALYZED
            domain.last_analyzed_at = datetime.utcnow()
            results.append({"domain": domain.domain, "status": "ok", "traffic": metrics.get("organic_traffic"), "dr": metrics.get("domain_rating")})
        except Exception as e:
            results.append({"domain": domain.domain, "status": "error", "error": str(e)})
        await asyncio.sleep(0.5)  # Rate limit buffer

    db.commit()
    return {"success": True, "analyzed": len([r for r in results if r["status"] == "ok"]), "remaining": remaining, "results": results}


@router.post("/bulk-delete")
async def bulk_delete_domains(
    data: BulkDeleteRequest,
    db: Session = Depends(get_db),
):
    """Bulk soft-delete multiple domains."""
    from datetime import datetime
    
    deleted = 0
    for domain_id in data.ids:
        domain = db.query(Domain).filter(Domain.id == domain_id).first()
        if domain and not domain.deleted_at:
            domain.deleted_at = datetime.utcnow()
            deleted += 1
    
    db.commit()
    
    return {"success": True, "deleted": deleted}


@router.post("/bulk-update")
async def bulk_update_domains(
    data: BulkUpdateRequest,
    db: Session = Depends(get_db),
):
    """Bulk update multiple domains (category, tags, status)."""
    updated = 0
    
    for domain_id in data.ids:
        domain = db.query(Domain).filter(Domain.id == domain_id).first()
        if domain:
            if data.category is not None:
                domain.category = data.category
            if data.tags is not None:
                domain.tags = data.tags
            if data.status is not None:
                domain.status = data.status
            updated += 1
    
    db.commit()
    
    return {"success": True, "updated": updated}


# Predefined categories and tags (can be extended to DB later)
import json
import os

PRESETS_FILE = "data/presets.json"

def load_presets():
    """Load predefined categories and tags from file."""
    if os.path.exists(PRESETS_FILE):
        try:
            with open(PRESETS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"categories": [], "tags": []}

def save_presets(presets):
    """Save predefined categories and tags to file."""
    os.makedirs(os.path.dirname(PRESETS_FILE), exist_ok=True)
    with open(PRESETS_FILE, 'w') as f:
        json.dump(presets, f, indent=2)


@router.get("/categories/list")
async def list_categories(
    db: Session = Depends(get_db),
):
    """Get all unique categories (predefined + used)."""
    presets = load_presets()
    predefined = set(presets.get("categories", []))
    
    results = db.query(Domain.category).filter(
        Domain.category.isnot(None),
        Domain.deleted_at.is_(None)
    ).distinct().all()
    
    used = set(r[0] for r in results if r[0])
    all_categories = sorted(predefined | used)
    
    return {"categories": all_categories, "predefined": list(predefined)}


@router.get("/tags/list")
async def list_tags(
    db: Session = Depends(get_db),
):
    """Get all unique tags (predefined + used)."""
    presets = load_presets()
    predefined = set(presets.get("tags", []))
    
    results = db.query(Domain.tags).filter(
        Domain.tags.isnot(None),
        Domain.deleted_at.is_(None)
    ).distinct().all()
    
    # Flatten and dedupe tags
    used = set()
    for r in results:
        if r[0]:
            for tag in r[0].split(','):
                tag = tag.strip()
                if tag:
                    used.add(tag)
    
    all_tags = sorted(predefined | used)
    
    return {"tags": all_tags, "predefined": list(predefined)}


def find_similar(new_item: str, existing: list[str], threshold: float = 0.8) -> list[str]:
    """Find similar items using simple lowercase comparison and prefix matching."""
    new_lower = new_item.lower().strip()
    similar = []
    for item in existing:
        item_lower = item.lower().strip()
        # Exact match (case insensitive)
        if new_lower == item_lower:
            similar.append(item)
        # One is prefix of other
        elif new_lower.startswith(item_lower) or item_lower.startswith(new_lower):
            similar.append(item)
        # Very similar (differ by only a few chars)
        elif len(new_lower) > 3 and len(item_lower) > 3:
            # Simple similarity: shared prefix length
            common = 0
            for a, b in zip(new_lower, item_lower):
                if a == b:
                    common += 1
                else:
                    break
            if common >= min(len(new_lower), len(item_lower)) * 0.7:
                similar.append(item)
    return similar


@router.post("/presets/categories")
async def set_predefined_categories(
    categories: list[str],
    db: Session = Depends(get_db),
):
    """Set predefined categories with duplicate/similar detection."""
    presets = load_presets()
    existing = presets.get("categories", [])
    
    # Get categories already in use
    results = db.query(Domain.category).filter(
        Domain.category.isnot(None),
        Domain.deleted_at.is_(None)
    ).distinct().all()
    used = [r[0] for r in results if r[0]]
    
    warnings = []
    cleaned = []
    seen = set()
    
    for cat in categories:
        cat = cat.strip()
        if not cat:
            continue
        
        cat_lower = cat.lower()
        
        # Check for duplicates in input
        if cat_lower in seen:
            warnings.append(f"Duplicate: '{cat}'")
            continue
        seen.add(cat_lower)
        
        # Check for similar existing presets
        similar_existing = [e for e in existing if e.lower() != cat_lower and find_similar(cat, [e])]
        if similar_existing:
            warnings.append(f"'{cat}' is similar to existing: {similar_existing}")
        
        # Check for similar used categories
        similar_used = [u for u in used if u.lower() != cat_lower and find_similar(cat, [u])]
        if similar_used:
            warnings.append(f"'{cat}' is similar to in-use: {similar_used}")
        
        cleaned.append(cat)
    
    presets["categories"] = cleaned
    save_presets(presets)
    
    return {
        "success": True, 
        "categories": cleaned,
        "warnings": warnings if warnings else None
    }


@router.post("/presets/tags")
async def set_predefined_tags(
    tags: list[str],
    db: Session = Depends(get_db),
):
    """Set predefined tags with duplicate/similar detection."""
    presets = load_presets()
    existing = presets.get("tags", [])
    
    # Get tags already in use
    results = db.query(Domain.tags).filter(
        Domain.tags.isnot(None),
        Domain.deleted_at.is_(None)
    ).distinct().all()
    used = set()
    for r in results:
        if r[0]:
            for tag in r[0].split(','):
                tag = tag.strip()
                if tag:
                    used.add(tag)
    
    warnings = []
    cleaned = []
    seen = set()
    
    for tag in tags:
        tag = tag.strip()
        if not tag:
            continue
        
        tag_lower = tag.lower()
        
        # Check for duplicates in input
        if tag_lower in seen:
            warnings.append(f"Duplicate: '{tag}'")
            continue
        seen.add(tag_lower)
        
        # Check for similar existing presets
        similar_existing = [e for e in existing if e.lower() != tag_lower and find_similar(tag, [e])]
        if similar_existing:
            warnings.append(f"'{tag}' is similar to existing: {similar_existing}")
        
        # Check for similar used tags
        similar_used = [u for u in used if u.lower() != tag_lower and find_similar(tag, [u])]
        if similar_used:
            warnings.append(f"'{tag}' is similar to in-use: {similar_used}")
        
        cleaned.append(tag)
    
    presets["tags"] = cleaned
    save_presets(presets)
    
    return {
        "success": True, 
        "tags": cleaned,
        "warnings": warnings if warnings else None
    }


@router.get("/competitors/list")
async def list_competitors(
    db: Session = Depends(get_db),
):
    """List all unique competitor (target) domains with backlink counts and stats."""
    from sqlalchemy import func, distinct
    
    # Get unique target domains from backlinks table with counts
    results = db.query(
        Backlink.target_domain,
        func.count(Backlink.id).label("backlink_count"),
        func.count(distinct(Backlink.source_domain_id)).label("referring_domains"),
        func.avg(Backlink.domain_rating).label("avg_dr"),
        func.avg(Backlink.traffic).label("avg_traffic"),
    ).filter(
        Backlink.deleted_at.is_(None) if hasattr(Backlink, 'deleted_at') else True
    ).group_by(
        Backlink.target_domain
    ).order_by(
        func.count(Backlink.id).desc()
    ).all()
    
    # Also get domains explicitly marked as competitor
    marked = db.query(Domain).filter(
        Domain.is_competitor == True,
        Domain.deleted_at.is_(None),
    ).all()
    
    # Merge: target domains from backlinks + explicitly marked competitors
    competitors = {}
    for r in results:
        competitors[r.target_domain] = {
            "domain": r.target_domain,
            "backlink_count": r.backlink_count,
            "referring_domains": r.referring_domains,
            "avg_dr": round(r.avg_dr, 1) if r.avg_dr else None,
            "avg_traffic": round(r.avg_traffic) if r.avg_traffic else None,
            "source": "backlinks",
        }
    
    for d in marked:
        if d.domain not in competitors:
            competitors[d.domain] = {
                "domain": d.domain,
                "domain_rating": d.domain_rating,
                "organic_traffic": d.organic_traffic,
                "backlink_count": 0,
                "referring_domains": 0,
                "avg_dr": None,
                "avg_traffic": None,
                "source": "marked",
            }
    
    return {"items": list(competitors.values()), "total": len(competitors)}


@router.delete("/competitors/{competitor_domain}")
async def remove_competitor(
    competitor_domain: str,
    delete_backlinks: bool = Query(True, description="Also delete all backlink records for this competitor"),
    delete_domains: bool = Query(False, description="Also delete referring domains that ONLY link to this competitor"),
    db: Session = Depends(get_db),
):
    """Remove a competitor and optionally its backlinks and orphaned referring domains."""
    from sqlalchemy import func
    
    removed = {"competitor": competitor_domain, "backlinks_deleted": 0, "domains_deleted": 0}
    
    # Unmark domain if it was marked as competitor
    marked = db.query(Domain).filter(
        Domain.domain == competitor_domain,
        Domain.is_competitor == True,
        Domain.deleted_at.is_(None),
    ).first()
    if marked:
        marked.is_competitor = False
        removed["unmarked"] = True
    
    if delete_backlinks:
        # Get all backlinks pointing to this competitor
        backlinks = db.query(Backlink).filter(
            Backlink.target_domain == competitor_domain,
        ).all()
        
        source_domain_ids = {bl.source_domain_id for bl in backlinks}
        
        # Delete the backlinks
        count = db.query(Backlink).filter(
            Backlink.target_domain == competitor_domain,
        ).delete()
        removed["backlinks_deleted"] = count
        
        if delete_domains and source_domain_ids:
            # Find domains that ONLY linked to this competitor (no other backlinks)
            for src_id in source_domain_ids:
                other_backlinks = db.query(Backlink).filter(
                    Backlink.source_domain_id == src_id,
                    Backlink.target_domain != competitor_domain,
                ).count()
                
                if other_backlinks == 0:
                    # This domain only linked to the removed competitor
                    # Soft-delete it unless it has orders, prices, or contacts
                    domain = db.query(Domain).filter(Domain.id == src_id).first()
                    if domain:
                        from ..models import Order, LinkPrice, Contact
                        has_orders = db.query(Order).filter(Order.domain_id == src_id).count() > 0
                        has_prices = db.query(LinkPrice).filter(
                            LinkPrice.domain_id == src_id, LinkPrice.deleted_at.is_(None)
                        ).count() > 0
                        has_contacts = db.query(Contact).filter(
                            Contact.domain_id == src_id, Contact.deleted_at.is_(None)
                        ).count() > 0
                        
                        if not has_orders and not has_prices and not has_contacts:
                            from datetime import datetime
                            domain.deleted_at = datetime.utcnow()
                            removed["domains_deleted"] = removed.get("domains_deleted", 0) + 1
    
    db.commit()
    return removed


@router.post("/bulk-import")
async def bulk_import_domains(
    domains: list[str],
    is_competitor: bool = False,
    db: Session = Depends(get_db),
):
    """Import multiple domains at once."""
    added = []
    skipped = []

    overrides = adult_classifier.load_adult_overrides(db)
    fetch_candidates: list[tuple[Domain, Optional[list[str]]]] = []

    for domain_name in domains:
        domain_name = normalize_domain(domain_name)
        if not domain_name:
            continue

        existing = db.query(Domain).filter(Domain.domain == domain_name).first()
        if existing:
            # Uncached/overridden duplicates still get their verdict refreshed
            if adult_classifier.apply_import_verdict(existing, overrides):
                fetch_candidates.append((existing, None))
            skipped.append(domain_name)
            continue

        domain = Domain(domain=domain_name, is_competitor=is_competitor)
        verdict = adult_classifier.classify_new_domain_for_import(domain_name, overrides=overrides)
        adult_classifier.apply_verdict_to_domain(domain, verdict)
        db.add(domain)
        added.append(domain_name)
        if verdict["domain_niche"] == adult_classifier.NICHE_UNKNOWN:
            fetch_candidates.append((domain, None))

    # Bounded homepage fallback for domains signals couldn't decide
    adult_scan = await adult_classifier.run_import_fetch_pass(fetch_candidates)
    db.commit()

    return {
        "success": True,
        "added": len(added),
        "skipped": len(skipped),
        "adult_scan": adult_scan,
        "added_domains": added,
        "skipped_domains": skipped,
    }


# ============ Owner Autocomplete ============

@router.get("/owners/search")
async def search_owners(q: str = Query("", min_length=1), db: Session = Depends(get_db)):
    """Search existing owners by name or email prefix."""
    import json as _json
    results = db.query(Domain.id, Domain.owner, Domain.email, Domain.telegram).filter(
        Domain.deleted_at.is_(None),
        (Domain.owner.ilike(f"%{q}%")) | (Domain.email.ilike(f"%{q}%")),
        Domain.owner.isnot(None),
    ).limit(50).all()
    # Dedupe by owner+email, collect domain IDs per owner
    owner_map: dict[tuple, dict] = {}
    for did, owner, email, telegram in results:
        key = (owner or "", email or "")
        if key not in owner_map:
            owner_map[key] = {"owner": owner, "email": email, "telegram": telegram, "domain_ids": []}
        owner_map[key]["domain_ids"].append(did)
    
    # Fetch payment methods from all matched domains
    all_domain_ids = []
    for v in owner_map.values():
        all_domain_ids.extend(v["domain_ids"])
    
    pm_rows = db.query(DomainPaymentMethod).filter(
        DomainPaymentMethod.domain_id.in_(all_domain_ids),
        DomainPaymentMethod.deleted_at.is_(None),
    ).all() if all_domain_ids else []
    
    # Map payment methods by domain_id
    pm_by_domain: dict[str, list] = {}
    for pm in pm_rows:
        pm_by_domain.setdefault(pm.domain_id, []).append(pm)
    
    items = []
    for key, v in list(owner_map.items())[:10]:
        # Collect unique payment methods across all this owner's domains
        seen_methods = set()
        payment_methods = []
        for did in v["domain_ids"]:
            for pm in pm_by_domain.get(did, []):
                method_key = (pm.method, pm.details or "")
                if method_key not in seen_methods:
                    seen_methods.add(method_key)
                    try: details = _json.loads(pm.details) if pm.details and pm.details.startswith('{') else {}
                    except: details = {}
                    payment_methods.append({"method": pm.method, "details": details, "is_preferred": pm.is_preferred})
        items.append({"owner": v["owner"], "email": v["email"], "telegram": v["telegram"], "payment_methods": payment_methods})
    return {"items": items}


# ============ Payment Methods ============

PAYMENT_METHODS = ["PayPal", "Wire Transfer", "Paxum", "Crypto"]

# Structured fields per payment method type
PAYMENT_FIELDS: dict[str, list[dict]] = {
    "PayPal": [
        {"key": "email", "label": "PayPal Email", "required": True},
    ],
    "Wire Transfer": [
        {"key": "name", "label": "Account Holder Name", "required": True},
        {"key": "company", "label": "Company Name", "required": False},
        {"key": "address", "label": "Address", "required": False},
        {"key": "country", "label": "Country", "required": True, "type": "select", "options": [
            "Afghanistan","Albania","Algeria","Andorra","Angola","Argentina","Armenia","Australia","Austria","Azerbaijan",
            "Bahamas","Bahrain","Bangladesh","Barbados","Belarus","Belgium","Belize","Benin","Bhutan","Bolivia",
            "Bosnia and Herzegovina","Botswana","Brazil","Brunei","Bulgaria","Burkina Faso","Burundi",
            "Cambodia","Cameroon","Canada","Cape Verde","Central African Republic","Chad","Chile","China","Colombia",
            "Comoros","Congo","Costa Rica","Croatia","Cuba","Cyprus","Czech Republic",
            "Denmark","Djibouti","Dominica","Dominican Republic",
            "Ecuador","Egypt","El Salvador","Equatorial Guinea","Eritrea","Estonia","Eswatini","Ethiopia",
            "Fiji","Finland","France",
            "Gabon","Gambia","Georgia","Germany","Ghana","Greece","Grenada","Guatemala","Guinea","Guinea-Bissau","Guyana",
            "Haiti","Honduras","Hungary",
            "Iceland","India","Indonesia","Iran","Iraq","Ireland","Israel","Italy",
            "Jamaica","Japan","Jordan",
            "Kazakhstan","Kenya","Kiribati","Kosovo","Kuwait","Kyrgyzstan",
            "Laos","Latvia","Lebanon","Lesotho","Liberia","Libya","Liechtenstein","Lithuania","Luxembourg",
            "Madagascar","Malawi","Malaysia","Maldives","Mali","Malta","Marshall Islands","Mauritania","Mauritius",
            "Mexico","Micronesia","Moldova","Monaco","Mongolia","Montenegro","Morocco","Mozambique","Myanmar",
            "Namibia","Nauru","Nepal","Netherlands","New Zealand","Nicaragua","Niger","Nigeria","North Korea","North Macedonia","Norway",
            "Oman",
            "Pakistan","Palau","Palestine","Panama","Papua New Guinea","Paraguay","Peru","Philippines","Poland","Portugal",
            "Qatar",
            "Romania","Russia","Rwanda",
            "Saint Kitts and Nevis","Saint Lucia","Saint Vincent and the Grenadines","Samoa","San Marino",
            "Sao Tome and Principe","Saudi Arabia","Senegal","Serbia","Seychelles","Sierra Leone","Singapore",
            "Slovakia","Slovenia","Solomon Islands","Somalia","South Africa","South Korea","South Sudan","Spain",
            "Sri Lanka","Sudan","Suriname","Sweden","Switzerland","Syria",
            "Taiwan","Tajikistan","Tanzania","Thailand","Timor-Leste","Togo","Tonga","Trinidad and Tobago",
            "Tunisia","Turkey","Turkmenistan","Tuvalu",
            "Uganda","Ukraine","United Arab Emirates","United Kingdom","United States","Uruguay","Uzbekistan",
            "Vanuatu","Vatican City","Venezuela","Vietnam",
            "Yemen",
            "Zambia","Zimbabwe",
        ]},
        {"key": "iban", "label": "IBAN", "required": True},
        {"key": "bic_swift", "label": "BIC/SWIFT", "required": False},
        {"key": "vat", "label": "VAT Number", "required": False},
    ],
    "Paxum": [
        {"key": "email", "label": "Paxum Email", "required": True},
    ],
    "Crypto": [
        {"key": "currency", "label": "Currency (BTC, ETH, USDT...)", "required": True},
        {"key": "network", "label": "Network (e.g. TRC20, ERC20)", "required": False},
        {"key": "wallet", "label": "Wallet Address", "required": True},
    ],
}


@router.get("/{domain_id}/payment-methods")
async def list_payment_methods(domain_id: str, db: Session = Depends(get_db)):
    methods = db.query(DomainPaymentMethod).filter(
        DomainPaymentMethod.domain_id == domain_id,
        DomainPaymentMethod.deleted_at.is_(None),
    ).order_by(DomainPaymentMethod.is_preferred.desc()).all()
    import json
    items = []
    for m in methods:
        d = {"id": m.id, "method": m.method, "is_preferred": m.is_preferred}
        try: d["details"] = json.loads(m.details) if m.details else {}
        except: d["details"] = {"note": m.details} if m.details else {}
        items.append(d)
    return {"items": items, "available": PAYMENT_METHODS, "fields": PAYMENT_FIELDS}


@router.post("/{domain_id}/payment-methods")
async def add_payment_method(domain_id: str, data: dict, db: Session = Depends(get_db)):
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    method = data.get("method", "").strip()
    if not method:
        raise HTTPException(status_code=400, detail="Method required")
    # If first payment method for this domain, make it preferred
    existing = db.query(DomainPaymentMethod).filter(
        DomainPaymentMethod.domain_id == domain_id,
        DomainPaymentMethod.deleted_at.is_(None),
    ).count()
    import json as _json
    details = data.get("details")
    if isinstance(details, dict):
        details = _json.dumps(details)
    pm = DomainPaymentMethod(
        domain_id=domain_id,
        method=method,
        details=details,
        is_preferred=existing == 0,
    )
    db.add(pm)
    db.commit()
    db.refresh(pm)
    return {"id": pm.id, "method": pm.method, "details": pm.details, "is_preferred": pm.is_preferred}


@router.put("/{domain_id}/payment-methods/{pm_id}")
async def update_payment_method(domain_id: str, pm_id: str, data: dict, db: Session = Depends(get_db)):
    pm = db.query(DomainPaymentMethod).filter(DomainPaymentMethod.id == pm_id, DomainPaymentMethod.domain_id == domain_id).first()
    if not pm:
        raise HTTPException(status_code=404, detail="Not found")
    import json as _json
    if "method" in data:
        pm.method = data["method"]
    if "details" in data:
        d = data["details"]
        pm.details = _json.dumps(d) if isinstance(d, dict) else d
    db.commit()
    return {"success": True}


@router.post("/{domain_id}/payment-methods/{pm_id}/set-preferred")
async def set_preferred_payment(domain_id: str, pm_id: str, db: Session = Depends(get_db)):
    # Unset all preferred for this domain
    db.query(DomainPaymentMethod).filter(
        DomainPaymentMethod.domain_id == domain_id,
        DomainPaymentMethod.deleted_at.is_(None),
    ).update({"is_preferred": False})
    # Set this one
    pm = db.query(DomainPaymentMethod).filter(DomainPaymentMethod.id == pm_id, DomainPaymentMethod.domain_id == domain_id).first()
    if not pm:
        raise HTTPException(status_code=404, detail="Not found")
    pm.is_preferred = True
    db.commit()
    return {"success": True}


@router.delete("/{domain_id}/payment-methods/{pm_id}")
async def delete_payment_method(domain_id: str, pm_id: str, db: Session = Depends(get_db)):
    pm = db.query(DomainPaymentMethod).filter(DomainPaymentMethod.id == pm_id, DomainPaymentMethod.domain_id == domain_id).first()
    if not pm:
        raise HTTPException(status_code=404, detail="Not found")
    from datetime import datetime
    pm.deleted_at = datetime.utcnow()
    was_preferred = pm.is_preferred
    db.commit()
    # If deleted the preferred one, promote the next one
    if was_preferred:
        next_pm = db.query(DomainPaymentMethod).filter(
            DomainPaymentMethod.domain_id == domain_id,
            DomainPaymentMethod.deleted_at.is_(None),
        ).first()
        if next_pm:
            next_pm.is_preferred = True
            db.commit()
    return {"success": True}


@router.post("/{domain_id}/grab-contact")
async def grab_contact_from_inbox(domain_id: str, db: Session = Depends(get_db)):
    """Search IMAP inbox for emails related to this domain and extract contact info."""
    import imaplib
    import email as email_lib
    from email.header import decode_header
    from email.utils import parseaddr
    from ..config import settings
    
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(404, "Domain not found")
    
    email_domain = domain.domain.replace("www.", "")
    found_contacts = []
    
    try:
        mail = imaplib.IMAP4_SSL(settings.imap_host)
        mail.login(settings.email_account, settings.email_password)
        
        for folder in ["INBOX", '"[Gmail]/Sent Mail"']:
            try:
                mail.select(folder, readonly=True)
            except:
                continue
            
            queries = [
                f'(FROM "@{email_domain}")',
                f'(TO "@{email_domain}")',
                f'(SUBJECT "{email_domain}")',
            ]
            
            seen = set()
            for q in queries:
                try:
                    _, msg_ids = mail.search(None, q)
                    for num in (msg_ids[0].split() if msg_ids[0] else [])[-10:]:
                        if num in seen:
                            continue
                        seen.add(num)
                        _, msg_data = mail.fetch(num, "(RFC822)")
                        if msg_data[0] is None:
                            continue
                        msg = email_lib.message_from_bytes(msg_data[0][1])
                        
                        for header in ["From", "To", "Reply-To", "Cc"]:
                            raw = msg.get(header, "")
                            if not raw:
                                continue
                            import re
                            addrs = re.findall(r'[\w.+-]+@[\w.-]+', raw)
                            for addr in addrs:
                                addr_lower = addr.lower()
                                if addr_lower == settings.email_account.lower():
                                    continue
                                name, _ = parseaddr(raw)
                                if not name or name == addr:
                                    name = ""
                                found_contacts.append({
                                    "email": addr_lower,
                                    "name": name,
                                    "source": header,
                                })
                except Exception:
                    continue
        
        mail.logout()
    except Exception as e:
        raise HTTPException(500, f"IMAP error: {str(e)}")
    
    if not found_contacts:
        return {"found": 0, "contacts": [], "saved": False}
    
    # Deduplicate, prioritize From > Reply-To > To > Cc
    priority = {"From": 0, "Reply-To": 1, "To": 2, "Cc": 3}
    by_email = {}
    for c in found_contacts:
        e = c["email"]
        if e not in by_email or priority.get(c["source"], 9) < priority.get(by_email[e]["source"], 9):
            by_email[e] = c
    
    unique = list(by_email.values())
    
    # Auto-save if domain has no owner/email
    saved = False
    if not domain.email and not domain.owner:
        best = None
        for c in unique:
            if email_domain in c["email"]:
                best = c
                break
        if not best:
            for c in unique:
                if c["source"] == "From":
                    best = c
                    break
        if not best:
            best = unique[0]
        
        domain.email = best["email"]
        if best["name"]:
            domain.owner = best["name"]
        db.commit()
        saved = True
    
    return {
        "found": len(unique),
        "contacts": unique[:10],
        "saved": saved,
        "saved_email": domain.email if saved else None,
    }


class SelectedGrabRequest(BaseModel):
    domain_ids: list[str]


class ClassifyAdultRequest(BaseModel):
    domain_ids: list[str]
    force_refresh: bool = False  # re-run classifier on cached verdicts (overrides still win)


@router.post("/classify-adult")
async def classify_adult_domains(body: ClassifyAdultRequest, db: Session = Depends(get_db)):
    """Classify selected domains via the shared adult classifier.

    Precedence per domain: manual override > cached verdict (unless
    force_refresh) > keyword/signal scoring > one homepage fetch > AI.
    Verdict metadata is persisted. Processes up to 5 domains concurrently
    to stay within proxy timeout.
    """
    import asyncio

    if not body.domain_ids:
        return {"scanned": 0, "adult": 0, "non_adult": 0, "unclear": 0, "results": []}

    targets = db.query(Domain).filter(
        Domain.id.in_(body.domain_ids),
        Domain.deleted_at.is_(None),
    ).all()

    # Anchor texts give the classifier extra context (batched, one query)
    anchor_rows = db.query(Backlink.source_domain_id, Backlink.anchor_text).filter(
        Backlink.source_domain_id.in_([d.id for d in targets]),
        Backlink.anchor_text.isnot(None),
    ).all()
    anchors_map: dict[str, list[str]] = {}
    for did, anchor in anchor_rows:
        anchors_map.setdefault(did, []).append(anchor)

    semaphore = asyncio.Semaphore(5)

    async def classify_one(d: Domain) -> dict:
        async with semaphore:
            try:
                return await asyncio.wait_for(
                    adult_classifier.classify_domain_with_cache(
                        db, d,
                        anchor_texts=anchors_map.get(d.id),
                        force_refresh=body.force_refresh,
                    ),
                    timeout=20,
                )
            except asyncio.TimeoutError:
                return {"domain": d.domain, "domain_niche": "unknown", "is_adult": None,
                        "confidence": 0, "method": "timeout", "detail": "scan timed out"}

    scan_results = await asyncio.gather(*[classify_one(d) for d in targets])
    db.commit()

    results = []
    adult_count = 0
    non_adult_count = 0
    unclear_count = 0
    for r in scan_results:
        niche = r.get("domain_niche")
        if niche == adult_classifier.NICHE_ADULT:
            adult_count += 1
        elif niche == adult_classifier.NICHE_NON_ADULT:
            non_adult_count += 1
        else:
            unclear_count += 1
        results.append({
            "domain": r["domain"],
            "is_adult": r.get("is_adult"),
            "domain_niche": niche,
            "confidence": r.get("confidence", 0),
            "method": r.get("method", "unknown"),
            "detail": r.get("detail", ""),
        })

    return {
        "scanned": len(targets),
        "adult": adult_count,
        "non_adult": non_adult_count,
        "unclear": unclear_count,
        "results": results,
    }


@router.post("/selected-grab-contacts")
async def selected_grab_contacts(
    body: SelectedGrabRequest,
    db: Session = Depends(get_db),
):
    """Grab contacts for selected domains via SSE stream.
    
    Streams real-time progress as each domain is processed:
    1. IMAP inbox search (all domains, fast)
    2. Page scraper — ContactsGrabber (domains without IMAP match)
    3. Whois lookup (domains still without email)
    
    Each event: {type, domain, email, method, progress, total}
    """
    import json
    import asyncio
    import imaplib
    import re as re_mod
    import httpx
    from fastapi.responses import StreamingResponse
    from ..config import settings
    from ..services.scraper import EmailScraper, ContactsGrabber

    targets = db.query(Domain).filter(
        Domain.id.in_(body.domain_ids),
        Domain.deleted_at.is_(None),
    ).all()

    if not targets:
        return {"scanned": 0, "found": 0}

    async def event_stream():
        total = len(targets)
        found = 0
        processed = 0

        def emit(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        yield emit({"type": "start", "total": total})

        # --- Phase 1: IMAP ---
        yield emit({"type": "phase", "phase": "inbox", "message": f"Checking inbox for {total} domains..."})
        imap_found = {}
        try:
            mail = imaplib.IMAP4_SSL(settings.imap_host)
            mail.login(settings.email_account, settings.email_password)
            mail.select("INBOX", readonly=True)

            for d in targets:
                email_domain = d.domain.replace("www.", "")
                try:
                    _, msg_ids = mail.search(None, f'(FROM "@{email_domain}")')
                    nums = (msg_ids[0].split() if msg_ids[0] else [])[-3:]
                    for num in nums:
                        _, msg_data = mail.fetch(num, "(BODY[HEADER.FIELDS (FROM REPLY-TO)])")
                        if msg_data[0] is None:
                            continue
                        header_data = msg_data[0][1]
                        if isinstance(header_data, bytes):
                            header_data = header_data.decode("utf-8", errors="replace")
                        addrs = re_mod.findall(r'[\w.+-]+@[\w.-]+', header_data)
                        for addr in addrs:
                            addr_lower = addr.lower()
                            if addr_lower != settings.email_account.lower():
                                name_match = re_mod.search(r'(?:From|Reply-To):\s*(?:"?([^"<]+)"?\s*<)', header_data)
                                name = name_match.group(1).strip() if name_match else ""
                                imap_found[d.id] = {"email": addr_lower, "name": name}
                                break
                        if d.id in imap_found:
                            break
                except Exception:
                    continue

            mail.logout()
        except Exception as e:
            yield emit({"type": "error", "message": f"IMAP error: {e}"})

        # Save + emit IMAP results
        for d in targets:
            if d.id in imap_found:
                best = imap_found[d.id]
                d.email = best["email"]
                if best["name"]:
                    d.owner = best["name"]
                processed += 1
                found += 1
                yield emit({"type": "found", "domain": d.domain, "email": best["email"], "method": "inbox", "progress": processed, "total": total})
        db.commit()

        # --- Phase 2: Page scraper ---
        need_scrape = [d for d in targets if d.id not in imap_found]
        if need_scrape:
            yield emit({"type": "phase", "phase": "scraper", "message": f"Scraping {len(need_scrape)} websites for contacts..."})
            email_scraper = EmailScraper()
            semaphore = asyncio.Semaphore(10)

            async def scrape_one(d):
                """Returns (domain, result_dict_or_None, was_cf_blocked)"""
                async with semaphore:
                    cf_blocked = False
                    try:
                        async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                        }) as client:
                            for path in ["", "/contact", "/contact-us", "/advertise", "/about"]:
                                try:
                                    url = f"https://{d.domain}{path}"
                                    resp = await client.get(url)
                                    if resp.status_code == 200:
                                        for e in email_scraper._extract_emails(resp.text):
                                            if not email_scraper._is_blacklisted(e):
                                                return d, {"email": e.lower(), "source_url": url, "source_type": path or "homepage"}, False
                                    elif resp.status_code in (403, 503) and "just a moment" in resp.text[:500].lower():
                                        cf_blocked = True
                                except Exception:
                                    continue
                    except Exception:
                        pass
                    return d, None, cf_blocked

            cf_blocked_domains = []
            tasks = [scrape_one(d) for d in need_scrape]
            for coro in asyncio.as_completed(tasks):
                d, result, was_cf = await coro
                processed += 1
                if result:
                    d.email = result["email"]
                    existing = db.query(Contact).filter(
                        Contact.domain_id == d.id, Contact.email == result["email"], Contact.deleted_at.is_(None),
                    ).first()
                    if not existing:
                        db.add(Contact(
                            domain_id=d.id, email=result["email"],
                            source_page=result.get("source_url"),
                            source_type=result.get("source_type", "scraper"),
                            is_primary=True,
                        ))
                    found += 1
                    yield emit({"type": "found", "domain": d.domain, "email": result["email"], "method": "scraper", "progress": processed, "total": total})
                elif was_cf:
                    cf_blocked_domains.append(d)
                    yield emit({"type": "miss", "domain": d.domain, "method": "cf_blocked", "progress": processed, "total": total})
                else:
                    yield emit({"type": "miss", "domain": d.domain, "method": "scraper", "progress": processed, "total": total})
            db.commit()

        # --- Phase 2.5: Browser scrape for CF-blocked domains ---
        if cf_blocked_domains:
            yield emit({"type": "phase", "phase": "browser", "message": f"Browser scraping {len(cf_blocked_domains)} CF-protected sites..."})
            for d in cf_blocked_domains:
                try:
                    import subprocess
                    # Use agent-browser to open contact page and extract mailto links
                    session_name = f"grab_{d.domain.replace('.','_')}"
                    subprocess.run(["agent-browser", "--session", session_name, "--headed", "open", f"https://{d.domain}/contact"], capture_output=True, timeout=20)
                    subprocess.run(["agent-browser", "--session", session_name, "wait", "--load", "networkidle"], capture_output=True, timeout=15)
                    import time; time.sleep(2)
                    
                    # Extract mailto links and visible emails
                    js_result = subprocess.run(
                        ["agent-browser", "--session", session_name, "eval", "--stdin"],
                        input=b'''(function() {
                            var mailtos = Array.from(document.querySelectorAll('a[href^="mailto:"]')).map(a => a.href.replace('mailto:','').split('?')[0]);
                            var text = document.body.innerText;
                            var visible = text.match(/[\\w.+-]+@[\\w.-]+\\.[a-z]{2,}/gi) || [];
                            return JSON.stringify([...new Set([...mailtos, ...visible])]);
                        })()''',
                        capture_output=True, timeout=10,
                    )
                    subprocess.run(["agent-browser", "--session", session_name, "close"], capture_output=True, timeout=5)
                    
                    if js_result.returncode == 0:
                        import json as _json
                        raw = js_result.stdout.decode().strip().strip('"')
                        emails = _json.loads(raw) if raw.startswith('[') else []
                        emails = [e.lower() for e in emails if e and '@' in e and not email_scraper._is_blacklisted(e.lower())]
                        
                        if emails:
                            d.email = emails[0]
                            existing = db.query(Contact).filter(
                                Contact.domain_id == d.id, Contact.email == emails[0], Contact.deleted_at.is_(None),
                            ).first()
                            if not existing:
                                db.add(Contact(
                                    domain_id=d.id, email=emails[0],
                                    source_type="browser_scrape", is_primary=True,
                                ))
                            found += 1
                            yield emit({"type": "found", "domain": d.domain, "email": emails[0], "method": "browser", "progress": processed, "total": total})
                            db.commit()
                            continue
                except Exception as e:
                    print(f"Browser scrape error for {d.domain}: {e}")
                
                yield emit({"type": "miss", "domain": d.domain, "method": "browser", "progress": processed, "total": total})

        # --- Phase 3: Whois for remaining ---
        need_whois = [d for d in targets if not d.email]
        if need_whois:
            yield emit({"type": "phase", "phase": "whois", "message": f"Checking whois for {len(need_whois)} domains..."})
            for d in need_whois:
                processed_before = processed
                try:
                    import subprocess
                    result = subprocess.run(
                        ["whois", d.domain], capture_output=True, text=True, timeout=10,
                    )
                    if result.returncode == 0:
                        whois_emails = re_mod.findall(r'[\w.+-]+@[\w.-]+', result.stdout)
                        # Filter out registrar/abuse emails
                        whois_emails = [
                            e.lower() for e in whois_emails
                            if not any(x in e.lower() for x in ["abuse@", "noreply@", "privacy@", "contact@privacyguard", "whoisguard", "domainsby", "registrar"])
                        ]
                        if whois_emails:
                            email = whois_emails[0]
                            d.email = email
                            existing = db.query(Contact).filter(
                                Contact.domain_id == d.id, Contact.email == email, Contact.deleted_at.is_(None),
                            ).first()
                            if not existing:
                                db.add(Contact(
                                    domain_id=d.id, email=email,
                                    source_type="whois", is_primary=True,
                                ))
                            found += 1
                            yield emit({"type": "found", "domain": d.domain, "email": email, "method": "whois", "progress": processed + 1, "total": total})
                        else:
                            yield emit({"type": "miss", "domain": d.domain, "method": "whois", "progress": processed + 1, "total": total})
                except Exception:
                    yield emit({"type": "miss", "domain": d.domain, "method": "whois", "progress": processed + 1, "total": total})
                processed += 1
            db.commit()

        yield emit({"type": "done", "total": total, "found": found, "missed": total - found})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/bulk-grab-contacts")
async def bulk_grab_contacts(db: Session = Depends(get_db)):
    """Grab contacts from inbox for all domains missing contact info. Uses single IMAP connection."""
    import imaplib
    import email as email_lib
    from email.utils import parseaddr
    from ..config import settings
    from ..models import Contact
    
    missing = db.query(Domain).filter(
        Domain.deleted_at.is_(None),
        (Domain.email.is_(None) | (Domain.email == "")),
    ).all()
    
    has_contacts = {
        r[0] for r in db.query(Contact.domain_id).filter(Contact.deleted_at.is_(None)).distinct().all()
    }
    
    targets = [d for d in missing if d.id not in has_contacts][:100]
    
    if not targets:
        return {"scanned": 0, "found": 0, "results": []}
    
    results = []
    try:
        mail = imaplib.IMAP4_SSL(settings.imap_host)
        mail.login(settings.email_account, settings.email_password)
        
        for d in targets:
            email_domain = d.domain.replace("www.", "")
            found = []
            
            for folder in ["INBOX", '"[Gmail]/Sent Mail"']:
                try:
                    mail.select(folder, readonly=True)
                except:
                    continue
                
                for q in [f'(FROM "@{email_domain}")', f'(TO "@{email_domain}")', f'(SUBJECT "{email_domain}")']:
                    try:
                        _, msg_ids = mail.search(None, q)
                        for num in (msg_ids[0].split() if msg_ids[0] else [])[-3:]:
                            _, msg_data = mail.fetch(num, "(BODY[HEADER.FIELDS (FROM TO REPLY-TO)])")
                            if msg_data[0] is None:
                                continue
                            header_data = msg_data[0][1]
                            if isinstance(header_data, bytes):
                                header_data = header_data.decode("utf-8", errors="replace")
                            
                            import re
                            addrs = re.findall(r'[\w.+-]+@[\w.-]+', header_data)
                            for addr in addrs:
                                addr_lower = addr.lower()
                                if addr_lower != settings.email_account.lower():
                                    name_match = re.search(r'(?:From|Reply-To):\s*(?:"?([^"<]+)"?\s*<)', header_data)
                                    name = name_match.group(1).strip() if name_match else ""
                                    found.append({"email": addr_lower, "name": name})
                    except:
                        continue
            
            if found:
                # Dedupe, prefer @domain emails
                by_email = {}
                for c in found:
                    if c["email"] not in by_email:
                        by_email[c["email"]] = c
                
                best = None
                for c in by_email.values():
                    if email_domain in c["email"]:
                        best = c
                        break
                if not best:
                    best = list(by_email.values())[0]
                
                d.email = best["email"]
                if best["name"]:
                    d.owner = best["name"]
                results.append({"domain": d.domain, "email": best["email"]})
        
        db.commit()
        mail.logout()
    except Exception as e:
        print(f"Bulk grab error: {e}")
        db.commit()  # Save what we got
    
    return {"scanned": len(targets), "found": len(results), "results": results}
