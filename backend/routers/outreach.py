"""
Outreach API router - email campaigns and messaging.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import OutreachCampaign, OutreachMessage, Contact, OutreachStatus
from ..services.email import EmailService

router = APIRouter()


@router.get("/campaigns")
async def list_campaigns(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List all outreach campaigns."""
    query = db.query(OutreachCampaign).filter(OutreachCampaign.deleted_at.is_(None))
    
    total = query.count()
    campaigns = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return {
        "items": campaigns,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("/campaigns")
async def create_campaign(
    name: str,
    description: Optional[str] = None,
    subject_template: Optional[str] = None,
    body_template: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Create a new outreach campaign."""
    campaign = OutreachCampaign(
        name=name,
        description=description,
        subject_template=subject_template,
        body_template=body_template,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
):
    """Get a specific campaign with stats."""
    campaign = db.query(OutreachCampaign).filter(
        OutreachCampaign.id == campaign_id
    ).first()
    
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    return campaign


@router.get("/messages")
async def list_messages(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    campaign_id: Optional[str] = None,
    status: Optional[OutreachStatus] = None,
    db: Session = Depends(get_db),
):
    """List outreach messages."""
    query = db.query(OutreachMessage).filter(OutreachMessage.deleted_at.is_(None))
    
    if campaign_id:
        query = query.filter(OutreachMessage.campaign_id == campaign_id)
    if status:
        query = query.filter(OutreachMessage.status == status)
    
    total = query.count()
    messages = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return {
        "items": messages,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("/messages")
async def create_message(
    contact_id: str,
    subject: str,
    body: str,
    campaign_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Create a draft outreach message."""
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    message = OutreachMessage(
        contact_id=contact_id,
        campaign_id=campaign_id,
        subject=subject,
        body=body,
        status=OutreachStatus.DRAFT,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.post("/messages/{message_id}/send")
async def send_message(
    message_id: str,
    db: Session = Depends(get_db),
):
    """Send an outreach message."""
    message = db.query(OutreachMessage).filter(
        OutreachMessage.id == message_id
    ).first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    if message.status not in [OutreachStatus.DRAFT, OutreachStatus.SCHEDULED]:
        raise HTTPException(status_code=400, detail="Message already sent")
    
    contact = db.query(Contact).filter(Contact.id == message.contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    try:
        email_service = EmailService()
        await email_service.send(
            to_email=contact.email,
            subject=message.subject,
            body=message.body,
        )
        
        from datetime import datetime
        message.status = OutreachStatus.SENT
        message.sent_at = datetime.utcnow()
        
        # Update campaign stats
        if message.campaign_id:
            campaign = db.query(OutreachCampaign).filter(
                OutreachCampaign.id == message.campaign_id
            ).first()
            if campaign:
                campaign.total_sent += 1
        
        db.commit()
        
        return {"success": True, "message": "Email sent", "status": message.status.value}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


@router.post("/messages/{message_id}/status")
async def update_message_status(
    message_id: str,
    status: OutreachStatus,
    db: Session = Depends(get_db),
):
    """Manually update message status (for tracking opens, replies)."""
    message = db.query(OutreachMessage).filter(
        OutreachMessage.id == message_id
    ).first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    from datetime import datetime
    message.status = status
    
    if status == OutreachStatus.OPENED:
        message.opened_at = datetime.utcnow()
    elif status == OutreachStatus.REPLIED:
        message.replied_at = datetime.utcnow()
    
    db.commit()
    
    return {"success": True, "status": status.value}
