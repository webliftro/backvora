"""
Campaign Auto-Pilot Service - Orchestrates the full auto pipeline for campaigns.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from urllib.parse import urlparse

from ..models import (
    Campaign, Domain, Contact, LinkPrice, Order, OrderLink,
    AnchorText, TargetURL, TargetSite, DomainStatus,
)


def get_eligible_domains(campaign: Campaign, db: Session) -> List[Dict[str, Any]]:
    """
    Query domains matching campaign filters.
    - Must have contact email + pricing
    - Status in REPLIED, DEAL_CLOSED, or ACCEPTED
    - Exclude domains already used for same target site
    - Sorted by best value (lowest price per DR point)
    """
    eligible_statuses = [DomainStatus.REPLIED, DomainStatus.DEAL_CLOSED, DomainStatus.ACCEPTED]

    # Base query: domains with valid status
    query = db.query(Domain).filter(
        Domain.deleted_at.is_(None),
        Domain.status.in_(eligible_statuses),
    )

    # Must have contact email (domain-level or via contacts table)
    domains_with_contacts = db.query(Contact.domain_id).filter(
        Contact.deleted_at.is_(None),
        Contact.email.isnot(None),
    ).distinct().subquery()

    query = query.filter(
        or_(
            Domain.email.isnot(None) & (Domain.email != ''),
            Domain.id.in_(domains_with_contacts),
        )
    )

    # Must have pricing
    price_filters = [LinkPrice.deleted_at.is_(None)]
    if campaign.filter_link_type:
        price_filters.append(LinkPrice.link_type == campaign.filter_link_type)
    if campaign.filter_price_min is not None:
        price_filters.append(LinkPrice.price >= campaign.filter_price_min)
    if campaign.filter_price_max is not None:
        price_filters.append(LinkPrice.price <= campaign.filter_price_max)

    domains_with_prices = db.query(LinkPrice.domain_id).filter(
        *price_filters
    ).distinct().subquery()
    query = query.filter(Domain.id.in_(domains_with_prices))

    # Domain metric filters
    if campaign.filter_traffic_min is not None:
        query = query.filter(Domain.organic_traffic >= campaign.filter_traffic_min)
    if campaign.filter_traffic_max is not None:
        query = query.filter(Domain.organic_traffic <= campaign.filter_traffic_max)
    if campaign.filter_dr_min is not None:
        query = query.filter(Domain.domain_rating >= campaign.filter_dr_min)
    if campaign.filter_dr_max is not None:
        query = query.filter(Domain.domain_rating <= campaign.filter_dr_max)

    # Niche tag filter
    if campaign.filter_niche_tags:
        filter_tags = [t.strip().lower() for t in campaign.filter_niche_tags.split(",") if t.strip()]
        if filter_tags:
            # Match any of the tags
            tag_conditions = []
            for tag in filter_tags:
                tag_conditions.append(Domain.niche_tags.ilike(f"%{tag}%"))
                tag_conditions.append(Domain.tags.ilike(f"%{tag}%"))
                tag_conditions.append(Domain.category.ilike(f"%{tag}%"))
            query = query.filter(or_(*tag_conditions))

    # Exclude domains already used for same target site
    target_site = campaign.target_site
    if target_site:
        target_domain = target_site.replace("www.", "").lower()
        # Find all orders in ALL campaigns for same target site
        used_domain_ids_q = (
            db.query(Order.domain_id)
            .join(OrderLink, OrderLink.order_id == Order.id, isouter=True)
            .join(Campaign, Campaign.id == Order.campaign_id)
            .filter(
                or_(
                    # Check order-level target_url
                    Order.target_url.ilike(f"%{target_domain}%"),
                    # Check order links target_url
                    OrderLink.target_url.ilike(f"%{target_domain}%"),
                )
            )
            .distinct()
        )
        used_domain_ids = [r[0] for r in used_domain_ids_q.all()]
        if used_domain_ids:
            query = query.filter(Domain.id.notin_(used_domain_ids))

    domains = query.limit(200).all()

    # Build result with pricing info, sorted by value
    results = []
    for d in domains:
        # Get best price for this domain
        price_q = db.query(LinkPrice).filter(
            LinkPrice.domain_id == d.id,
            LinkPrice.deleted_at.is_(None),
        )
        if campaign.filter_link_type:
            price_q = price_q.filter(LinkPrice.link_type == campaign.filter_link_type)
        prices = price_q.all()
        if not prices:
            continue

        best_price = min(prices, key=lambda p: p.price or float('inf'))
        dr = d.domain_rating or 1
        value_score = (best_price.price or 9999) / dr  # lower = better value

        results.append({
            "domain": d,
            "price": best_price.price,
            "link_type": best_price.link_type,
            "currency": best_price.currency or "USD",
            "value_score": value_score,
        })

    # Sort by best value
    results.sort(key=lambda x: x["value_score"])
    return results


def should_create_order(campaign: Campaign, db: Session) -> bool:
    """Check if campaign should create a new order based on mode, velocity, and budget."""
    if campaign.mode != "auto":
        return False

    if campaign.status != "active":
        return False

    # Check budget
    if campaign.budget_total is not None and campaign.budget_spent >= campaign.budget_total:
        # Auto-pause
        campaign.status = "paused"
        db.commit()
        from .scheduler import remove_campaign_job
        remove_campaign_job(campaign.id)
        return False

    # Check velocity
    if campaign.last_order_sent_at is not None:
        period = timedelta(days=campaign.velocity_period_days or 7)
        if datetime.utcnow() - campaign.last_order_sent_at < period:
            return False

    return True


async def run_campaign_cycle(campaign_id: str, db: Session) -> Dict[str, Any]:
    """
    Main autopilot function - runs one cycle of the campaign.
    """
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.deleted_at.is_(None),
    ).first()
    if not campaign:
        return {"success": False, "reason": "Campaign not found"}

    if not should_create_order(campaign, db):
        return {"success": False, "reason": "Not eligible for new order"}

    # Get eligible domains
    eligible = get_eligible_domains(campaign, db)
    if not eligible:
        return {"success": False, "reason": "No eligible domains found"}

    # Pick best domain
    pick = eligible[0]
    domain = pick["domain"]
    price = pick["price"]
    link_type = pick["link_type"]
    currency = pick["currency"]

    # Find contact
    contact = db.query(Contact).filter(
        Contact.domain_id == domain.id,
        Contact.deleted_at.is_(None),
        Contact.is_primary == True,
    ).first()
    if not contact:
        contact = db.query(Contact).filter(
            Contact.domain_id == domain.id,
            Contact.deleted_at.is_(None),
        ).first()

    # Auto-assign anchor text using campaign's target site anchor pool
    anchor_text_val = None
    anchor_type_val = None
    target_url_val = None
    anchor_text_id = None

    if campaign.target_site_id:
        site = db.query(TargetSite).filter(TargetSite.id == campaign.target_site_id).first()
        if site:
            urls = db.query(TargetURL).filter(
                TargetURL.site_id == site.id,
                TargetURL.deleted_at.is_(None),
            ).order_by(TargetURL.priority.desc()).all()

            if urls:
                # Get anchor distribution
                target_dist = {
                    "brand": site.anchor_brand_pct,
                    "topical": site.anchor_topical_pct,
                    "generic": site.anchor_generic_pct,
                    "exact": site.anchor_exact_pct,
                    "url": site.anchor_url_pct,
                }

                # Count current usage
                type_used = {"brand": 0, "topical": 0, "generic": 0, "exact": 0, "url": 0}
                all_anchors = []
                for u in urls:
                    anchors = db.query(AnchorText).filter(
                        AnchorText.target_url_id == u.id,
                        AnchorText.deleted_at.is_(None),
                    ).all()
                    for a in anchors:
                        all_anchors.append({"anchor": a, "url": u})
                        if a.anchor_type in type_used:
                            type_used[a.anchor_type] += a.times_used

                if all_anchors:
                    total = sum(type_used.values()) or 1
                    actual_pct = {k: v / total * 100 for k, v in type_used.items()}
                    gaps = {k: target_dist.get(k, 0) - actual_pct.get(k, 0) for k in target_dist}
                    best_type = max(gaps, key=gaps.get)

                    candidates = [a for a in all_anchors if a["anchor"].anchor_type == best_type]
                    if not candidates:
                        candidates = all_anchors
                    candidates.sort(key=lambda a: a["anchor"].times_used)
                    pick_anchor = candidates[0]

                    anchor_text_val = pick_anchor["anchor"].text
                    anchor_type_val = pick_anchor["anchor"].anchor_type
                    target_url_val = pick_anchor["url"].url
                    anchor_text_id = pick_anchor["anchor"].id

    # Fallback anchor if no pool
    if not anchor_text_val:
        anchor_text_val = campaign.target_site or campaign.name
        anchor_type_val = "brand"
        target_url_val = f"https://{campaign.target_site}" if campaign.target_site else None

    # Create order
    order = Order(
        campaign_id=campaign.id,
        domain_id=domain.id,
        contact_id=contact.id if contact else None,
        link_type=link_type,
        price=price,
        currency=currency,
        target_url=target_url_val,
        anchor_text=anchor_text_val,
        anchor_type=anchor_type_val,
        anchor_text_id=anchor_text_id,
        status="draft",
    )
    db.add(order)
    db.flush()  # ensure order.id is populated

    # Add order link
    ol = OrderLink(
        order_id=order.id,
        target_url=target_url_val or "",
        anchor_text=anchor_text_val,
        anchor_type=anchor_type_val,
        anchor_text_id=anchor_text_id,
        slot=1,
    )
    db.add(ol)

    # Increment times_used
    if anchor_text_id:
        pool_anchor = db.query(AnchorText).filter(AnchorText.id == anchor_text_id).first()
        if pool_anchor:
            pool_anchor.times_used = (pool_anchor.times_used or 0) + 1

    db.commit()
    db.refresh(order)

    # Generate article
    from .article_writer import generate_article
    article_result = await generate_article(order.id, db)

    if campaign.approval_mode == "review":
        # Send to Slack for review
        order.status = "pending_review"
        db.commit()

        from .slack_notifier import send_article_for_review
        await send_article_for_review(order, domain, order.article_content, campaign)

        return {
            "success": True,
            "action": "pending_review",
            "order_id": order.id,
            "domain": domain.domain,
            "price": price,
        }
    else:
        # Auto mode - send directly
        from .order_sender import send_order
        await send_order(order.id, db)

        campaign.last_order_sent_at = datetime.utcnow()
        campaign.budget_spent = (campaign.budget_spent or 0) + (price or 0)
        db.commit()

        # Check budget after spending
        if campaign.budget_total is not None and campaign.budget_spent >= campaign.budget_total:
            campaign.status = "paused"
            db.commit()
            from .scheduler import remove_campaign_job
            remove_campaign_job(campaign.id)
            from .slack_notifier import send_slack_alert
            await send_slack_alert(
                "BUDGET_EXHAUSTED", None, None,
                extra={
                    "domain": campaign.name,
                    "budget_total": campaign.budget_total,
                    "budget_spent": campaign.budget_spent,
                }
            )

        return {
            "success": True,
            "action": "sent",
            "order_id": order.id,
            "domain": domain.domain,
            "price": price,
        }


async def handle_article_approval(
    order_id: str,
    approved: bool,
    modified: bool,
    db: Session,
) -> Dict[str, Any]:
    """Handle approval/rejection of an article from review."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return {"success": False, "reason": "Order not found"}

    campaign = db.query(Campaign).filter(Campaign.id == order.campaign_id).first()
    if not campaign:
        return {"success": False, "reason": "Campaign not found"}

    domain = db.query(Domain).filter(Domain.id == order.domain_id).first()

    if not approved:
        # Rejected
        order.status = "rejected"
        campaign.consecutive_approvals = 0
        db.commit()
        return {"success": True, "action": "rejected", "order_id": order_id}

    # Approved
    if modified:
        campaign.consecutive_approvals = 0
    else:
        campaign.consecutive_approvals = (campaign.consecutive_approvals or 0) + 1

        # Check graduation threshold
        if campaign.consecutive_approvals >= (campaign.approval_threshold or 10):
            campaign.approval_mode = "auto"
            db.commit()
            from .slack_notifier import send_slack_alert
            await send_slack_alert(
                "CAMPAIGN_GRADUATED", None, None,
                extra={
                    "domain": campaign.name,
                    "threshold": campaign.approval_threshold,
                }
            )

    # Send article to publisher
    from .order_sender import send_order
    await send_order(order.id, db)

    campaign.last_order_sent_at = datetime.utcnow()
    campaign.budget_spent = (campaign.budget_spent or 0) + (order.price or 0)
    db.commit()

    # Check budget
    if campaign.budget_total is not None and campaign.budget_spent >= campaign.budget_total:
        campaign.status = "paused"
        db.commit()
        from .scheduler import remove_campaign_job
        remove_campaign_job(campaign.id)
        from .slack_notifier import send_slack_alert
        await send_slack_alert(
            "BUDGET_EXHAUSTED", None, None,
            extra={
                "domain": campaign.name,
                "budget_total": campaign.budget_total,
                "budget_spent": campaign.budget_spent,
            }
        )

    return {
        "success": True,
        "action": "approved_and_sent",
        "order_id": order_id,
        "consecutive_approvals": campaign.consecutive_approvals,
        "approval_mode": campaign.approval_mode,
    }
