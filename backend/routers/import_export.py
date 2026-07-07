"""
Import/Export router - CSV imports from Ahrefs, SEMrush, etc.
"""

import csv
import io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Domain, Backlink
from ..services import adult_classifier
from ..utils.domains import extract_root_domain

router = APIRouter()


@router.post("/ahrefs-backlinks")
async def import_ahrefs_backlinks_csv(
    file: UploadFile = File(...),
    competitor_domain: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Import backlinks from Ahrefs CSV export.
    
    Expected columns (flexible matching):
    - Referring Page URL / URL From
    - Domain Rating (Source) / DR
    - Domain Traffic / Traffic  
    - Anchor / Anchor Text
    - Dofollow / Follow
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    content = await file.read()
    
    # Try different encodings (Ahrefs exports vary)
    text = None
    for encoding in ['utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be', 'latin-1']:
        try:
            text = content.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    
    if text is None:
        raise HTTPException(status_code=400, detail="Could not decode CSV file - unsupported encoding")
    
    # Detect delimiter (Ahrefs uses tabs, others use commas)
    first_line = text.split('\n')[0] if text else ''
    delimiter = '\t' if '\t' in first_line else ','
    
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    
    # Debug: log the column names
    fieldnames = reader.fieldnames or []
    print(f"CSV delimiter: '{delimiter}', columns found: {fieldnames}")
    
    # Normalize column names (Ahrefs exports vary)
    def find_col(row: dict, options: list[str]) -> Optional[str]:
        for opt in options:
            for key in row.keys():
                if opt.lower() in key.lower():
                    return row[key]
        return None
    
    added_domains = []
    added_backlinks = []
    skipped = 0

    overrides = adult_classifier.load_adult_overrides(db)
    # domain.id → [domain, anchors]; anchors accumulate across rows so the
    # fetch pass sees the full anchor evidence for each ambiguous domain
    fetch_candidates: dict[str, list] = {}
    classified_ids: set[str] = set()

    row_count = 0
    for row in reader:
        row_count += 1
        if row_count <= 3:
            print(f"Row {row_count}: {dict(row)}")
        
        # Extract domain from referring URL
        url_from = find_col(row, ['Referring page URL', 'Referring Page URL', 'URL From', 'Source URL', 'Referring Page'])
        if not url_from:
            if row_count <= 3:
                print(f"  -> No URL found, skipping")
            skipped += 1
            continue
        
        # Parse domain from URL
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url_from)
            referring_domain = parsed.netloc.lower()
            if referring_domain.startswith('www.'):
                referring_domain = referring_domain[4:]
        except:
            skipped += 1
            continue
        
        if not referring_domain:
            skipped += 1
            continue
        
        # Extract metrics
        dr_str = find_col(row, ['Domain rating', 'Domain Rating', 'DR', 'Source DR'])
        traffic_str = find_col(row, ['Domain traffic', 'Domain Traffic', 'Traffic', 'Organic Traffic'])
        anchor = find_col(row, ['Anchor', 'Anchor Text', 'Link Anchor'])
        dofollow_str = find_col(row, ['Nofollow', 'Dofollow', 'Follow', 'Type', 'Link Type'])
        
        # Parse values
        try:
            dr = float(dr_str) if dr_str and dr_str.strip() else None
        except:
            dr = None
        
        try:
            # Handle formatted numbers like "1,234,567"
            traffic = int(str(traffic_str).replace(',', '').replace(' ', '')) if traffic_str and traffic_str.strip() else None
        except:
            traffic = None
        
        is_dofollow = True
        if dofollow_str:
            dofollow_lower = str(dofollow_str).lower().strip()
            # Ahrefs "Nofollow" column: "true" = nofollow, "false" = dofollow
            is_dofollow = dofollow_lower not in ['true', 'yes', '1', 'nofollow']
        
        # Root domain dedup: blog.x.com matches x.com
        root_domain = extract_root_domain(referring_domain)

        # Find existing by exact match or root domain match
        domain = db.query(Domain).filter(Domain.domain == referring_domain).first()
        if not domain:
            # Check if root domain exists under a different subdomain
            all_domains = db.query(Domain).filter(Domain.deleted_at.is_(None)).all()
            for existing_d in all_domains:
                if extract_root_domain(existing_d.domain) == root_domain:
                    domain = existing_d
                    break
        if not domain:
            domain = Domain(
                domain=referring_domain,
                is_competitor=False,
                domain_rating=dr,
                organic_traffic=traffic,
            )
            db.add(domain)
            db.flush()
            added_domains.append({
                "domain": referring_domain,
                "traffic": traffic,
                "dr": dr,
            })
        else:
            # Update metrics if we have better data
            if traffic and (not domain.organic_traffic or traffic > domain.organic_traffic):
                domain.organic_traffic = traffic
            if dr and not domain.domain_rating:
                domain.domain_rating = dr

        # Classify new AND existing domains once per import (overrides win,
        # cached fetched verdicts stay untouched); ambiguous ones queue for
        # the bounded homepage fetch pass with every anchor seen in this CSV
        if domain.id not in classified_ids:
            classified_ids.add(domain.id)
            anchors = [anchor] if anchor else []
            if adult_classifier.apply_import_verdict(domain, overrides, anchor_texts=anchors or None):
                fetch_candidates[domain.id] = [domain, anchors]
        elif domain.id in fetch_candidates and anchor:
            fetch_candidates[domain.id][1].append(anchor)


        # Check if backlink exists
        existing = db.query(Backlink).filter(
            Backlink.source_domain_id == domain.id,
            Backlink.target_domain == competitor_domain,
            Backlink.source_url == url_from,
        ).first()
        
        if existing:
            continue
        
        # Create backlink
        backlink = Backlink(
            source_domain_id=domain.id,
            source_url=url_from,
            target_domain=competitor_domain,
            anchor_text=anchor,
            is_dofollow=is_dofollow,
            domain_rating=dr,
            traffic=traffic,
        )
        db.add(backlink)
        added_backlinks.append(referring_domain)

    # Bounded homepage fallback for domains signals couldn't decide
    adult_scan = await adult_classifier.run_import_fetch_pass(
        [(d, anchors or None) for d, anchors in fetch_candidates.values()]
    )
    db.commit()

    return {
        "success": True,
        "competitor": competitor_domain,
        "file": file.filename,
        "domains_added": len(added_domains),
        "backlinks_added": len(added_backlinks),
        "skipped": skipped,
        "adult_scan": adult_scan,
        "domains": sorted(added_domains, key=lambda x: x.get('traffic') or 0, reverse=True)[:20],
    }


