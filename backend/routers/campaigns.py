"""
Campaigns API router - Campaign management for link building.
"""

from typing import Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from ..database import get_db
from ..models import (
    Campaign, CampaignTarget, PublisherRules, Order, OrderLink, LinkCheck,
    Domain, Contact, LinkPrice, DomainPaymentMethod,
    TargetSite, TargetURL, AnchorText
)


router = APIRouter()


# ============ Campaigns CRUD ============

OPTIONAL_NUMBER_FIELDS = (
    "budget",
    "spent",
    "filter_traffic_min",
    "filter_traffic_max",
    "filter_dr_min",
    "filter_dr_max",
    "filter_price_min",
    "filter_price_max",
    "budget_total",
)


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _normalize_text_literal(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower()
    return value

@router.get("")
async def list_campaigns(db: Session = Depends(get_db)):
    """List all campaigns with stats."""
    campaigns = db.query(Campaign).filter(Campaign.deleted_at.is_(None)).all()
    
    campaign_ids = [c.id for c in campaigns]
    
    # Batch stats
    order_counts = dict(
        db.query(Order.campaign_id, func.count(Order.id))
        .filter(Order.campaign_id.in_(campaign_ids))
        .group_by(Order.campaign_id)
        .all()
    ) if campaign_ids else {}
    
    live_counts = dict(
        db.query(Order.campaign_id, func.count(Order.id))
        .filter(Order.campaign_id.in_(campaign_ids), Order.status.in_(['published', 'paid', 'live']))
        .group_by(Order.campaign_id)
        .all()
    ) if campaign_ids else {}

    # Calculate spent dynamically: sum of prices for orders where payment was actually made
    from sqlalchemy import or_
    spent_rows = (
        db.query(Order.campaign_id, func.sum(Order.price))
        .filter(
            Order.campaign_id.in_(campaign_ids),
            or_(Order.paid_at.isnot(None), Order.payment_sent_at.isnot(None)),
        )
        .group_by(Order.campaign_id)
        .all()
    ) if campaign_ids else []
    spent_map = {row[0]: float(row[1] or 0) for row in spent_rows}

    items = []
    for c in campaigns:
        items.append({
            "id": c.id,
            "name": c.name,
            "target_site": c.target_site,
            "status": c.status,
            "budget": c.budget,
            "spent": spent_map.get(c.id, 0.0),
            "notes": c.notes,
            "anchor_brand_pct": c.anchor_brand_pct,
            "anchor_generic_pct": c.anchor_generic_pct,
            "anchor_topical_pct": c.anchor_topical_pct,
            "anchor_exact_pct": c.anchor_exact_pct,
            "total_orders": order_counts.get(c.id, 0),
            "links_live": live_counts.get(c.id, 0),
            "mode": c.mode,
            "velocity_count": c.velocity_count,
            "velocity_period_days": c.velocity_period_days,
            "approval_mode": c.approval_mode,
            "consecutive_approvals": c.consecutive_approvals,
            "approval_threshold": c.approval_threshold,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        })
    
    return {"items": items}


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str, db: Session = Depends(get_db)):
    """Get campaign detail with targets and orders."""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.deleted_at.is_(None)
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Get targets
    targets = db.query(CampaignTarget).filter(
        CampaignTarget.campaign_id == campaign_id,
        CampaignTarget.deleted_at.is_(None)
    ).all()
    
    # Get orders with domain info
    orders = db.query(Order, Domain.domain, Contact.email).outerjoin(
        Domain, Order.domain_id == Domain.id
    ).outerjoin(
        Contact, Order.contact_id == Contact.id
    ).filter(Order.campaign_id == campaign_id).all()
    
    order_items = []
    for order, domain_name, contact_email in orders:
        order_items.append({
            "id": order.id,
            "domain_id": order.domain_id,
            "domain": domain_name,
            "contact_email": contact_email,
            "link_type": order.link_type,
            "price": order.price,
            "currency": order.currency,
            "target_url": order.target_url,
            "anchor_text": order.anchor_text,
            "anchor_type": order.anchor_type,
            "article_content": order.article_content,
            "article_topic": order.article_topic,
            "nofollow_target": order.nofollow_target,
            "nofollow_resources": order.nofollow_resources,
            "skip_resource_links": order.skip_resource_links,
            "max_words": order.max_words,
            "resource_links_count": order.resource_links_count,
            "brand_mentions_scope": order.brand_mentions_scope,
            "brand_mentions_brands": order.brand_mentions_brands,
            "brand_mentions_in_title": order.brand_mentions_in_title,
            "brand_mentions_body_count": order.brand_mentions_body_count,
            "live_url": order.live_url,
            "status": order.status,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "payment_sent_at": order.payment_sent_at.isoformat() if order.payment_sent_at else None,
            "live_at": order.live_at.isoformat() if order.live_at else None,
            "last_checked_at": order.last_checked_at.isoformat() if order.last_checked_at else None,
            "last_check_status": order.last_check_status,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "links": [{
                "id": link.id,
                "target_url": link.target_url,
                "anchor_text": link.anchor_text,
                "anchor_type": link.anchor_type,
                "anchor_text_id": link.anchor_text_id,
                "slot": link.slot,
            } for link in (order.links or [])],
        })

    # Calculate spent dynamically: sum of prices for orders where payment was actually made
    from sqlalchemy import or_ as _or
    spent_result = (
        db.query(func.sum(Order.price))
        .filter(
            Order.campaign_id == campaign_id,
            _or(Order.paid_at.isnot(None), Order.payment_sent_at.isnot(None)),
        )
        .scalar()
    )
    dynamic_spent = float(spent_result or 0)

    return {
        "id": campaign.id,
        "name": campaign.name,
        "target_site": campaign.target_site, "target_site_id": campaign.target_site_id,
        "status": campaign.status,
        "budget": campaign.budget,
        "spent": dynamic_spent,
        "notes": campaign.notes,
        "anchor_brand_pct": campaign.anchor_brand_pct,
        "anchor_generic_pct": campaign.anchor_generic_pct,
        "anchor_topical_pct": campaign.anchor_topical_pct,
        "anchor_exact_pct": campaign.anchor_exact_pct,
        "mode": campaign.mode,
        "filter_traffic_min": campaign.filter_traffic_min,
        "filter_traffic_max": campaign.filter_traffic_max,
        "filter_dr_min": campaign.filter_dr_min,
        "filter_dr_max": campaign.filter_dr_max,
        "filter_price_min": campaign.filter_price_min,
        "filter_price_max": campaign.filter_price_max,
        "filter_niche_tags": campaign.filter_niche_tags,
        "filter_link_type": campaign.filter_link_type,
        "velocity_count": campaign.velocity_count,
        "velocity_period_days": campaign.velocity_period_days,
        "budget_total": campaign.budget_total,
        "budget_spent": campaign.budget_spent,
        "last_order_sent_at": campaign.last_order_sent_at.isoformat() if campaign.last_order_sent_at else None,
        "approval_mode": campaign.approval_mode,
        "consecutive_approvals": campaign.consecutive_approvals,
        "approval_threshold": campaign.approval_threshold,
        "schedule_enabled": campaign.schedule_enabled,
        "schedule_interval_hours": campaign.schedule_interval_hours,
        "targets": [
            {
                "id": t.id,
                "url": t.url,
                "brand_name": t.brand_name,
                "description": t.description,
                "priority": t.priority,
            }
            for t in targets
        ],
        "orders": order_items,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None,
    }


