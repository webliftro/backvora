"""
Link Prices API router - manage link type pricing per domain.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import LinkPrice, Domain

router = APIRouter()


# ============ Schemas ============

class LinkPriceCreate(BaseModel):
    domain_id: str
    link_type: str = Field(..., min_length=1, max_length=100)
    price: Optional[float] = None
    currency: str = "USD"
    duration_months: Optional[int] = Field(None, ge=1, le=12)
    is_permanent: bool = False
    notes: Optional[str] = None


class LinkPriceUpdate(BaseModel):
    link_type: Optional[str] = Field(None, min_length=1, max_length=100)
    price: Optional[float] = None
    currency: Optional[str] = None
    duration_months: Optional[int] = Field(None, ge=1, le=12)
    is_permanent: Optional[bool] = None
    notes: Optional[str] = None


# ============ Endpoints ============

@router.get("/domain/{domain_id}")
async def list_link_prices(
    domain_id: str,
    db: Session = Depends(get_db),
):
    """Get all link prices for a domain."""
    prices = db.query(LinkPrice).filter(
        LinkPrice.domain_id == domain_id,
        LinkPrice.deleted_at.is_(None),
    ).all()
    
    return {
        "items": [
            {
                "id": p.id,
                "domain_id": p.domain_id,
                "link_type": p.link_type,
                "price": p.price,
                "currency": p.currency,
                "duration_months": p.duration_months,
                "is_permanent": p.is_permanent,
                "notes": p.notes,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in prices
        ],
        "total": len(prices),
    }


@router.post("")
async def create_link_price(
    data: LinkPriceCreate,
    db: Session = Depends(get_db),
):
    """Add a link price for a domain."""
    # Verify domain exists
    domain = db.query(Domain).filter(Domain.id == data.domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    
    # If permanent, clear duration
    duration = None if data.is_permanent else data.duration_months
    
    price = LinkPrice(
        domain_id=data.domain_id,
        link_type=data.link_type,
        price=data.price,
        currency=data.currency,
        duration_months=duration,
        is_permanent=data.is_permanent,
        notes=data.notes,
    )
    db.add(price)
    db.commit()
    db.refresh(price)
    
    return {
        "success": True,
        "id": price.id,
        "link_type": price.link_type,
        "price": price.price,
        "currency": price.currency,
        "duration_months": price.duration_months,
        "is_permanent": price.is_permanent,
    }


@router.put("/{price_id}")
async def update_link_price(
    price_id: str,
    data: LinkPriceUpdate,
    db: Session = Depends(get_db),
):
    """Update a link price."""
    price = db.query(LinkPrice).filter(
        LinkPrice.id == price_id,
        LinkPrice.deleted_at.is_(None),
    ).first()
    if not price:
        raise HTTPException(status_code=404, detail="Link price not found")
    
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(price, key, value)
    
    # If toggling permanent, clear duration
    if price.is_permanent:
        price.duration_months = None
    
    db.commit()
    db.refresh(price)
    
    return {"success": True, "id": price.id}


@router.delete("/{price_id}")
async def delete_link_price(
    price_id: str,
    db: Session = Depends(get_db),
):
    """Delete a link price."""
    price = db.query(LinkPrice).filter(
        LinkPrice.id == price_id,
        LinkPrice.deleted_at.is_(None),
    ).first()
    if not price:
        raise HTTPException(status_code=404, detail="Link price not found")
    
    from datetime import datetime
    price.deleted_at = datetime.utcnow()
    db.commit()
    
    return {"success": True}


# ============ Link Type Presets ============

@router.get("/types/list")
async def list_link_types(
    db: Session = Depends(get_db),
):
    """Get all available link types (presets + used)."""
    import sqlite3
    from ..config import settings
    
    # Get presets from raw table (not in ORM)
    db_path = settings.database_url.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    presets = set()
    try:
        c.execute("SELECT name FROM link_type_presets ORDER BY name")
        presets = set(r[0] for r in c.fetchall())
    except Exception:
        pass
    
    # Get types actually in use
    used = set()
    results = db.query(LinkPrice.link_type).filter(
        LinkPrice.deleted_at.is_(None)
    ).distinct().all()
    for r in results:
        if r[0]:
            used.add(r[0])
    
    all_types = sorted(presets | used)
    conn.close()
    
    return {"types": all_types, "presets": list(presets)}


@router.post("/types/add")
async def add_link_type(
    name: str,
):
    """Add a new link type preset."""
    import sqlite3
    from ..config import settings
    
    db_path = settings.database_url.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    try:
        c.execute("INSERT INTO link_type_presets (name) VALUES (?)", (name.strip(),))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Link type already exists")
    
    conn.close()
    return {"success": True, "name": name.strip()}


@router.put("/types/rename")
async def rename_link_type(
    old_name: str,
    new_name: str,
    db: Session = Depends(get_db),
):
    """Rename a link type preset and update all existing link prices using it."""
    import sqlite3
    from ..config import settings
    
    old_name = old_name.strip()
    new_name = new_name.strip()
    
    if not new_name:
        raise HTTPException(status_code=400, detail="New name cannot be empty")
    
    db_path = settings.database_url.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Check old exists
    c.execute("SELECT id FROM link_type_presets WHERE name = ?", (old_name,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Link type not found")
    
    # Check new doesn't conflict
    c.execute("SELECT id FROM link_type_presets WHERE name = ? AND name != ?", (new_name, old_name))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="A link type with that name already exists")
    
    # Rename preset
    c.execute("UPDATE link_type_presets SET name = ? WHERE name = ?", (new_name, old_name))
    conn.commit()
    conn.close()
    
    # Update all link_prices using the old name
    updated = db.query(LinkPrice).filter(
        LinkPrice.link_type == old_name,
        LinkPrice.deleted_at.is_(None),
    ).update({"link_type": new_name})
    db.commit()
    
    return {"success": True, "old_name": old_name, "new_name": new_name, "prices_updated": updated}


@router.delete("/types/delete")
async def delete_link_type(
    name: str,
):
    """Delete a link type preset (doesn't remove existing prices using it)."""
    import sqlite3
    from ..config import settings
    
    db_path = settings.database_url.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("DELETE FROM link_type_presets WHERE name = ?", (name.strip(),))
    if c.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Link type not found")
    
    conn.commit()
    conn.close()
    return {"success": True}


# ============ Pricing Engine ============

class FairPriceRequest(BaseModel):
    domain_rating: int
    organic_traffic: int
    link_type: str = "Guest Post"
    asking_price: Optional[float] = None


@router.post("/fair-price")
def get_fair_price(req: FairPriceRequest, db: Session = Depends(get_db)):
    """Calculate fair price for a link placement based on existing data."""
    from ..services.pricing import calculate_fair_price, evaluate_asking_price

    if req.asking_price is not None:
        return evaluate_asking_price(
            db, req.domain_rating, req.organic_traffic, req.asking_price, req.link_type
        )
    return calculate_fair_price(db, req.domain_rating, req.organic_traffic, req.link_type)


@router.get("/evaluate/{domain_id}")
def evaluate_domain(domain_id: str, db: Session = Depends(get_db)):
    """Evaluate all link prices for a domain against fair market value."""
    from ..services.pricing import evaluate_domain_prices

    results = evaluate_domain_prices(db, domain_id)
    if not results:
        raise HTTPException(status_code=404, detail="Domain not found or no prices")
    return results
