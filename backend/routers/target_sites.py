"""Target Sites router - manage sites we're building links to."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import TargetSite, TargetURL, AnchorText, Order

router = APIRouter()


# --- Schemas ---

class SiteCreate(BaseModel):
    domain: str
    name: str
    brand_variations: Optional[str] = None  # comma-separated
    notes: Optional[str] = None
    anchor_brand_pct: int = 60
    anchor_generic_pct: int = 10
    anchor_topical_pct: int = 20
    anchor_exact_pct: int = 5
    anchor_url_pct: int = 5

class SiteUpdate(BaseModel):
    name: Optional[str] = None
    brand_variations: Optional[str] = None
    notes: Optional[str] = None
    anchor_brand_pct: Optional[int] = None
    anchor_generic_pct: Optional[int] = None
    anchor_topical_pct: Optional[int] = None
    anchor_exact_pct: Optional[int] = None
    anchor_url_pct: Optional[int] = None

class BulkURLInput(BaseModel):
    """Bulk add URLs + keywords. Format per entry: url | keyword1, keyword2, ..."""
    entries: list[str]  # raw lines like "https://camhours.com/girls | cam girls, live cam girls"
    site_name: Optional[str] = None  # brand name for auto-classification

class URLCreate(BaseModel):
    url: str
    description: Optional[str] = None
    priority: int = 1

class AnchorCreate(BaseModel):
    text: str
    anchor_type: str  # brand, topical, generic, exact, url

class AnchorUpdate(BaseModel):
    text: Optional[str] = None
    anchor_type: Optional[str] = None


# --- Auto-classification ---

GENERIC_ANCHORS = {
    "click here", "visit", "website", "learn more", "read more", "check it out",
    "here", "this site", "visit site", "go here", "see more", "view", "link",
    "visit website", "official site", "homepage", "site", "check out",
}

def classify_anchor(text: str, brand_name: str, site_domain: str, url: str, brand_variations: list[str] | None = None) -> str:
    """Auto-classify an anchor text."""
    t = text.strip().lower()
    brand = brand_name.lower()
    domain = site_domain.lower().replace("www.", "")
    
    # URL type
    if t.startswith("http") or t == domain or t == f"www.{domain}":
        return "url"
    
    # Brand type (contains brand name or any variation)
    brands = [brand] + [v.strip().lower() for v in (brand_variations or []) if v.strip()]
    if any(b and (t == b or b in t) for b in brands):
        return "brand"
    
    # Generic
    if t in GENERIC_ANCHORS:
        return "generic"
    
    # Exact match: if anchor exactly matches a meaningful part of the URL path
    from urllib.parse import urlparse
    try:
        path = urlparse(url).path.strip("/").replace("-", " ").replace("_", " ").lower()
        if path and t == path:
            return "exact"
    except:
        pass
    
    # Default to topical (keyword-rich)
    return "topical"


# --- Routes ---

@router.get("")
async def list_sites(db: Session = Depends(get_db)):
    sites = db.query(TargetSite).filter(TargetSite.deleted_at.is_(None)).all()
    items = []
    for s in sites:
        urls = db.query(TargetURL).filter(
            TargetURL.site_id == s.id, TargetURL.deleted_at.is_(None)
        ).all()
        
        total_anchors = 0
        total_used = 0
        for u in urls:
            anchors = db.query(AnchorText).filter(
                AnchorText.target_url_id == u.id, AnchorText.deleted_at.is_(None)
            ).all()
            total_anchors += len(anchors)
            total_used += sum(a.times_used for a in anchors)
        
        # Count orders pointing to this site's URLs
        order_count = db.query(Order).filter(
            Order.target_url.ilike(f"%{s.domain}%"),
        ).count()
        
        items.append({
            "id": s.id,
            "domain": s.domain,
            "name": s.name,
            "brand_variations": s.brand_variations,
            "notes": s.notes,
            "anchor_brand_pct": s.anchor_brand_pct,
            "anchor_generic_pct": s.anchor_generic_pct,
            "anchor_topical_pct": s.anchor_topical_pct,
            "anchor_exact_pct": s.anchor_exact_pct,
            "anchor_url_pct": s.anchor_url_pct,
            "url_count": len(urls),
            "anchor_count": total_anchors,
            "total_used": total_used,
            "order_count": order_count,
        })
    return {"items": items}


@router.post("")
async def create_site(data: SiteCreate, db: Session = Depends(get_db)):
    existing = db.query(TargetSite).filter(
        TargetSite.domain == data.domain, TargetSite.deleted_at.is_(None)
    ).first()
    if existing:
        raise HTTPException(400, "Site already exists")
    
    site = TargetSite(**data.model_dump())
    db.add(site)
    db.commit()
    db.refresh(site)
    return {"id": site.id, "domain": site.domain}


@router.get("/{site_id}")
async def get_site(site_id: str, db: Session = Depends(get_db)):
    site = db.query(TargetSite).filter(
        TargetSite.id == site_id, TargetSite.deleted_at.is_(None)
    ).first()
    if not site:
        raise HTTPException(404, "Site not found")
    
    urls = db.query(TargetURL).filter(
        TargetURL.site_id == site.id, TargetURL.deleted_at.is_(None)
    ).order_by(TargetURL.priority.desc()).all()
    
    url_items = []
    for u in urls:
        anchors = db.query(AnchorText).filter(
            AnchorText.target_url_id == u.id, AnchorText.deleted_at.is_(None)
        ).all()
        url_items.append({
            "id": u.id,
            "url": u.url,
            "description": u.description,
            "priority": u.priority,
            "anchors": [{
                "id": a.id,
                "text": a.text,
                "anchor_type": a.anchor_type,
                "times_used": a.times_used,
            } for a in anchors],
        })
    
    # Compute actual distribution from all anchors
    type_counts = {"brand": 0, "generic": 0, "topical": 0, "exact": 0, "url": 0}
    type_used = {"brand": 0, "generic": 0, "topical": 0, "exact": 0, "url": 0}
    for u in url_items:
        for a in u["anchors"]:
            t = a["anchor_type"]
            if t in type_counts:
                type_counts[t] += 1
                type_used[t] += a["times_used"]
    
    total_used = sum(type_used.values()) or 1
    actual_dist = {k: round(v / total_used * 100) for k, v in type_used.items()}
    
    return {
        "id": site.id,
        "domain": site.domain,
        "name": site.name,
        "brand_variations": site.brand_variations,
        "notes": site.notes,
        "anchor_brand_pct": site.anchor_brand_pct,
        "anchor_generic_pct": site.anchor_generic_pct,
        "anchor_topical_pct": site.anchor_topical_pct,
        "anchor_exact_pct": site.anchor_exact_pct,
        "anchor_url_pct": site.anchor_url_pct,
        "urls": url_items,
        "actual_distribution": actual_dist,
    }


@router.put("/{site_id}")
async def update_site(site_id: str, data: SiteUpdate, db: Session = Depends(get_db)):
    site = db.query(TargetSite).filter(
        TargetSite.id == site_id, TargetSite.deleted_at.is_(None)
    ).first()
    if not site:
        raise HTTPException(404, "Site not found")
    
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(site, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/{site_id}")
async def delete_site(site_id: str, db: Session = Depends(get_db)):
    site = db.query(TargetSite).filter(
        TargetSite.id == site_id, TargetSite.deleted_at.is_(None)
    ).first()
    if not site:
        raise HTTPException(404, "Site not found")
    from datetime import datetime
    site.deleted_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


# --- URL management ---

@router.post("/{site_id}/urls")
async def add_url(site_id: str, data: URLCreate, db: Session = Depends(get_db)):
    site = db.query(TargetSite).filter(
        TargetSite.id == site_id, TargetSite.deleted_at.is_(None)
    ).first()
    if not site:
        raise HTTPException(404, "Site not found")
    
    url = TargetURL(site_id=site.id, **data.model_dump())
    db.add(url)
    db.commit()
    db.refresh(url)
    return {"id": url.id}


@router.delete("/urls/{url_id}")
async def delete_url(url_id: str, db: Session = Depends(get_db)):
    url = db.query(TargetURL).filter(
        TargetURL.id == url_id, TargetURL.deleted_at.is_(None)
    ).first()
    if not url:
        raise HTTPException(404, "URL not found")
    from datetime import datetime
    url.deleted_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


# --- Anchor management ---

@router.post("/urls/{url_id}/anchors")
async def add_anchor(url_id: str, data: AnchorCreate, db: Session = Depends(get_db)):
    url = db.query(TargetURL).filter(
        TargetURL.id == url_id, TargetURL.deleted_at.is_(None)
    ).first()
    if not url:
        raise HTTPException(404, "URL not found")
    
    anchor = AnchorText(target_url_id=url.id, **data.model_dump())
    db.add(anchor)
    db.commit()
    db.refresh(anchor)
    return {"id": anchor.id}


@router.put("/anchors/{anchor_id}")
async def update_anchor(anchor_id: str, data: AnchorUpdate, db: Session = Depends(get_db)):
    anchor = db.query(AnchorText).filter(
        AnchorText.id == anchor_id, AnchorText.deleted_at.is_(None)
    ).first()
    if not anchor:
        raise HTTPException(404, "Anchor not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(anchor, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/anchors/{anchor_id}")
async def delete_anchor(anchor_id: str, db: Session = Depends(get_db)):
    anchor = db.query(AnchorText).filter(
        AnchorText.id == anchor_id, AnchorText.deleted_at.is_(None)
    ).first()
    if not anchor:
        raise HTTPException(404, "Anchor not found")
    from datetime import datetime
    anchor.deleted_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


# --- Bulk import ---

@router.post("/{site_id}/bulk-import")
async def bulk_import(site_id: str, data: BulkURLInput, db: Session = Depends(get_db)):
    """Bulk import URLs and keywords. Each line: url | kw1, kw2, kw3
    If no keywords provided, just creates the URL entry.
    Auto-classifies anchor types."""
    site = db.query(TargetSite).filter(
        TargetSite.id == site_id, TargetSite.deleted_at.is_(None)
    ).first()
    if not site:
        raise HTTPException(404, "Site not found")
    
    brand_name = data.site_name or site.name
    urls_created = 0
    anchors_created = 0
    
    for line in data.entries:
        line = line.strip()
        if not line:
            continue
        
        parts = line.split("|", 1)
        url_str = parts[0].strip()
        keywords = []
        if len(parts) > 1:
            keywords = [k.strip() for k in parts[1].split(",") if k.strip()]
        
        if not url_str:
            continue
        
        # Check if URL already exists
        existing_url = db.query(TargetURL).filter(
            TargetURL.site_id == site.id,
            TargetURL.url == url_str,
            TargetURL.deleted_at.is_(None),
        ).first()
        
        if existing_url:
            target_url = existing_url
        else:
            target_url = TargetURL(site_id=site.id, url=url_str)
            db.add(target_url)
            db.flush()
            urls_created += 1
        
        # Add keywords as anchors
        existing_anchors = {
            a.text.lower()
            for a in db.query(AnchorText).filter(
                AnchorText.target_url_id == target_url.id,
                AnchorText.deleted_at.is_(None),
            ).all()
        }
        
        for kw in keywords:
            if kw.lower() in existing_anchors:
                continue
            variations = [v.strip() for v in (site.brand_variations or "").split(",") if v.strip()]
            anchor_type = classify_anchor(kw, brand_name, site.domain, url_str, variations)
            anchor = AnchorText(
                target_url_id=target_url.id,
                text=kw,
                anchor_type=anchor_type,
            )
            db.add(anchor)
            anchors_created += 1
    
    db.commit()
    return {
        "urls_created": urls_created,
        "anchors_created": anchors_created,
    }


# --- Suggest next anchor ---

@router.get("/{site_id}/suggest-anchor")
async def suggest_anchor(site_id: str, db: Session = Depends(get_db)):
    """Suggest the best anchor text to use next based on distribution targets."""
    site = db.query(TargetSite).filter(
        TargetSite.id == site_id, TargetSite.deleted_at.is_(None)
    ).first()
    if not site:
        raise HTTPException(404, "Site not found")
    
    target_dist = {
        "brand": site.anchor_brand_pct,
        "generic": site.anchor_generic_pct,
        "topical": site.anchor_topical_pct,
        "exact": site.anchor_exact_pct,
        "url": site.anchor_url_pct,
    }
    
    # Get all anchors with usage
    urls = db.query(TargetURL).filter(
        TargetURL.site_id == site.id, TargetURL.deleted_at.is_(None)
    ).all()
    
    all_anchors = []
    type_used = {"brand": 0, "generic": 0, "topical": 0, "exact": 0, "url": 0}
    for u in urls:
        anchors = db.query(AnchorText).filter(
            AnchorText.target_url_id == u.id, AnchorText.deleted_at.is_(None)
        ).all()
        for a in anchors:
            all_anchors.append({"anchor": a, "url": u})
            if a.anchor_type in type_used:
                type_used[a.anchor_type] += a.times_used
    
    total = sum(type_used.values()) or 1
    actual_pct = {k: v / total * 100 for k, v in type_used.items()}
    
    # Find most underrepresented type
    gaps = {k: target_dist.get(k, 0) - actual_pct.get(k, 0) for k in target_dist}
    best_type = max(gaps, key=gaps.get)
    
    # Pick least-used anchor of that type
    candidates = [a for a in all_anchors if a["anchor"].anchor_type == best_type]
    if not candidates:
        # Fall back to any type
        candidates = all_anchors
    
    if not candidates:
        return {"suggestion": None}
    
    candidates.sort(key=lambda a: a["anchor"].times_used)
    pick = candidates[0]
    
    return {
        "suggestion": {
            "anchor_id": pick["anchor"].id,
            "text": pick["anchor"].text,
            "anchor_type": pick["anchor"].anchor_type,
            "target_url": pick["url"].url,
            "times_used": pick["anchor"].times_used,
        },
        "distribution": {
            "target": target_dist,
            "actual": {k: round(v, 1) for k, v in actual_pct.items()},
            "gaps": {k: round(v, 1) for k, v in gaps.items()},
        },
    }
