"""
Orders API router - Verification, payment confirmation, health checks.
"""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Order, Domain, Contact, LinkCheck, DomainPaymentMethod, SentEmail


router = APIRouter()


class ApproveRequest(BaseModel):
    modified: bool = False
    article_content: Optional[str] = None


@router.post("/{order_id}/approve")
async def approve_order(order_id: str, body: ApproveRequest = None, db: Session = Depends(get_db)):
    """Approve an article for sending to publisher."""
    from ..services.campaign_autopilot import handle_article_approval
    if body and body.article_content:
        order = db.query(Order).filter(Order.id == order_id).first()
        if order:
            order.article_content = body.article_content
            db.commit()
    modified = body.modified if body else False
    return await handle_article_approval(order_id, approved=True, modified=modified, db=db)


@router.post("/{order_id}/reject")
async def reject_order(order_id: str, db: Session = Depends(get_db)):
    """Reject an article."""
    from ..services.campaign_autopilot import handle_article_approval
    return await handle_article_approval(order_id, approved=False, modified=False, db=db)


class VerifyRequest(BaseModel):
    url: str


class ConfirmPaymentRequest(BaseModel):
    notes: Optional[str] = None


class MarkPaymentSentRequest(BaseModel):
    notes: Optional[str] = None


@router.post("/{order_id}/mark-payment-sent")
async def mark_payment_sent(order_id: str, body: MarkPaymentSentRequest = None, db: Session = Depends(get_db)):
    """Mark payment as sent for an order (upfront-payment publishers). Sends email to publisher."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    domain = db.query(Domain).filter(Domain.id == order.domain_id).first()

    order.payment_sent_at = datetime.utcnow()
    order.status = "payment_sent"

    # Resolve contact email
    contact_email = None
    contact_name = "there"
    if order.contact_id:
        contact = db.query(Contact).filter(Contact.id == order.contact_id).first()
        if contact:
            contact_email = contact.email
            contact_name = contact.name or "there"
    if not contact_email and domain and domain.email:
        contact_email = domain.email
        contact_name = domain.owner or "there"

    email_sent = False
    if contact_email:
        try:
            from ..services.reply_parser import send_followup_custom, get_thread_context
            domain_name = domain.domain if domain else "your site"
            extra_note = f"\n\n{body.notes}" if body and body.notes else ""
            email_body = f"""Hi {contact_name},

Just a quick note to let you know that payment has been sent for the guest post on {domain_name}. Please let me know once it's live and I'll verify the placement.{extra_note}

Thanks,
Tony"""
            # Thread into existing conversation — use full context including subject
            ctx = get_thread_context(db, domain.id, contact_email) if domain else {"in_reply_to": None, "references": None, "subject": None}
            await send_followup_custom(
                contact_email, domain_name, contact_name, email_body,
                domain_id=domain.id if domain else None,
                db=db,
                in_reply_to=ctx["in_reply_to"],
                references=ctx["references"],
            )
            email_sent = True
        except Exception as e:
            print(f"Failed to send payment-sent email: {e}")

    db.commit()
    db.refresh(order)

    return {
        "id": order.id,
        "status": order.status,
        "payment_sent_at": order.payment_sent_at.isoformat(),
        "email_sent": email_sent,
        "email_to": contact_email,
    }


@router.post("/{order_id}/verify")
async def verify_order(order_id: str, body: VerifyRequest, db: Session = Depends(get_db)):
    """Trigger manual verification of a live URL for an order."""
    from ..services.link_monitor import verify_live_url
    try:
        result = await verify_live_url(order_id, body.url, db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{order_id}/deep-verify")
async def deep_verify_order(order_id: str, body: VerifyRequest, db: Session = Depends(get_db)):
    """
    Deep verification using agent-browser (real browser rendering).
    
    Takes screenshot, verifies rendered links, checks images loaded,
    validates dofollow on rendered page. More thorough than basic verify.
    """
    from ..services.link_monitor import deep_verify_live_url
    try:
        result = await deep_verify_live_url(order_id, body.url, db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{order_id}/confirm-payment")
async def confirm_payment(order_id: str, body: ConfirmPaymentRequest = None, db: Session = Depends(get_db)):
    """Confirm payment for an order. Sets paid_at, sends confirmation email, Slack alert."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    domain = db.query(Domain).filter(Domain.id == order.domain_id).first()

    # Update order
    order.paid_at = datetime.utcnow()
    order.status = "paid"

    # Get contact email
    contact_email = None
    contact_name = "there"
    if order.contact_id:
        contact = db.query(Contact).filter(Contact.id == order.contact_id).first()
        if contact:
            contact_email = contact.email
            contact_name = contact.name or "there"
    if not contact_email and domain and domain.email:
        contact_email = domain.email
        contact_name = domain.owner or "there"

    # Send confirmation email
    if contact_email:
        try:
            from ..services.reply_parser import send_followup_custom
            domain_name = domain.domain if domain else "your site"
            payment_body = f"""Hi {contact_name},

Just wanted to let you know that payment has been sent for the guest post on {domain_name}. Thank you for the great placement!

If you have any questions, feel free to reach out.

Best,
Tony"""
            await send_followup_custom(contact_email, domain_name, contact_name, payment_body,
                                       domain_id=domain.id if domain else None, db=db)
        except Exception as e:
            print(f"Failed to send payment confirmation email: {e}")

    db.commit()

    # Slack notification
    try:
        from ..services.slack_notifier import send_slack_alert
        pm = db.query(DomainPaymentMethod).filter(
            DomainPaymentMethod.domain_id == order.domain_id,
        ).first()
        payment_info = f"{pm.method}: {pm.details}" if pm and pm.details else (pm.method if pm else "")
        await send_slack_alert("PAYMENT_CONFIRMED", order, domain, extra={
            "payment_info": payment_info,
        })
    except Exception as e:
        print(f"Slack alert failed: {e}")

    # Auto-verify the live URL and mark as live if verification passes
    verify_result = None
    if order.live_url:
        try:
            from ..services.link_monitor import verify_live_url
            verify_result = await verify_live_url(order_id, order.live_url, db, auto_update_status=True)
            # Refresh order after verification may have updated it
            db.refresh(order)
            if verify_result.get("verified"):
                order.status = "live"
                order.live_at = datetime.utcnow()
                db.commit()
        except Exception as e:
            print(f"Auto-verification after payment failed: {e}")
            verify_result = {"verified": False, "error": str(e)}

    return {
        "success": True,
        "order_id": order_id,
        "status": order.status,
        "paid_at": order.paid_at.isoformat(),
        "verification": verify_result,
    }


@router.post("/check-links")
async def check_links(db: Session = Depends(get_db)):
    """Monthly health check - re-verify all live/paid orders."""
    from ..services.link_monitor import check_all_live_links
    try:
        result = await check_all_live_links(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{order_id}/checks")
async def get_checks(order_id: str, db: Session = Depends(get_db)):
    """Get verification history for an order."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    checks = db.query(LinkCheck).filter(
        LinkCheck.order_id == order_id
    ).order_by(LinkCheck.checked_at.desc()).all()

    return [
        {
            "id": c.id,
            "checked_at": c.checked_at.isoformat() if c.checked_at else None,
            "status": c.status,
            "http_status": c.http_status,
            "found_anchor": c.found_anchor,
            "found_url": c.found_url,
            "notes": c.notes,
        }
        for c in checks
    ]
