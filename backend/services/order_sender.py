"""
Order Sender Service - Sends completed orders to publishers via email.
Includes article content, links to include, and any special instructions.
"""

import smtplib
import ssl
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formatdate, make_msgid
from typing import Dict, Any, List
from pathlib import Path
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Order, Domain, Contact, OrderLink, PublisherRules, SentEmail, Campaign, ReceivedEmail
from .docx_generator import generate_docx


EMAIL_TEMPLATE = """Hi {contact_name},

I hope this message finds you well!

As discussed, I've prepared a guest post article for {domain}. Please find it attached as a Word document with images embedded.

Article: {title}
Word count: ~{word_count}

The article includes the following links:
{links_list}

{special_instructions}

Please let me know if you'd like any revisions. Once the article is live, please send me the published URL and payment will follow immediately.

Looking forward to working with you!

Best regards,
Tony
"""


def get_contact_email(order: Order, domain: Domain, db: Session) -> tuple[str, str]:
    """
    Get the contact email and name for an order.
    Checks: order.contact_id → domain.email → primary contact
    
    Returns:
        tuple of (email, name)
    """
    contact_name = "there"
    contact_email = None
    
    # First check if order has a contact assigned
    if order.contact_id:
        contact = db.query(Contact).filter(Contact.id == order.contact_id).first()
        if contact and contact.email:
            contact_email = contact.email
            contact_name = contact.name or "there"
    
    # Fallback to domain email
    if not contact_email and domain.email:
        contact_email = domain.email
        contact_name = domain.owner or "there"
    
    # Fallback to primary contact
    if not contact_email:
        primary = db.query(Contact).filter(
            Contact.domain_id == domain.id,
            Contact.is_primary == True
        ).first()
        if primary:
            contact_email = primary.email
            contact_name = primary.name or "there"
    
    if not contact_email:
        raise ValueError(f"No contact email found for domain {domain.domain}")
    
    return contact_email, contact_name