@router.post("/domains-csv")
async def import_domains_csv(
    file: UploadFile = File(...),
    min_traffic: Optional[int] = Form(None),
    max_traffic: Optional[int] = Form(None),
    min_dr: Optional[int] = Form(None),
    max_dr: Optional[int] = Form(None),
    skip_non_adult: Optional[bool] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Import domains from CSV. Handles multiple formats:
    - Simple CSV with 'domain' column
    - Ahrefs exports with 'Referring page URL' or 'Target' columns
    - Tab or comma delimited

    Optional columns: dr/DR/Domain Rating, traffic/Traffic/Domain Traffic

    Every domain in the CSV — new or already stored without a fetched
    verdict — is classified via the shared adult classifier: signal scoring
    first, then one bounded homepage fetch for the domains signals couldn't
    decide (capped per import, no AI). With skip_non_adult, confirmed
    non-adult domains are filtered out; adult AND still-unknown domains are
    imported (ambiguous domains that may be adult are never silently
    dropped — they stay `unknown` until a later import or on-demand
    classification resolves them).
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    content = await file.read()
    
    # Try different encodings
    text = None
    for encoding in ['utf-8-sig', 'utf-16', 'utf-16-le', 'latin-1']:
        try:
            text = content.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    
    if text is None:
        raise HTTPException(status_code=400, detail="Could not decode CSV — unsupported encoding")
    
    # Detect delimiter
    first_line = text.split('\n')[0] if text else ''
    delimiter = '\t' if '\t' in first_line else ','
    
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    fieldnames = reader.fieldnames or []
    
    def find_col(row: dict, options: list) -> Optional[str]:
        for opt in options:
            for key in row.keys():
                if opt.lower() in key.lower():
                    val = row[key]
                    if val and str(val).strip():
                        return str(val).strip()
        return None
    
    added = []
    skipped = 0
    filtered_out = 0

    overrides = adult_classifier.load_adult_overrides(db)
    fetch_candidates: list[tuple[Domain, Optional[list[str]]]] = []
    # names of domains created by THIS import — only these may be dropped
    # if the fetch pass confirms them non-adult under skip_non_adult
    new_domain_names: set[str] = set()

    from urllib.parse import urlparse
    
    for row in reader:
        # Try to extract domain from various column patterns
        domain_name = find_col(row, ['domain', 'Domain', 'Target']) 
        
        if not domain_name:
            # Try extracting from a URL column (Ahrefs style)
            url_val = find_col(row, ['Referring page URL', 'URL', 'Source URL', 'Page URL', 'Referring Page'])
            if url_val:
                try:
                    domain_name = urlparse(url_val).netloc.lower()
                except:
                    pass
        
        if not domain_name:
            # Last resort: first column value
            vals = [v for v in row.values() if v and str(v).strip()]
            if vals:
                domain_name = str(vals[0]).strip()
        
        if not domain_name:
            skipped += 1
            continue
        
        domain_name = domain_name.strip().lower()
        if domain_name.startswith('http'):
            try:
                domain_name = urlparse(domain_name).netloc
            except:
                pass
        if domain_name.startswith('www.'):
            domain_name = domain_name[4:]
        
        # Skip invalid domains
        if '.' not in domain_name or ' ' in domain_name:
            skipped += 1
            continue
        
        # Check if exists
        existing = db.query(Domain).filter(Domain.domain == domain_name).first()
        if existing:
            # Update metrics if we have better data
            dr_val = find_col(row, ['dr', 'DR', 'Domain Rating', 'Domain rating'])
            traffic_val = find_col(row, ['traffic', 'Traffic', 'Domain Traffic', 'Organic Traffic'])
            updated = False
            if dr_val:
                try:
                    dr = float(dr_val)
                    if not existing.domain_rating or dr > existing.domain_rating:
                        existing.domain_rating = dr
                        updated = True
                except:
                    pass
            if traffic_val:
                try:
                    traffic = int(str(traffic_val).replace(',', '').replace(' ', ''))
                    if not existing.organic_traffic or traffic > existing.organic_traffic:
                        existing.organic_traffic = traffic
                        updated = True
                except:
                    pass
            # Existing rows still get classifier/override updates: old
            # blind-default rows without a fetched verdict, or rows whose
            # root gained a manual override since creation
            if adult_classifier.apply_import_verdict(existing, overrides):
                fetch_candidates.append((existing, None))
            skipped += 1
            continue
        
        # Parse optional fields
        dr = None
        traffic = None
        
        dr_val = find_col(row, ['dr', 'DR', 'Domain Rating', 'Domain rating', 'Source DR'])
        if dr_val:
            try:
                dr = float(dr_val)
            except:
                pass
        
        traffic_val = find_col(row, ['traffic', 'Traffic', 'Domain Traffic', 'Organic Traffic'])
        if traffic_val:
            try:
                traffic = int(str(traffic_val).replace(',', '').replace(' ', ''))
            except:
                pass
        
        # Apply filters
        if min_traffic is not None and (traffic is None or traffic < min_traffic):
            filtered_out += 1
            continue
        if max_traffic is not None and (traffic is not None and traffic > max_traffic):
            filtered_out += 1
            continue
        if min_dr is not None and (dr is None or dr < min_dr):
            filtered_out += 1
            continue
        if max_dr is not None and (dr is not None and dr > max_dr):
            filtered_out += 1
            continue
        
        # Phase-1 verdict (override, else signals — no HTTP yet)
        verdict = adult_classifier.classify_new_domain_for_import(domain_name, overrides=overrides)

        # Adult-only filter: drop confirmed non-adult; keep adult AND unknown
        # (ambiguous domains may be adult — never silently drop them here;
        # the fetch pass below gets one chance to resolve them)
        if skip_non_adult and verdict["domain_niche"] == adult_classifier.NICHE_NON_ADULT:
            filtered_out += 1
            continue

        is_competitor = False
        comp_val = find_col(row, ['is_competitor', 'competitor'])
        if comp_val:
            is_competitor = comp_val.lower() in ['true', '1', 'yes', 'y']

        domain = Domain(
            domain=domain_name,
            is_competitor=is_competitor,
            domain_rating=dr,
            organic_traffic=traffic,
        )
        adult_classifier.apply_verdict_to_domain(domain, verdict)
        db.add(domain)
        added.append(domain_name)
        if verdict["domain_niche"] == adult_classifier.NICHE_UNKNOWN:
            fetch_candidates.append((domain, None))
            new_domain_names.add(domain_name)

    # Bounded homepage fallback for domains signals couldn't decide
    db.flush()
    adult_scan = await adult_classifier.run_import_fetch_pass(fetch_candidates)

    # Domains this import created that the fetch confirmed non-adult are
    # dropped after all; pre-existing rows are never deleted by a filter
    if skip_non_adult:
        for domain_obj, _ in fetch_candidates:
            if (
                domain_obj.domain in new_domain_names
                and domain_obj.domain_niche == adult_classifier.NICHE_NON_ADULT
            ):
                new_domain_names.discard(domain_obj.domain)
                db.delete(domain_obj)
                added.remove(domain_obj.domain)
                filtered_out += 1

    db.commit()

    return {
        "success": True,
        "added": len(added),
        "skipped": skipped,
        "filtered_out": filtered_out,
        "total_rows": len(added) + skipped + filtered_out,
        "adult_scan": adult_scan,
        "domains": added[:50],
    }
