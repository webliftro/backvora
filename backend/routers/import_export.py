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
        def _extract_root(d):
            parts = d.lower().split(".")
            if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "edu", "gov", "ac"):
                return ".".join(parts[-3:])
            return ".".join(parts[-2:]) if len(parts) >= 2 else d
        
        root_domain = _extract_root(referring_domain)
        
        # Find existing by exact match or root domain match
        domain = db.query(Domain).filter(Domain.domain == referring_domain).first()
        if not domain:
            # Check if root domain exists under a different subdomain
            all_domains = db.query(Domain).filter(Domain.deleted_at.is_(None)).all()
            for existing_d in all_domains:
                if _extract_root(existing_d.domain) == root_domain:
                    domain = existing_d
                    break
        if not domain:
            domain = Domain(
                domain=referring_domain,
                is_competitor=False,
                is_adult=True,
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
    
    db.commit()
    
    return {
        "success": True,
        "competitor": competitor_domain,
        "file": file.filename,
        "domains_added": len(added_domains),
        "backlinks_added": len(added_backlinks),
        "skipped": skipped,
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
        
        # Adult keyword check on import (quick Tier 1 only — no HTTP fetches)
        if skip_non_adult:
            from ..services.adult_classifier import classify_domain_keyword
            is_adult_kw = classify_domain_keyword(domain_name)
            if is_adult_kw is not True:
                # Not obviously adult by domain name — skip
                filtered_out += 1
                continue
        
        is_competitor = False
        comp_val = find_col(row, ['is_competitor', 'competitor'])
        if comp_val:
            is_competitor = comp_val.lower() in ['true', '1', 'yes', 'y']
        
        domain = Domain(
            domain=domain_name,
            is_competitor=is_competitor,
            is_adult=True,
            domain_rating=dr,
            organic_traffic=traffic,
        )
        db.add(domain)
        added.append(domain_name)
    
    db.commit()
    
    return {
        "success": True,
        "added": len(added),
        "skipped": skipped,
        "filtered_out": filtered_out,
        "total_rows": len(added) + skipped + filtered_out,
        "domains": added[:50],
    }