async def send_order(
    order_id: str,
    db: Session
) -> Dict[str, Any]:
    """
    Send a completed order to the publisher via email.
    
    Args:
        order_id: The order ID to send
        db: Database session
        
    Returns:
        Dict with success status and sent email details
    """
    # Fetch order with relationships
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError(f"Order {order_id} not found")
    
    # Validate order has article content
    if not order.article_content:
        raise ValueError(f"Order {order_id} has no article content. Generate article first.")
    
    # Get domain
    domain = db.query(Domain).filter(Domain.id == order.domain_id).first()
    if not domain:
        raise ValueError(f"Domain {order.domain_id} not found")
    
    # Get contact email
    contact_email, contact_name = get_contact_email(order, domain, db)
    
    # Get campaign for context
    campaign = db.query(Campaign).filter(Campaign.id == order.campaign_id).first()
    campaign_name = campaign.name if campaign else "Link Building Campaign"
    
    # Get all links
    links = db.query(OrderLink).filter(OrderLink.order_id == order_id).order_by(OrderLink.slot).all()
    
    # If no links exist, check legacy fields
    if not links and order.anchor_text and order.target_url:
        links_list = f"• {order.anchor_text} → {order.target_url}"
    else:
        links_list = "\n".join([
            f"• {link.anchor_text} → {link.target_url}"
            for link in links
        ])
    
    # Get publisher rules for special instructions
    rules = db.query(PublisherRules).filter(PublisherRules.domain_id == domain.id).first()
    special_instructions = ""
    if rules and rules.placement_notes:
        special_instructions = f"**Special Instructions:**\n{rules.placement_notes}\n"
    
    # Check if publisher wanted upfront payment — add payment terms reminder
    upfront_negotiation = db.query(SentEmail).filter(
        SentEmail.domain_id == domain.id,
        SentEmail.body.like("%(auto no-upfront%"),
    ).count()
    payment_methods = [pm.method for pm in domain.payment_methods] if hasattr(domain, 'payment_methods') and domain.payment_methods else []
    
    if upfront_negotiation > 0 or any("upfront" in str(pm).lower() for pm in payment_methods):
        special_instructions += (
            "\n**Payment terms:** As mentioned, we process payment as soon as the article is live "
            "and verified. Once you share the published URL, payment will be sent the same day "
            "via your preferred method. We've always honored this with all our publishing partners.\n"
        )
    
    # Extract title and word count
    article_lines = order.article_content.split('\n')
    title_line = article_lines[0] if article_lines else "Guest Post Article"
    if title_line.startswith("TITLE:"):
        title_line = title_line.replace("TITLE:", "").strip()
    word_count = len(order.article_content.split())
    
    # Generate DOCX
    docx_path = generate_docx(order.article_content, order_id)
    docx_filename = Path(docx_path).name
    
    # Build email body
    email_body = EMAIL_TEMPLATE.format(
        contact_name=contact_name,
        domain=domain.domain,
        title=title_line,
        word_count=word_count,
        links_list=links_list,
        special_instructions=special_instructions,
    )
    
    subject = f"Guest Post Article for {domain.domain}"

    # Thread into existing conversation using full thread context
    from .reply_parser import get_thread_context
    ctx = get_thread_context(db, domain.id, contact_email)
    in_reply_to = ctx["in_reply_to"]
    references = ctx["references"]
    # Use the thread's subject to stay in the same conversation
    # But ONLY if there's a received email (i.e. a real thread exists, not just our own sent emails)
    if ctx["subject"] and db.query(ReceivedEmail).filter(
        ReceivedEmail.domain_id == domain.id,
        ReceivedEmail.message_id.isnot(None),
        ReceivedEmail.message_id != "",
    ).first():
        thread_subject = ctx["subject"]
        subject = thread_subject if thread_subject.lower().startswith("re:") else f"Re: {thread_subject}"
    
    # Send email via SMTP
    try:
        context = ssl.create_default_context()
        smtp = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context)
        smtp.login(settings.email_account, settings.email_password)
        
        try:
            msg = MIMEMultipart()
            msg["From"] = settings.email_account
            msg["To"] = contact_email
            msg["Subject"] = subject
            msg["Date"] = formatdate(localtime=True)
            # Generate Message-ID ourselves so we can store it for future threading
            sent_message_id = make_msgid(domain=settings.smtp_host)
            msg["Message-ID"] = sent_message_id

            # Add threading headers to reply in existing conversation
            if in_reply_to:
                msg["In-Reply-To"] = in_reply_to
                msg["References"] = in_reply_to
            msg.attach(MIMEText(email_body, "plain"))
            
            # Attach DOCX
            with open(docx_path, "rb") as f:
                part = MIMEBase("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={docx_filename}")
                msg.attach(part)
            
            smtp.send_message(msg)
            
            # Save to Gmail Sent folder via IMAP so it shows in Gmail UI
            try:
                import imaplib
                imap = imaplib.IMAP4_SSL("imap.gmail.com")
                imap.login(settings.email_account, settings.email_password)
                imap.select('"[Gmail]/Sent Mail"')
                imap.append(
                    '"[Gmail]/Sent Mail"',
                    "\\Seen",
                    None,
                    msg.as_bytes(),
                )
                imap.logout()
            except Exception as imap_err:
                print(f"Warning: Could not save to Sent folder: {imap_err}")
            
            # Update order status
            order.status = "sent"
            
            # Save to sent_emails table
            sent_email = SentEmail(
                to_email=contact_email,
                subject=subject,
                body=email_body,
                domain_id=domain.id,
                contact_id=order.contact_id,
                message_id=sent_message_id,
                sent_at=datetime.utcnow()
            )
            db.add(sent_email)
            db.commit()
            db.refresh(order)
            
            return {
                "success": True,
                "order_id": order_id,
                "sent_to": contact_email,
                "subject": subject,
                "status": "sent",
                "sent_at": sent_email.sent_at.isoformat()
            }
            
        finally:
            smtp.quit()
            
    except Exception as e:
        db.rollback()
        raise Exception(f"Failed to send email: {str(e)}")


async def send_orders_batch(
    order_ids: List[str],
    db: Session
) -> Dict[str, Any]:
    """
    Send multiple orders in batch.
    
    Args:
        order_ids: List of order IDs
        db: Database session
        
    Returns:
        Dict with success count and any errors
    """
    results = {
        "success": 0,
        "failed": 0,
        "errors": []
    }
    
    for order_id in order_ids:
        try:
            await send_order(order_id, db)
            results["success"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "order_id": order_id,
                "error": str(e)
            })
    
    return results