class CampaignCreate(BaseModel):
    name: str
    target_site: str = ""
    target_site_id: Optional[str] = None
    status: str = "paused"
    budget: Optional[float] = None
    notes: Optional[str] = None
    anchor_brand_pct: int = 60
    anchor_generic_pct: int = 20
    anchor_topical_pct: int = 15
    anchor_exact_pct: int = 5
    mode: str = "manual"
    filter_traffic_min: Optional[int] = None
    filter_traffic_max: Optional[int] = None
    filter_dr_min: Optional[int] = None
    filter_dr_max: Optional[int] = None
    filter_price_min: Optional[float] = None
    filter_price_max: Optional[float] = None
    filter_niche_tags: Optional[str] = None
    filter_link_type: Optional[str] = None
    velocity_count: int = 1
    velocity_period_days: int = 7
    budget_total: Optional[float] = None
    schedule_enabled: bool = False
    schedule_interval_hours: int = 6

    @field_validator(*OPTIONAL_NUMBER_FIELDS, mode="before", check_fields=False)
    @classmethod
    def normalize_blank_numbers(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("schedule_interval_hours", mode="before")
    @classmethod
    def normalize_blank_schedule_interval(cls, value: Any) -> Any:
        return 6 if isinstance(value, str) and value.strip() == "" else value

    @field_validator("status", "mode", mode="before")
    @classmethod
    def normalize_status_and_mode(cls, value: Any) -> Any:
        return _normalize_text_literal(value)

@router.post("")
async def create_campaign(data: CampaignCreate, db: Session = Depends(get_db)):
    """Create a new campaign."""
    # If target_site_id provided, auto-fill target_site domain and pull distribution
    target_site_domain = data.target_site
    anchor_pcts = {
        "anchor_brand_pct": data.anchor_brand_pct,
        "anchor_generic_pct": data.anchor_generic_pct,
        "anchor_topical_pct": data.anchor_topical_pct,
        "anchor_exact_pct": data.anchor_exact_pct,
    }
    if data.target_site_id:
        ts = db.query(TargetSite).filter(TargetSite.id == data.target_site_id).first()
        if ts:
            target_site_domain = ts.domain
            anchor_pcts = {
                "anchor_brand_pct": ts.anchor_brand_pct,
                "anchor_generic_pct": ts.anchor_generic_pct,
                "anchor_topical_pct": ts.anchor_topical_pct,
                "anchor_exact_pct": ts.anchor_exact_pct,
            }
    
    campaign = Campaign(
        name=data.name,
        target_site=target_site_domain,
        target_site_id=data.target_site_id,
        status=data.status,
        budget=data.budget,
        notes=data.notes,
        mode=data.mode,
        filter_traffic_min=data.filter_traffic_min,
        filter_traffic_max=data.filter_traffic_max,
        filter_dr_min=data.filter_dr_min,
        filter_dr_max=data.filter_dr_max,
        filter_price_min=data.filter_price_min,
        filter_price_max=data.filter_price_max,
        filter_niche_tags=data.filter_niche_tags,
        filter_link_type=data.filter_link_type,
        velocity_count=data.velocity_count,
        velocity_period_days=data.velocity_period_days,
        budget_total=data.budget_total,
        schedule_enabled=data.schedule_enabled,
        schedule_interval_hours=data.schedule_interval_hours,
        **anchor_pcts,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    
    return {
        "id": campaign.id,
        "name": campaign.name,
        "target_site": campaign.target_site, "target_site_id": campaign.target_site_id,
        "status": campaign.status,
        "budget": campaign.budget,
        "spent": campaign.spent,
        "notes": campaign.notes,
        "anchor_brand_pct": campaign.anchor_brand_pct,
        "anchor_generic_pct": campaign.anchor_generic_pct,
        "anchor_topical_pct": campaign.anchor_topical_pct,
        "anchor_exact_pct": campaign.anchor_exact_pct,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
    }


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    target_site: Optional[str] = None
    target_site_id: Optional[str] = None
    status: Optional[str] = None
    budget: Optional[float] = None
    spent: Optional[float] = None
    notes: Optional[str] = None
    anchor_brand_pct: Optional[int] = None
    anchor_generic_pct: Optional[int] = None
    anchor_topical_pct: Optional[int] = None
    anchor_exact_pct: Optional[int] = None
    mode: Optional[str] = None
    filter_traffic_min: Optional[int] = None
    filter_traffic_max: Optional[int] = None
    filter_dr_min: Optional[int] = None
    filter_dr_max: Optional[int] = None
    filter_price_min: Optional[float] = None
    filter_price_max: Optional[float] = None
    filter_niche_tags: Optional[str] = None
    filter_link_type: Optional[str] = None
    velocity_count: Optional[int] = None
    velocity_period_days: Optional[int] = None
    budget_total: Optional[float] = None
    schedule_enabled: Optional[bool] = None
    schedule_interval_hours: Optional[int] = None

    @field_validator(*OPTIONAL_NUMBER_FIELDS, "schedule_interval_hours", mode="before", check_fields=False)
    @classmethod
    def normalize_blank_numbers(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("status", "mode", mode="before")
    @classmethod
    def normalize_status_and_mode(cls, value: Any) -> Any:
        return _normalize_text_literal(value)

@router.put("/{campaign_id}")
async def update_campaign(campaign_id: str, data: CampaignUpdate, db: Session = Depends(get_db)):
    """Update campaign."""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.deleted_at.is_(None)
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    updates = data.model_dump(exclude_unset=True)
    if data.target_site_id:
        target_site = db.query(TargetSite).filter(TargetSite.id == data.target_site_id).first()
        if not target_site:
            raise HTTPException(status_code=404, detail="Target site not found")
        updates.setdefault("target_site", target_site.domain)
        updates.setdefault("anchor_brand_pct", target_site.anchor_brand_pct)
        updates.setdefault("anchor_generic_pct", target_site.anchor_generic_pct)
        updates.setdefault("anchor_topical_pct", target_site.anchor_topical_pct)
        updates.setdefault("anchor_exact_pct", target_site.anchor_exact_pct)

    for field, value in updates.items():
        setattr(campaign, field, value)
    
    db.commit()
    db.refresh(campaign)
    
    # Update scheduler based on new state
    from ..services.scheduler import add_campaign_job, remove_campaign_job
    if campaign.mode == "auto" and campaign.schedule_enabled and campaign.status == "active":
        add_campaign_job(campaign.id, campaign.schedule_interval_hours or 6)
    else:
        remove_campaign_job(campaign.id)
    
    return {"success": True, "id": campaign.id}


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: str, db: Session = Depends(get_db)):
    """Delete campaign (soft delete)."""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.deleted_at.is_(None)
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    campaign.deleted_at = datetime.utcnow()
    db.commit()
    
    return {"success": True}


# ============ Campaign Targets ============

class TargetCreate(BaseModel):
    url: str
    brand_name: str
    description: Optional[str] = None
    priority: int = 1

@router.post("/{campaign_id}/targets")
async def create_target(campaign_id: str, data: TargetCreate, db: Session = Depends(get_db)):
    """Add a target URL to campaign."""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.deleted_at.is_(None)
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    target = CampaignTarget(
        campaign_id=campaign_id,
        url=data.url,
        brand_name=data.brand_name,
        description=data.description,
        priority=data.priority,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    
    return {
        "id": target.id,
        "url": target.url,
        "brand_name": target.brand_name,
        "description": target.description,
        "priority": target.priority,
    }


class TargetUpdate(BaseModel):
    url: Optional[str] = None
    brand_name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None

@router.put("/targets/{target_id}")
async def update_target(target_id: str, data: TargetUpdate, db: Session = Depends(get_db)):
    """Update campaign target."""
    target = db.query(CampaignTarget).filter(
        CampaignTarget.id == target_id,
        CampaignTarget.deleted_at.is_(None)
    ).first()
    
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(target, field, value)
    
    db.commit()
    
    return {"success": True}


@router.delete("/targets/{target_id}")
async def delete_target(target_id: str, db: Session = Depends(get_db)):
    """Delete campaign target."""
    target = db.query(CampaignTarget).filter(
        CampaignTarget.id == target_id,
        CampaignTarget.deleted_at.is_(None)
    ).first()
    
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    
    target.deleted_at = datetime.utcnow()
    db.commit()
    
    return {"success": True}


# ============ Publisher Rules ============

@router.get("/publisher-rules/{domain_id}")
async def get_publisher_rules(domain_id: str, db: Session = Depends(get_db)):
    """Get publisher rules for a domain."""
    rules = db.query(PublisherRules).filter(
        PublisherRules.domain_id == domain_id,
        PublisherRules.deleted_at.is_(None)
    ).first()
    
    if not rules:
        return {"exists": False}
    
    return {
        "exists": True,
        "id": rules.id,
        "max_urls": rules.max_urls,
        "cross_domain": rules.cross_domain,
        "we_write": rules.we_write,
        "min_words": rules.min_words,
        "max_words": rules.max_words,
        "link_attribute": rules.link_attribute,
        "max_images": rules.max_images,
        "image_count": rules.image_count,
        "resource_links_count": rules.resource_links_count,
        "skip_resource_links": rules.skip_resource_links,
        "brand_mentions_scope": rules.brand_mentions_scope,
        "brand_mentions_brands": rules.brand_mentions_brands,
        "brand_mentions_in_title": rules.brand_mentions_in_title,
        "brand_mentions_body_count": rules.brand_mentions_body_count,
        "content_guidelines": rules.content_guidelines,
        "placement_notes": rules.placement_notes,
    }


class PublisherRulesCreate(BaseModel):
    max_urls: Optional[int] = None
    cross_domain: Optional[bool] = None
    we_write: Optional[bool] = None
    min_words: Optional[int] = None
    max_words: Optional[int] = None
    link_attribute: Optional[str] = None  # dofollow, nofollow, sponsored
    max_images: Optional[int] = None
    image_count: Optional[int] = None
    resource_links_count: Optional[int] = None
    skip_resource_links: Optional[bool] = None
    brand_mentions_scope: Optional[str] = None
    brand_mentions_brands: Optional[str] = None
    brand_mentions_in_title: Optional[bool] = None
    brand_mentions_body_count: Optional[int] = None
    content_guidelines: Optional[str] = None
    placement_notes: Optional[str] = None

@router.post("/publisher-rules/{domain_id}")
async def create_publisher_rules(domain_id: str, data: PublisherRulesCreate, db: Session = Depends(get_db)):
    """Create or update publisher rules for a domain."""
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    
    rules = db.query(PublisherRules).filter(PublisherRules.domain_id == domain_id).first()
    
    if rules:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(rules, field, value)
        rules.deleted_at = None
    else:
        rules = PublisherRules(domain_id=domain_id, **data.model_dump(exclude_unset=True))
        db.add(rules)
    
    db.commit()
    db.refresh(rules)
    
    return {
        "id": rules.id,
        "max_urls": rules.max_urls,
        "cross_domain": rules.cross_domain,
        "we_write": rules.we_write,
        "min_words": rules.min_words,
        "max_words": rules.max_words,
        "link_attribute": rules.link_attribute,
        "max_images": rules.max_images,
        "image_count": rules.image_count,
        "resource_links_count": rules.resource_links_count,
        "skip_resource_links": rules.skip_resource_links,
        "brand_mentions_scope": rules.brand_mentions_scope,
        "brand_mentions_brands": rules.brand_mentions_brands,
        "brand_mentions_in_title": rules.brand_mentions_in_title,
        "brand_mentions_body_count": rules.brand_mentions_body_count,
        "content_guidelines": rules.content_guidelines,
        "placement_notes": rules.placement_notes,
    }


@router.delete("/publisher-rules/{domain_id}")
async def delete_publisher_rules(domain_id: str, db: Session = Depends(get_db)):
    """Delete publisher rules."""
    rules = db.query(PublisherRules).filter(
        PublisherRules.domain_id == domain_id
    ).first()
    
    if not rules:
        raise HTTPException(status_code=404, detail="Rules not found")
    
    rules.deleted_at = datetime.utcnow()
    db.commit()
    
    return {"success": True}


@router.post("/publisher-rules/{domain_id}/grab")
async def grab_publisher_rules(domain_id: str, db: Session = Depends(get_db)):
    """Extract publisher rules from email conversations using AI."""
    from ..services.reply_parser import call_sonnet
    from ..models import SentEmail
    
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(404, "Domain not found")
    
    # Gather all email conversations for this domain
    # 1. Emails we sent
    sent = db.query(SentEmail).filter(SentEmail.domain_id == domain_id).order_by(SentEmail.sent_at).all()
    
    # 2. Received replies (scan IMAP for emails from domain's contact)
    import imaplib, email as email_lib
    from email.header import decode_header
    from ..config import settings
    
    email_threads = []
    for s in sent:
        email_threads.append(f"[SENT to {s.to_email}] Subject: {s.subject}\n{s.body[:1500]}")
    
    # Fetch replies from IMAP
    contact_emails = set()
    if domain.email:
        contact_emails.add(domain.email)
    contacts = db.query(Contact).filter(Contact.domain_id == domain_id, Contact.deleted_at.is_(None)).all()
    for c in contacts:
        if c.email:
            contact_emails.add(c.email)
    
    # Always search IMAP by domain name (broader search)
    try:
        mail = imaplib.IMAP4_SSL(settings.imap_host)
        mail.login(settings.email_account, settings.email_password)
        mail.select("INBOX", readonly=True)
        
        # Search strategies: by contact emails, by domain in FROM, and by domain in subject
        search_queries = []
        for addr in contact_emails:
            search_queries.append(f'(FROM "{addr}")')
        # Search by domain name in FROM (catches any email from that domain)
        email_domain = domain.domain.replace("www.", "")
        search_queries.append(f'(FROM "@{email_domain}")')
        # Search by domain name in subject
        search_queries.append(f'(SUBJECT "{email_domain}")')
        # Also search SENT folder for our outgoing emails
        seen_nums = set()
        
        for query in search_queries:
            try:
                _, msg_ids = mail.search(None, query)
                for num in (msg_ids[0].split() if msg_ids[0] else [])[-5:]:
                    if num in seen_nums:
                        continue
                    seen_nums.add(num)
                    _, msg_data = mail.fetch(num, "(RFC822)")
                    if msg_data[0] is None:
                        continue
                    msg = email_lib.message_from_bytes(msg_data[0][1])
                    from_addr = msg.get("From", "")
                    subject = ""
                    raw_subj = msg.get("Subject", "")
                    if raw_subj:
                        parts = decode_header(raw_subj)
                        subject = " ".join(
                            p.decode(enc or "utf-8") if isinstance(p, bytes) else p
                            for p, enc in parts
                        )
                    body = ""
                    html_body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            ct = part.get_content_type()
                            payload = part.get_payload(decode=True)
                            if not payload:
                                continue
                            decoded = payload.decode("utf-8", errors="replace")
                            if ct == "text/plain" and not body:
                                body = decoded[:2000]
                            elif ct == "text/html" and not html_body:
                                html_body = decoded[:3000]
                    else:
                        payload = msg.get_payload(decode=True)
                        if payload:
                            decoded = payload.decode("utf-8", errors="replace")
                            if msg.get_content_type() == "text/html":
                                html_body = decoded[:3000]
                            else:
                                body = decoded[:2000]
                    
                    # Fallback to HTML with tag stripping
                    if not body and html_body:
                        import re
                        body = re.sub(r'<[^>]+>', ' ', html_body)
                        body = re.sub(r'\s+', ' ', body).strip()[:2000]
                    
                    if body.strip():
                        email_threads.append(f"[EMAIL from {from_addr}] Subject: {subject}\n{body}")
            except Exception as e:
                print(f"IMAP search error for query {query}: {e}")
        
        # Also check Sent folder
        try:
            mail.select('"[Gmail]/Sent Mail"', readonly=True)
            sent_queries = [f'(TO "@{email_domain}")', f'(SUBJECT "{email_domain}")']
            for addr in contact_emails:
                sent_queries.append(f'(TO "{addr}")')
            for query in sent_queries:
                try:
                    _, msg_ids = mail.search(None, query)
                    for num in (msg_ids[0].split() if msg_ids[0] else [])[-5:]:
                        _, msg_data = mail.fetch(num, "(RFC822)")
                        if msg_data[0] is None:
                            continue
                        msg = email_lib.message_from_bytes(msg_data[0][1])
                        to_addr = msg.get("To", "")
                        subject = ""
                        raw_subj = msg.get("Subject", "")
                        if raw_subj:
                            parts = decode_header(raw_subj)
                            subject = " ".join(
                                p.decode(enc or "utf-8") if isinstance(p, bytes) else p
                                for p, enc in parts
                            )
                        body = ""
                        html_body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                ct = part.get_content_type()
                                payload = part.get_payload(decode=True)
                                if not payload:
                                    continue
                                decoded = payload.decode("utf-8", errors="replace")
                                if ct == "text/plain" and not body:
                                    body = decoded[:2000]
                                elif ct == "text/html" and not html_body:
                                    html_body = decoded[:3000]
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                decoded = payload.decode("utf-8", errors="replace")
                                if msg.get_content_type() == "text/html":
                                    html_body = decoded[:3000]
                                else:
                                    body = decoded[:2000]
                        
                        if not body and html_body:
                            import re as re2
                            body = re2.sub(r'<[^>]+>', ' ', html_body)
                            body = re2.sub(r'\s+', ' ', body).strip()[:2000]
                        
                        if body.strip():
                            email_threads.append(f"[SENT to {to_addr}] Subject: {subject}\n{body}")
                except Exception as e:
                    print(f"Sent folder search error: {e}")
        except Exception as e:
            print(f"Could not access Sent folder: {e}")
        
        mail.logout()
    except Exception as e:
        print(f"IMAP error grabbing rules: {e}")
    
    if not email_threads:
        raise HTTPException(400, "No email conversations found for this domain")
    
    conversation = "\n\n---\n\n".join(email_threads[-10:])  # last 10 messages
    
    prompt = f"""Analyze this email conversation with the publisher of {domain.domain}. Extract publisher rules, article requirements, AND any pricing/payment information.

CONVERSATION:
{conversation}

Extract the following as JSON:
{{
  "max_urls": <int or null - max outgoing URLs allowed per article/placement>,
  "cross_domain": <bool or null - do they allow links to multiple different domains in one article?>,
  "we_write": <bool or null - do WE provide the content/article, or do they write it?>,
  "min_words": <int or null - minimum word count requirement>,
  "max_words": <int or null - maximum word count allowed>,
  "link_attribute": <string or null - "dofollow", "nofollow", or "sponsored". What rel attribute do the links get?>,
  "max_images": <int or null - max images allowed per article>,
  "image_count": <int or null - recommended or required number of images>,
  "resource_links_count": <int or null - how many outbound/resource/authority links are allowed besides our target links>,
  "skip_resource_links": <bool or null - does the publisher explicitly forbid outbound links to other sites?>,
  "brand_mentions_scope": <"any" | "all" | null - enforce brand mention for any one linked brand or all linked brands>,
  "brand_mentions_brands": <string or null - comma-separated exact brand names to enforce (overrides scope)>,
  "brand_mentions_in_title": <bool or null - should a required brand appear in the title?>,
  "brand_mentions_body_count": <int or null - required body mention count per required brand>,
  "content_guidelines": <string or null - any content requirements, topics, formatting rules, forbidden topics>,
  "placement_notes": <string or null - where links go, link placement specifics, any other placement details>,
  "additional_notes": <string or null - any other relevant publisher rules or preferences>,
  "contact_name": <string or null - the name of the person we're dealing with>,
  "link_offerings": [
    {{"type": "<link type: Guest Post, Header, Footer, Navbar, Sidebar, Toplist, etc>", "price": <number>, "currency": "USD", "duration": "<permanent or Xmo>"}}
  ],
  "payment_methods": ["<PayPal, Wire Transfer, Paxum, USDT, Bitcoin, etc>"]
}}

Only include information explicitly stated or clearly implied in the emails. Use null/empty arrays for anything not mentioned."""

    try:
        result = await call_sonnet(prompt)
    except Exception as e:
        raise HTTPException(500, f"AI parsing failed: {str(e)}")
    
    # Save rules
    existing = db.query(PublisherRules).filter(
        PublisherRules.domain_id == domain_id,
        PublisherRules.deleted_at.is_(None)
    ).first()
    
    # Fields that map directly from AI extraction to PublisherRules
    rule_fields = [
        "max_urls", "cross_domain", "we_write", "min_words", "max_words",
        "link_attribute", "max_images", "image_count", "resource_links_count",
        "skip_resource_links", "brand_mentions_scope", "brand_mentions_in_title",
        "brand_mentions_body_count", "brand_mentions_brands", "content_guidelines",
    ]
    
    if existing:
        for field in rule_fields:
            val = result.get(field)
            if val is not None:
                setattr(existing, field, val)
        if result.get("placement_notes"):
            notes = result["placement_notes"]
            if result.get("additional_notes"):
                notes += "\n" + result["additional_notes"]
            existing.placement_notes = notes
    else:
        placement = result.get("placement_notes") or ""
        if result.get("additional_notes"):
            placement += ("\n" + result["additional_notes"]) if placement else result["additional_notes"]
        kwargs = {f: result.get(f) for f in rule_fields if result.get(f) is not None}
        kwargs["placement_notes"] = placement or None
        rules = PublisherRules(domain_id=domain_id, **kwargs)
        db.add(rules)
    
    # Save contact name
    if result.get("contact_name") and not domain.owner:
        domain.owner = result["contact_name"]
    
    # Save link prices
    from ..services.reply_parser import map_link_type, map_payment_method
    offerings = result.get("link_offerings") or []
    for offering in offerings:
        link_type = map_link_type(offering.get("type", ""))
        price = offering.get("price")
        if not link_type or not price:
            continue
        # Check if already exists
        existing_price = db.query(LinkPrice).filter(
            LinkPrice.domain_id == domain_id,
            LinkPrice.link_type == link_type,
            LinkPrice.deleted_at.is_(None),
        ).first()
        if not existing_price:
            duration_str = offering.get("duration", "permanent")
            is_permanent = "permanent" in str(duration_str).lower() if duration_str else True
            duration_months = None
            if not is_permanent and duration_str:
                import re
                m = re.search(r'(\d+)', str(duration_str))
                if m:
                    duration_months = int(m.group(1))
            lp = LinkPrice(
                domain_id=domain_id,
                link_type=link_type,
                price=float(price),
                currency=offering.get("currency", "USD"),
                is_permanent=is_permanent,
                duration_months=duration_months,
            )
            db.add(lp)
    
    # Save payment methods
    payments = result.get("payment_methods") or []
    for pm_raw in payments:
        method = map_payment_method(pm_raw)
        existing_pm = db.query(DomainPaymentMethod).filter(
            DomainPaymentMethod.domain_id == domain_id,
            DomainPaymentMethod.method == method,
            DomainPaymentMethod.deleted_at.is_(None),
        ).first()
        if not existing_pm:
            db.add(DomainPaymentMethod(domain_id=domain_id, method=method))
    
    db.commit()
    return {"ok": True, "extracted": result}


# ============ Orders ============

class OrderCreate(BaseModel):
    domain_id: str
    link_type: str
    price: Optional[float] = None
    currency: str = "USD"
    contact_id: Optional[str] = None
    target_url: Optional[str] = None
    anchor_text: Optional[str] = None
    anchor_type: Optional[str] = None
    anchor_text_id: Optional[str] = None
    article_content: Optional[str] = None

@router.post("/{campaign_id}/orders")
async def create_order(campaign_id: str, data: OrderCreate, db: Session = Depends(get_db)):
    """Create a new order for the campaign."""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.deleted_at.is_(None)
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    domain = db.query(Domain).filter(Domain.id == data.domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    
    anchor_type = data.anchor_type
    # Auto-classify anchor type based on text content if not specified
    if not anchor_type and data.anchor_text:
        # Use the classifier with brand info from the linked target site
        from .target_sites import classify_anchor
        brand_name = ""
        site_domain = campaign.target_site or ""
        brand_variations = []
        if campaign.target_site_id:
            ts = db.query(TargetSite).filter(TargetSite.id == campaign.target_site_id).first()
            if ts:
                brand_name = ts.name
                site_domain = ts.domain
                brand_variations = [v.strip() for v in (ts.brand_variations or "").split(",") if v.strip()]
        anchor_type = classify_anchor(data.anchor_text, brand_name, site_domain, data.target_url or "", brand_variations)
    
    # If anchor_text_id provided, auto-fill text/type from pool
    anchor_text_val = data.anchor_text
    target_url_val = data.target_url
    if data.anchor_text_id:
        pool_anchor = db.query(AnchorText).filter(AnchorText.id == data.anchor_text_id).first()
        if pool_anchor:
            if not anchor_text_val:
                anchor_text_val = pool_anchor.text
            if not anchor_type:
                anchor_type = pool_anchor.anchor_type
            if not target_url_val:
                target_url_obj = db.query(TargetURL).filter(TargetURL.id == pool_anchor.target_url_id).first()
                if target_url_obj:
                    target_url_val = target_url_obj.url
            pool_anchor.times_used = (pool_anchor.times_used or 0) + 1
    
    order = Order(
        campaign_id=campaign_id,
        domain_id=data.domain_id,
        contact_id=data.contact_id,
        link_type=data.link_type,
        price=data.price,
        currency=data.currency,
        target_url=target_url_val,
        anchor_text=anchor_text_val,
        anchor_type=anchor_type,
        anchor_text_id=data.anchor_text_id,
        article_content=data.article_content,
    )
    db.add(order)
    
    if data.price:
        campaign.spent = (campaign.spent or 0) + data.price
    
    db.commit()
    db.refresh(order)
    
    return {
        "id": order.id,
        "campaign_id": order.campaign_id,
        "domain_id": order.domain_id,
        "link_type": order.link_type,
        "price": order.price,
        "anchor_type": order.anchor_type,
        "status": order.status,
    }


class OrderUpdate(BaseModel):
    link_type: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    target_url: Optional[str] = None
    anchor_text: Optional[str] = None
    anchor_type: Optional[str] = None
    article_content: Optional[str] = None
    live_url: Optional[str] = None
    status: Optional[str] = None
    nofollow_target: Optional[bool] = None
    nofollow_resources: Optional[bool] = None
    skip_resource_links: Optional[bool] = None
    max_words: Optional[int] = None
    resource_links_count: Optional[int] = None
    brand_mentions_scope: Optional[str] = None
    brand_mentions_brands: Optional[str] = None
    brand_mentions_in_title: Optional[bool] = None
    brand_mentions_body_count: Optional[int] = None

@router.put("/orders/{order_id}")
async def update_order(order_id: str, data: OrderUpdate, db: Session = Depends(get_db)):
    """Update an order."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    old_price = order.price
    updates = data.model_dump(exclude_unset=True)
    
    for field, value in updates.items():
        setattr(order, field, value)
    
    # Auto-set timestamps based on status
    if "status" in updates:
        if updates["status"] == "paid" and not order.paid_at:
            order.paid_at = datetime.utcnow()
        elif updates["status"] == "published" and not order.live_at:
            order.live_at = datetime.utcnow()
        elif updates["status"] == "live" and not order.live_at:
            order.live_at = datetime.utcnow()
    
    # Update campaign spent if price changed
    if "price" in updates and updates["price"] != old_price:
        campaign = db.query(Campaign).filter(Campaign.id == order.campaign_id).first()
        if campaign:
            diff = (updates["price"] or 0) - (old_price or 0)
            campaign.spent = (campaign.spent or 0) + diff
    
    db.commit()
    
    return {"success": True}


@router.delete("/orders/{order_id}")
async def delete_order(order_id: str, db: Session = Depends(get_db)):
    """Delete an order."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Update campaign spent
    if order.price:
        campaign = db.query(Campaign).filter(Campaign.id == order.campaign_id).first()
        if campaign:
            campaign.spent = (campaign.spent or 0) - order.price
    
    db.delete(order)
    db.commit()
    
    return {"success": True}


# ============ Order Links (multi-link per order) ============

class OrderLinkCreate(BaseModel):
    target_url: str
    anchor_text: str
    anchor_type: Optional[str] = None
    anchor_text_id: Optional[str] = None
    article_topic: Optional[str] = None

@router.post("/orders/{order_id}/links")
async def add_order_link(order_id: str, data: OrderLinkCreate, db: Session = Depends(get_db)):
    """Add a link slot to an order."""
    from .target_sites import classify_anchor
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")
    
    # Get max slot
    max_slot = db.query(func.max(OrderLink.slot)).filter(OrderLink.order_id == order_id).scalar() or 0
    
    # Check publisher max_urls
    pub_rules = db.query(PublisherRules).filter(PublisherRules.domain_id == order.domain_id).first()
    if pub_rules and pub_rules.max_urls and (max_slot + 1) > pub_rules.max_urls:
        raise HTTPException(400, f"Publisher allows max {pub_rules.max_urls} links")
    
    # Auto-classify if no type
    anchor_type = data.anchor_type
    if not anchor_type:
        campaign = db.query(Campaign).filter(Campaign.id == order.campaign_id).first()
        brand_name, site_domain, variations = "", "", []
        if campaign and campaign.target_site_id:
            ts = db.query(TargetSite).filter(TargetSite.id == campaign.target_site_id).first()
            if ts:
                brand_name, site_domain = ts.name, ts.domain
                variations = [v.strip() for v in (ts.brand_variations or "").split(",") if v.strip()]
        anchor_type = classify_anchor(data.anchor_text, brand_name, site_domain, data.target_url, variations)
    
    # Increment times_used on anchor pool
    if data.anchor_text_id:
        pool_anchor = db.query(AnchorText).filter(AnchorText.id == data.anchor_text_id).first()
        if pool_anchor:
            pool_anchor.times_used = (pool_anchor.times_used or 0) + 1
    
    # Update article topic on the order if provided
    if data.article_topic is not None:
        order.article_topic = data.article_topic
    
    link = OrderLink(
        order_id=order_id,
        target_url=data.target_url,
        anchor_text=data.anchor_text,
        anchor_type=anchor_type,
        anchor_text_id=data.anchor_text_id,
        slot=max_slot + 1,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return {"id": link.id, "slot": link.slot, "anchor_type": anchor_type}


@router.delete("/order-links/{link_id}")
async def delete_order_link(link_id: str, db: Session = Depends(get_db)):
    """Remove a link slot from an order."""
    link = db.query(OrderLink).filter(OrderLink.id == link_id).first()
    if not link:
        raise HTTPException(404, "Link not found")
    
    # Decrement times_used
    if link.anchor_text_id:
        pool_anchor = db.query(AnchorText).filter(AnchorText.id == link.anchor_text_id).first()
        if pool_anchor and pool_anchor.times_used > 0:
            pool_anchor.times_used -= 1
    
    db.delete(link)
    db.commit()
    return {"ok": True}


# ============ Campaign Analytics ============

@router.get("/{campaign_id}/anchor-stats")
async def get_anchor_stats(campaign_id: str, db: Session = Depends(get_db)):
    """Get anchor text distribution stats for campaign."""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.deleted_at.is_(None)
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Count orders by anchor type
    orders = db.query(Order.anchor_type, func.count(Order.id)).filter(
        Order.campaign_id == campaign_id,
        Order.anchor_type.isnot(None)
    ).group_by(Order.anchor_type).all()
    
    counts = dict(orders)
    total = sum(counts.values()) or 1  # Avoid division by zero
    
    current = {
        "brand": round(counts.get("brand", 0) / total * 100, 1),
        "generic": round(counts.get("generic", 0) / total * 100, 1),
        "topical": round(counts.get("topical", 0) / total * 100, 1),
        "exact": round(counts.get("exact", 0) / total * 100, 1),
    }
    
    target = {
        "brand": campaign.anchor_brand_pct,
        "generic": campaign.anchor_generic_pct,
        "topical": campaign.anchor_topical_pct,
        "exact": campaign.anchor_exact_pct,
    }
    
    return {
        "current": current,
        "target": target,
        "total_orders": total,
        "counts": counts,
    }


@router.get("/{campaign_id}/anchor-pool")
async def get_anchor_pool(campaign_id: str, db: Session = Depends(get_db)):
    """Get available anchors from the linked Target Site for order creation."""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id, Campaign.deleted_at.is_(None)
    ).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    site = None
    if campaign.target_site_id:
        site = db.query(TargetSite).filter(TargetSite.id == campaign.target_site_id).first()
    if not site and campaign.target_site:
        site = db.query(TargetSite).filter(TargetSite.domain == campaign.target_site, TargetSite.deleted_at.is_(None)).first()
        if site:
            campaign.target_site_id = site.id
            db.commit()
    if not site:
        return {"site": None, "urls": [], "suggestion": None}
    
    urls = db.query(TargetURL).filter(
        TargetURL.site_id == site.id, TargetURL.deleted_at.is_(None)
    ).order_by(TargetURL.priority.desc()).all()
    
    target_dist = {
        "brand": site.anchor_brand_pct,
        "topical": site.anchor_topical_pct,
        "generic": site.anchor_generic_pct,
        "exact": site.anchor_exact_pct,
        "url": site.anchor_url_pct,
    }
    
    type_used = {"brand": 0, "topical": 0, "generic": 0, "exact": 0, "url": 0}
    all_anchors = []
    url_items = []
    
    for u in urls:
        anchors = db.query(AnchorText).filter(
            AnchorText.target_url_id == u.id, AnchorText.deleted_at.is_(None)
        ).all()
        anchor_items = []
        for a in anchors:
            anchor_items.append({
                "id": a.id, "text": a.text, "anchor_type": a.anchor_type,
                "times_used": a.times_used,
            })
            all_anchors.append({"anchor": a, "url": u})
            if a.anchor_type in type_used:
                type_used[a.anchor_type] += a.times_used
        url_items.append({
            "id": u.id, "url": u.url, "description": u.description,
            "priority": u.priority, "anchors": anchor_items,
        })
    
    # Compute suggestion
    total = sum(type_used.values()) or 1
    actual_pct = {k: v / total * 100 for k, v in type_used.items()}
    gaps = {k: target_dist.get(k, 0) - actual_pct.get(k, 0) for k in target_dist}
    best_type = max(gaps, key=gaps.get)
    
    suggestion = None
    candidates = [a for a in all_anchors if a["anchor"].anchor_type == best_type]
    if not candidates:
        candidates = all_anchors
    if candidates:
        candidates.sort(key=lambda a: a["anchor"].times_used)
        pick = candidates[0]
        suggestion = {
            "anchor_id": pick["anchor"].id,
            "text": pick["anchor"].text,
            "anchor_type": pick["anchor"].anchor_type,
            "target_url": pick["url"].url,
            "target_url_id": pick["url"].id,
            "times_used": pick["anchor"].times_used,
        }
    
    return {
        "site": {"id": site.id, "name": site.name, "domain": site.domain},
        "urls": url_items,
        "suggestion": suggestion,
        "distribution": {
            "target": target_dist,
            "actual": {k: round(v, 1) for k, v in actual_pct.items()},
            "gaps": {k: round(v, 1) for k, v in gaps.items()},
        },
    }


@router.get("/{campaign_id}/ready-domains")
async def get_ready_domains(
    campaign_id: str,
    link_type: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_traffic: Optional[int] = None,
    max_traffic: Optional[int] = None,
    min_dr: Optional[float] = None,
    max_dr: Optional[float] = None,
    has_payment: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    """Get domains ready for orders (have contact + prices, optionally filtered)."""
    from sqlalchemy import or_
    
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.deleted_at.is_(None)
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Domains already ordered in this campaign
    ordered_domain_ids = db.query(Order.domain_id).filter(
        Order.campaign_id == campaign_id
    ).distinct().subquery()
    
    # Domains with contacts (table or domain-level email)
    domains_with_contacts = db.query(Contact.domain_id).filter(
        Contact.deleted_at.is_(None)
    ).distinct().subquery()
    
    # Domains with prices (optionally filtered by link_type and price range)
    price_filters = [LinkPrice.deleted_at.is_(None)]
    if link_type:
        price_filters.append(LinkPrice.link_type == link_type)
    if min_price is not None:
        price_filters.append(LinkPrice.price >= min_price)
    if max_price is not None:
        price_filters.append(LinkPrice.price <= max_price)
    
    domains_with_prices = db.query(LinkPrice.domain_id).filter(
        *price_filters
    ).distinct().subquery()
    
    # Domains with payment methods
    domains_with_payment = db.query(DomainPaymentMethod.domain_id).filter(
        DomainPaymentMethod.deleted_at.is_(None)
    ).distinct().subquery()
    
    # Main query: contact + prices required, payment optional
    query = db.query(Domain).filter(
        Domain.deleted_at.is_(None),
        or_(
            Domain.id.in_(domains_with_contacts),
            Domain.email.isnot(None) & (Domain.email != ''),
        ),
        Domain.id.in_(domains_with_prices),
        Domain.id.notin_(ordered_domain_ids),
    )
    
    if has_payment is True:
        query = query.filter(Domain.id.in_(domains_with_payment))
    elif has_payment is False:
        query = query.filter(Domain.id.notin_(domains_with_payment))
    
    if min_traffic is not None:
        query = query.filter(Domain.organic_traffic >= min_traffic)
    if max_traffic is not None:
        query = query.filter(Domain.organic_traffic <= max_traffic)
    if min_dr is not None:
        query = query.filter(Domain.domain_rating >= min_dr)
    if max_dr is not None:
        query = query.filter(Domain.domain_rating <= max_dr)
    
    ready = query.order_by(Domain.organic_traffic.desc()).limit(200).all()
    
    items = []
    for d in ready:
        link_types = db.query(LinkPrice.link_type, LinkPrice.price, LinkPrice.duration_months).filter(
            LinkPrice.domain_id == d.id,
            LinkPrice.deleted_at.is_(None)
        ).all()
        
        contact = db.query(Contact).filter(
            Contact.domain_id == d.id,
            Contact.deleted_at.is_(None),
            Contact.is_primary == True
        ).first()
        
        if not contact:
            contact = db.query(Contact).filter(
                Contact.domain_id == d.id,
                Contact.deleted_at.is_(None)
            ).first()
        
        payment_methods = db.query(DomainPaymentMethod.method).filter(
            DomainPaymentMethod.domain_id == d.id,
            DomainPaymentMethod.deleted_at.is_(None)
        ).all()
        
        items.append({
            "id": d.id,
            "domain": d.domain,
            "domain_rating": d.domain_rating,
            "organic_traffic": d.organic_traffic,
            "contact_name": d.owner,
            "contact_email": contact.email if contact else (d.email or None),
            "contact_id": contact.id if contact else None,
            "link_types": [
                {"type": lt, "price": p, "duration": dur} for lt, p, dur in link_types
            ],
            "payment_methods": [m for (m,) in payment_methods],
            "status": d.status,
        })
    
    return {"items": items, "total": len(items)}


@router.get("/scheduler/status")
async def scheduler_status():
    """Get scheduler status with all scheduled jobs."""
    from ..services.scheduler import get_scheduler, get_scheduled_jobs
    scheduler = get_scheduler()
    return {
        "running": scheduler is not None and scheduler.running if scheduler else False,
        "jobs": get_scheduled_jobs(),
    }


@router.post("/scheduler/reload")
async def scheduler_reload():
    """Force reload all scheduler jobs from DB."""
    from ..services.scheduler import reload_campaign_jobs, get_scheduled_jobs
    await reload_campaign_jobs()
    return {"reloaded": True, "jobs": get_scheduled_jobs()}


@router.post("/{campaign_id}/run-cycle")
async def run_campaign_cycle_endpoint(campaign_id: str, db: Session = Depends(get_db)):
    """Manually trigger one autopilot cycle for a campaign."""
    from ..services.campaign_autopilot import run_campaign_cycle
    return await run_campaign_cycle(campaign_id, db)


@router.post("/run-all-auto")
async def run_all_auto_campaigns(db: Session = Depends(get_db)):
    """Check all auto campaigns and run cycles where velocity allows."""
    from ..services.campaign_autopilot import run_campaign_cycle
    campaigns = db.query(Campaign).filter(
        Campaign.mode == "auto",
        Campaign.status == "active",
        Campaign.deleted_at.is_(None),
    ).all()
    results = []
    for c in campaigns:
        result = await run_campaign_cycle(c.id, db)
        results.append({"campaign_id": c.id, "name": c.name, **result})
    return {"campaigns_checked": len(campaigns), "results": results}


class BulkOrderItem(BaseModel):
    domain_id: str
    link_type: str
    price: Optional[float] = None
    contact_id: Optional[str] = None

class BulkOrderCreate(BaseModel):
    orders: list[BulkOrderItem]

@router.post("/{campaign_id}/orders/bulk")
async def create_bulk_orders(campaign_id: str, data: BulkOrderCreate, db: Session = Depends(get_db)):
    """Bulk-create draft orders for a campaign."""
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.deleted_at.is_(None)
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    created = []
    skipped = 0
    for item in data.orders:
        # Skip if already ordered in this campaign with same link type
        existing = db.query(Order).filter(
            Order.campaign_id == campaign_id,
            Order.domain_id == item.domain_id,
            Order.link_type == item.link_type,
        ).first()
        if existing:
            skipped += 1
            continue
        
        domain = db.query(Domain).filter(Domain.id == item.domain_id).first()
        if not domain:
            continue
        
        # Find contact
        contact_id = item.contact_id
        if not contact_id:
            contact = db.query(Contact).filter(
                Contact.domain_id == item.domain_id,
                Contact.deleted_at.is_(None),
            ).first()
            contact_id = contact.id if contact else None
        
        order = Order(
            campaign_id=campaign_id,
            domain_id=item.domain_id,
            contact_id=contact_id,
            link_type=item.link_type,
            price=item.price,
            currency="USD",
            status="draft",
        )
        db.add(order)
        created.append(order)
    
    db.commit()
    return {"created": len(created), "skipped": skipped}
