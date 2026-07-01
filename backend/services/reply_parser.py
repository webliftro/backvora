"""
Reply Parser Service - Processes incoming email replies using Claude Sonnet.
Extracts contact info, link types, prices, and payment methods.
Auto-populates domain records in BackVora.
"""

import imaplib
import email
import json
import re
import httpx
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parseaddr
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    SentEmail, Domain, Contact, LinkPrice, DomainPaymentMethod, DomainStatus, ContactForm,
    Order, ReceivedEmail,
)

# Track processed sender+domain combos to skip re-parsing
_processed_cache: set[str] = set()


# Canonical mappings for fuzzy matching
LINK_TYPE_ALIASES = {
    # Guest Post variants
    "guest post": "Guest Post",
    "guest article": "Guest Post",
    "blog post": "Guest Post",
    "article": "Guest Post",
    "sponsored post": "Guest Post",
    "sponsored article": "Guest Post",
    "post": "Guest Post",
    "content placement": "Guest Post",
    # Header/Navbar
    "header link": "Header",
    "header": "Header",
    "navigation link": "Navbar",
    "navbar": "Navbar",
    "nav link": "Navbar",
    "menu link": "Navbar",
    "menu tab": "Menu tab",
    "top menu": "Navbar",
    # Footer
    "footer link": "Footer",
    "footer": "Footer",
    # Sidebar
    "sidebar link": "Sidebar",
    "sidebar": "Sidebar",
    "sidebar friends": "Sidebar Friends",
    "blogroll": "Sidebar Friends",
    # Topbar/Toplist
    "topbar": "Topbar",
    "top bar": "Topbar",
    "toplist": "Toplist",
    "top list": "Toplist",
    # Sticky
    "sticky post": "Sticky Post",
    "sticky": "Sticky Post",
    "pinned post": "Sticky Post",
    # Other
    "link insert": "Link Insert",
    "link insertion": "Link Insert",
    "niche edit": "Link Insert",
    "homepage link": "Homepage",
    "homepage": "Homepage",
    "banner": "Banner",
    "model+content tab": "Model+Content tab",
    "model tab": "Model+Content tab",
}

PAYMENT_METHOD_ALIASES = {
    # PayPal
    "paypal": "PayPal",
    "pp": "PayPal",
    # Wire/Bank
    "wire transfer": "Wire Transfer",
    "wire": "Wire Transfer",
    "bank transfer": "Wire Transfer",
    "bank wire": "Wire Transfer",
    "sepa": "Wire Transfer",
    "swift": "Wire Transfer",
    "iban": "Wire Transfer",
    # Crypto
    "crypto": "Crypto",
    "cryptocurrency": "Crypto",
    "bitcoin": "Crypto",
    "btc": "Crypto",
    "usdt": "Crypto",
    "tether": "Crypto",
    "ethereum": "Crypto",
    "eth": "Crypto",
    "litecoin": "Crypto",
    # Paxum
    "paxum": "Paxum",
    # Wise
    "wise": "Wise",
    "transferwise": "Wise",
    # Skrill
    "skrill": "Skrill",
    # Payoneer
    "payoneer": "Payoneer",
}


EXTRACTION_PROMPT = """You are analyzing an email reply from a website owner responding to an advertising/link placement inquiry. Extract structured data from this email.

The email is a reply to our outreach about advertising on their website.

EXISTING LINK TYPES in our system (map to these when possible):
{link_types}

EXISTING PAYMENT METHODS in our system (map to these when possible):
{payment_methods}

EMAIL CONTENT:
---
From: {from_addr}
Subject: {subject}
Domain: {domain}

{body}
---

Extract the following as JSON. Be smart about mapping:
- "Guest Post" includes: article, blog post, sponsored post, content placement, post
- "Header" includes: header link, top navigation link
- "Navbar" includes: navigation link, menu link
- "Footer" includes: footer link, bottom link
- "Sidebar" includes: sidebar link, widget link
- For payment: "Wire Transfer" includes bank transfer, SEPA, SWIFT. "Crypto" includes BTC, USDT, ETH, etc.

If a link type doesn't match any existing type, use the closest match or create a new descriptive name.
For prices, extract the numeric value and determine if it's one-time, monthly, or yearly.

Return ONLY valid JSON:
{{
  "contact_name": "name of person or team (null if not found)",
  "contact_role": "their role if mentioned (null if not found)",
  "contact_email": "their email if different from sender (null if same)",
  "sentiment": "interested|negotiating|rejected|unclear",
  "link_offerings": [
    {{
      "type": "mapped link type name",
      "price": 123.45,
      "currency": "USD",
      "duration": "permanent|monthly|yearly|one-time",
      "duration_months": null,
      "notes": "any extra details"
    }}
  ],
  "payment_methods": ["PayPal", "Wire Transfer"],
  "requires_upfront_payment": true,
  "published_url": "URL of published article if mentioned (null if not found)",
  "additional_domains": ["other domains they mention owning"],
  "email_language": "language the email is written in (e.g. English, Italian, Spanish, etc.)",
  "summary": "one-line summary of the reply"
}}

IMPORTANT for "requires_upfront_payment":
- Set to true if the publisher explicitly asks for payment BEFORE publishing/placing the link
- Set to true if they send wallet addresses or payment details expecting payment first
- Set to false if they say payment after publish, or if payment timing is not mentioned
- Set to false if they're just listing payment methods without demanding upfront payment"""


def decode_str(s):
    if s is None:
        return ""
    parts = decode_header(s)
    result = []
    for data, charset in parts:
        if isinstance(data, bytes):
            result.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(data))
    return " ".join(result)


def extract_body(msg):
    """Extract text body from email."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            if ct == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except:
                    pass
        # Fallback to HTML stripped
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    html = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                    return re.sub(r'<[^>]+>', '', html)
                except:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True)
            if body:
                charset = msg.get_content_charset() or "utf-8"
                text = body.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    return re.sub(r'<[^>]+>', '', text)
                return text
        except:
            pass
    return ""


def map_link_type(raw_type: str) -> str:
    """Map a raw link type string to a canonical type."""
    lower = raw_type.lower().strip()
    if lower in LINK_TYPE_ALIASES:
        return LINK_TYPE_ALIASES[lower]
    # Try partial matching
    for alias, canonical in LINK_TYPE_ALIASES.items():
        if alias in lower or lower in alias:
            return canonical
    # Return as-is with title case
    return raw_type.strip().title()


def map_payment_method(raw_method: str) -> str:
    """Map a raw payment method string to a canonical method."""
    lower = raw_method.lower().strip()
    if lower in PAYMENT_METHOD_ALIASES:
        return PAYMENT_METHOD_ALIASES[lower]
    for alias, canonical in PAYMENT_METHOD_ALIASES.items():
        if alias in lower or lower in alias:
            return canonical
    return raw_method.strip().title()


async def call_sonnet(prompt: str) -> dict:
    """Call Claude Sonnet API for email parsing."""
    api_key = settings.anthropic_api_key if hasattr(settings, 'anthropic_api_key') else None
    if not api_key:
        # Try environment
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    
    if not api_key:
        raise ValueError("No Anthropic API key configured")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.anthropic_model,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        data = response.json()
        text = data["content"][0]["text"]
        
        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError(f"No JSON found in response: {text[:200]}")


def find_domain_for_email(db: Session, from_email: str, subject: str = None) -> Domain | None:
    """Find domain matching an email sender.
    
    Priority:
    1. If subject contains a tracked domain name, use that (most reliable)
    2. Most recent sent email to this address (not arbitrary first match)
    """
    # Priority 1: subject-line domain match (handles same-owner multi-domain correctly)
    if subject:
        all_domains = {d.domain.lower(): d for d in db.query(Domain).all()}
        subject_domains = re.findall(
            r'(?:www\.)?([a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)*\.[a-z]{2,})',
            subject, re.IGNORECASE,
        )
        for subj_domain in subject_domains:
            subj_domain = subj_domain.lower().lstrip("www.")
            if subj_domain in all_domains:
                return all_domains[subj_domain]
    
    # Priority 2: most recent sent email to this address
    sent = db.query(SentEmail).filter(
        SentEmail.to_email == from_email
    ).order_by(SentEmail.sent_at.desc()).first()
    if sent and sent.domain_id:
        return db.query(Domain).filter(Domain.id == sent.domain_id).first()
    
    # Try matching by email domain
    email_domain = from_email.split("@")[-1] if "@" in from_email else None
    if email_domain:
        domain = db.query(Domain).filter(Domain.domain == email_domain).first()
        if domain:
            return domain
        # Try without www
        domain = db.query(Domain).filter(Domain.domain.like(f"%{email_domain}%")).first()
        if domain:
            return domain
    
    return None


def domain_already_processed(db: Session, domain: Domain, from_email: str) -> bool:
    """Check if we already have contact + prices + payment methods for this domain.
    Skip only when ALL three are present. This allows follow-up replies to fill gaps."""
    # Check contact by email OR any contact for this domain
    has_contact = db.query(Contact).filter(
        Contact.domain_id == domain.id,
        (Contact.email == from_email) | (Contact.is_primary == True),
        Contact.deleted_at.is_(None),
    ).first()
    has_prices = db.query(LinkPrice).filter(LinkPrice.domain_id == domain.id).count() > 0
    has_payment = db.query(DomainPaymentMethod).filter(DomainPaymentMethod.domain_id == domain.id).count() > 0
    return bool(has_contact and has_prices and has_payment)


def _get_thread_headers(db: Session, domain_id: str, to_email: str) -> tuple[str, str]:
    """Get In-Reply-To and References for threading with a domain's email conversation.
    Returns (in_reply_to, references) or (None, None) if no prior messages found.
    
    Note: Use get_thread_context() instead when you also need the subject line for proper threading.
    """
    ctx = get_thread_context(db, domain_id, to_email)
    return ctx["in_reply_to"], ctx["references"]


def get_thread_context(db: Session, domain_id: str, to_email: str) -> dict:
    """Get full threading context: In-Reply-To, References, and subject.
    
    Returns dict with:
      - in_reply_to: Message-ID to reply to (or None)
      - references: References header chain (or None)  
      - subject: Subject from the anchor email (or None)
    
    Email clients (especially Gmail) use BOTH headers AND subject to group threads.
    If the subject doesn't match, a new thread is created even with correct headers.
    
    Threading priority:
    1. Most recent RECEIVED email (we're replying to them — this is the strongest thread signal)
    2. Most recent SENT email, but ONLY if there's also at least one received email
       (replying to our own email with no inbound messages creates a new thread in Gmail)
    """
    from datetime import datetime as _dt

    # Fetch most recent received with a real (non-empty) message_id
    last_received = db.query(ReceivedEmail).filter(
        ReceivedEmail.domain_id == domain_id,
        ReceivedEmail.message_id.isnot(None),
        ReceivedEmail.message_id != "",
    ).order_by(ReceivedEmail.received_at.desc()).first()

    # If we have a received email, that's our anchor — we're replying to them
    if last_received:
        # Also check if there's a more recent sent email (we might be continuing a conversation)
        last_sent = db.query(SentEmail).filter(
            SentEmail.domain_id == domain_id,
            SentEmail.message_id.isnot(None),
            SentEmail.message_id != "",
        ).order_by(SentEmail.sent_at.desc()).first()
        
        if last_sent:
            received_time = last_received.received_at or _dt.min
            sent_time = last_sent.sent_at or _dt.min
            anchor = last_received if received_time >= sent_time else last_sent
        else:
            anchor = last_received
        
        mid = anchor.message_id
        subject = getattr(anchor, "subject", None)
        
        # Use the received email's subject for threading (most reliable for Gmail)
        # Even if the sent email is more recent, use the received email's subject
        # because that's what the publisher's email client will thread on
        received_subject = getattr(last_received, "subject", None)
        if received_subject:
            subject = received_subject
        
        return {"in_reply_to": mid, "references": mid, "subject": subject}
    
    # No received emails — no real thread exists yet
    # Don't return our own sent email as a thread anchor (creates new thread in Gmail)
    return {"in_reply_to": None, "references": None, "subject": None}


async def process_reply(db: Session, msg_id: bytes, mail_conn, domain: Domain, received_email=None) -> dict:
    """Process a single email reply: parse with Sonnet and update domain."""
    status, msg_data = mail_conn.fetch(msg_id, "(BODY.PEEK[] FLAGS)")
    if status != "OK":
        return {"error": "Failed to fetch email"}
    
    raw = msg_data[0][1]
    msg = email.message_from_bytes(raw)
    
    from_addr = decode_str(msg.get("From", ""))
    _, from_email_addr = parseaddr(from_addr)
    subject = decode_str(msg.get("Subject", ""))
    body = extract_body(msg)
    
    if not body.strip():
        return {"error": "Empty email body"}
    
    # Extract Message-ID for threading
    original_message_id = msg.get("Message-ID", "").strip()
    original_references = msg.get("References", "").strip()
    
    # Build references chain for replies
    if original_references and original_message_id:
        reply_references = f"{original_references} {original_message_id}".strip()
    elif original_message_id:
        reply_references = original_message_id
    else:
        # Fallback: look up previous thread headers from DB
        reply_to, reply_refs = _get_thread_headers(db, domain.id, from_email_addr)
        original_message_id = reply_to
        reply_references = reply_refs
    
    # Update received_email with body text and message-id if provided
    if received_email:
        received_email.body_text = body[:10000]
        received_email.subject = subject[:500]
        received_email.message_id = original_message_id
    
    # Get existing link types and payment methods for context
    existing_types = [lp.link_type for lp in db.query(LinkPrice.link_type).distinct().all()]
    existing_payments = [pm.method for pm in db.query(DomainPaymentMethod.method).distinct().all()]
    
    # Build prompt
    prompt = EXTRACTION_PROMPT.format(
        link_types=", ".join(existing_types) if existing_types else "Guest Post, Header, Footer, Sidebar, Navbar",
        payment_methods=", ".join(existing_payments) if existing_payments else "PayPal, Wire Transfer, Crypto, Paxum",
        from_addr=from_addr,
        subject=subject,
        domain=domain.domain,
        body=body[:3000],  # Limit body length
    )
    
    # Call Sonnet
    parsed = await call_sonnet(prompt)
    
    # Update received_email with parsed data
    if received_email:
        received_email.parsed_data = parsed
        received_email.processing_status = "processed"
    
    # Parse email date for timeline-based logic
    _email_date = None
    _email_date_str = msg.get("Date", "")
    if _email_date_str:
        try:
            from email.utils import parsedate_to_datetime as _pdt
            _email_date = _pdt(_email_date_str)
        except:
            pass
    
    # Apply extracted data to domain
    results = {"domain": domain.domain, "parsed": parsed, "actions": [], "email_date": _email_date}
    
    # 1. Update contact info on domain
    if parsed.get("contact_name"):
        domain.owner = parsed["contact_name"]
        results["actions"].append(f"Set owner: {parsed['contact_name']}")
    
    contact_email = parsed.get("contact_email") or from_email_addr
    if contact_email and contact_email != domain.email:
        domain.email = contact_email
        results["actions"].append(f"Set email: {contact_email}")
    
    # 2. Create/update Contact record
    existing_contact = db.query(Contact).filter(
        Contact.domain_id == domain.id,
        Contact.email == contact_email,
        Contact.deleted_at.is_(None),
    ).first()
    
    new_contact = None
    if not existing_contact and contact_email:
        new_contact = Contact(
            domain_id=domain.id,
            email=contact_email,
            name=parsed.get("contact_name"),
            role=parsed.get("contact_role"),
            source_type="email_reply",
            is_primary=True,
        )
        db.add(new_contact)
        results["actions"].append(f"Created contact: {contact_email}")
        
        # Unset other primaries
        db.query(Contact).filter(
            Contact.domain_id == domain.id,
            Contact.email != contact_email,
            Contact.deleted_at.is_(None),
        ).update({"is_primary": False})
    elif existing_contact:
        if parsed.get("contact_name") and not existing_contact.name:
            existing_contact.name = parsed["contact_name"]
        if parsed.get("contact_role") and not existing_contact.role:
            existing_contact.role = parsed["contact_role"]
        if not existing_contact.is_primary:
            existing_contact.is_primary = True
            db.query(Contact).filter(
                Contact.domain_id == domain.id,
                Contact.id != existing_contact.id,
                Contact.deleted_at.is_(None),
            ).update({"is_primary": False})
        results["actions"].append(f"Updated contact: {contact_email}")
    
    # Link received_email to contact
    if received_email:
        if existing_contact:
            received_email.contact_id = existing_contact.id
        elif new_contact:
            db.flush()  # Get the new contact ID
            received_email.contact_id = new_contact.id
    
    # 3. Add link prices
    for offering in parsed.get("link_offerings", []):
        link_type = map_link_type(offering.get("type", ""))
        price = offering.get("price")
        if not link_type or price is None:
            continue
        
        currency = offering.get("currency", "USD")
        duration = offering.get("duration", "one-time")
        duration_months = offering.get("duration_months")
        is_permanent = duration in ("permanent", "one-time")
        
        if duration == "yearly":
            duration_months = 12
        elif duration == "monthly":
            duration_months = 1
        
        # Check if this link type already exists for domain
        existing_price = db.query(LinkPrice).filter(
            LinkPrice.domain_id == domain.id,
            LinkPrice.link_type == link_type,
        ).first()
        
        if existing_price:
            existing_price.price = price
            existing_price.currency = currency
            existing_price.duration_months = duration_months
            existing_price.is_permanent = is_permanent
            existing_price.notes = offering.get("notes", "")
            results["actions"].append(f"Updated price: {link_type} = {price} {currency}")
        else:
            db.add(LinkPrice(
                domain_id=domain.id,
                link_type=link_type,
                price=price,
                currency=currency,
                duration_months=duration_months,
                is_permanent=is_permanent,
                notes=offering.get("notes", ""),
            ))
            results["actions"].append(f"Added price: {link_type} = {price} {currency}")
    
    # 4. Add payment methods
    for method_raw in parsed.get("payment_methods", []):
        method = map_payment_method(method_raw)
        existing_pm = db.query(DomainPaymentMethod).filter(
            DomainPaymentMethod.domain_id == domain.id,
            DomainPaymentMethod.method == method,
        ).first()
        if not existing_pm:
            db.add(DomainPaymentMethod(
                domain_id=domain.id,
                method=method,
                is_preferred=False,
            ))
            results["actions"].append(f"Added payment method: {method}")
    
    # 4b. Handle upfront payment demands — auto-negotiate up to 3 times
    # SKIP if domain already has an active order (sent/content_ready/live) — we're past negotiation
    # SKIP if domain explicitly accepts upfront payment (e.g. PayPal buyer protection agreed)
    active_order_statuses = {"sent", "content_ready", "live"}
    has_active_order = db.query(Order).filter(
        Order.domain_id == domain.id,
        Order.status.in_(active_order_statuses),
        Order.deleted_at.is_(None),
    ).first() is not None

    accepts_upfront = getattr(domain, "accepts_upfront_payment", False)

    if has_active_order:
        results["actions"].append("Skipped no-upfront reply: domain has an active order (delivery mode, not negotiation)")
    if accepts_upfront:
        results["actions"].append("Skipped no-upfront reply: domain marked as accepts_upfront_payment")

    if parsed.get("requires_upfront_payment") and contact_email and not has_active_order and not accepts_upfront:
        # Count how many no-upfront replies we've already sent
        upfront_replies_count = db.query(SentEmail).filter(
            SentEmail.domain_id == domain.id,
            SentEmail.body.like("%(auto no-upfront%"),
        ).count()
        
        # Get our last no-upfront reply (if any)
        last_upfront_sent = db.query(SentEmail).filter(
            SentEmail.domain_id == domain.id,
            SentEmail.body.like("%(auto no-upfront%"),
        ).order_by(SentEmail.sent_at.desc()).first()
        
        # Get the timestamp of the incoming email we're processing
        incoming_date = results.get("email_date")
        
        # RULE: Only escalate if this email was sent AFTER our last no-upfront reply.
        # If they sent multiple emails before we even responded, treat as one request.
        # If they don't respond or agree, we wait. Only push back if they explicitly
        # disagree after receiving our no-upfront message.
        template_key = None
        
        if last_upfront_sent:
            if incoming_date and incoming_date < last_upfront_sent.sent_at:
                # Their email predates our reply — not a new pushback, skip
                results["actions"].append("Skipped no-upfront reply (their email predates our last no-upfront reply)")
            elif upfront_replies_count == 1:
                # They pushed back after our first attempt — try PayPal compromise
                template_key = "no_upfront_2"
            elif upfront_replies_count == 2:
                # Third and final: graceful walkaway
                template_key = "no_upfront_final"
            elif upfront_replies_count >= 3:
                results["actions"].append("Upfront payment negotiation already exhausted (3 attempts). Skipping.")
        else:
            # No previous no-upfront reply sent — this is the first time
            template_key = "no_upfront_1"

        if template_key:
                try:
                    from ..config import settings as _settings
                    name = parsed.get("contact_name") or "there"
                    reply_body = FOLLOWUP_TEMPLATES[template_key].format(
                        name=name,
                        domain=domain.domain,
                        paypal_address=_settings.paypal_address,
                    )
                    await send_followup_custom(
                        contact_email,
                        domain.domain,
                        name,
                        reply_body,
                        domain_id=domain.id,
                        db=db,
                        log_body=f"(auto no-upfront reply #{upfront_replies_count + 1}: {template_key})",
                        in_reply_to=original_message_id,
                        references=reply_references,
                    )
                    domain.status = DomainStatus.NEGOTIATING
                    db.commit()
                    results["actions"].append(
                        f"Auto no-upfront reply #{upfront_replies_count + 1} sent to {contact_email} ({template_key})"
                    )

                    # If this was the final attempt, flag for human review
                    if template_key == "no_upfront_final":
                        results["actions"].append("NOTIFY_OWNER: Publisher insists on upfront payment after 3 negotiations. Manual review needed.")
                        try:
                            from .slack_notifier import send_slack_alert
                            await send_slack_alert("UPFRONT_PAYMENT_DEADLOCK", None, domain, extra={
                                "contact": contact_email,
                                "attempts": upfront_replies_count + 1,
                                "note": "Publisher insists on upfront payment. All auto-negotiation attempts exhausted.",
                            })
                        except Exception:
                            pass  # Slack is best-effort
                except Exception as e:
                    results["actions"].append(f"Failed to send no-upfront reply: {e}")
        elif upfront_replies_count >= 3:
            results["actions"].append("Upfront payment negotiation already exhausted (3 attempts). Skipping.")

    # 4c. Auto-detect language from email and set on domain if not already set
    detected_lang = parsed.get("email_language")
    if detected_lang and detected_lang.lower() != "english" and (not domain.language or domain.language == "English"):
        domain.language = detected_lang.title()
        results["actions"].append(f"Auto-detected language: {detected_lang}")

    # 5. Update domain status based on sentiment
    sentiment = parsed.get("sentiment", "unclear")
    if sentiment == "interested" and domain.status.value in ("new", "analyzed", "contacted"):
        domain.status = DomainStatus.REPLIED
        results["actions"].append("Status → replied")
    elif sentiment == "negotiating":
        domain.status = DomainStatus.NEGOTIATING
        results["actions"].append("Status → negotiating")
    elif sentiment == "rejected":
        domain.status = DomainStatus.REJECTED
        results["actions"].append("Status → rejected")
        # Send graceful decline if we previously sent a counter-offer
        if contact_email:
            prev_counter = db.query(SentEmail).filter(
                SentEmail.domain_id == domain.id,
                SentEmail.body.like("%(auto counter-offer%"),
            ).first()
            prev_decline = db.query(SentEmail).filter(
                SentEmail.domain_id == domain.id,
                SentEmail.body.like("%(graceful decline)%"),
            ).first()
            if prev_counter and not prev_decline:
                try:
                    name = parsed.get("contact_name") or "there"
                    await send_followup_custom(
                        contact_email,
                        domain.domain,
                        name,
                        FOLLOWUP_TEMPLATES["graceful_decline"].format(
                            name=name,
                            domain=domain.domain,
                        ),
                        domain_id=domain.id,
                        db=db,
                        log_body="(graceful decline)",
                        in_reply_to=original_message_id,
                        references=reply_references,
                    )
                    db.commit()
                    results["actions"].append("Sent graceful decline (keeping door open)")
                except Exception as e:
                    results["actions"].append(f"Failed to send graceful decline: {e}")
    elif domain.status.value == "contacted":
        domain.status = DomainStatus.REPLIED
        results["actions"].append("Status → replied")
    
    db.commit()
    
    # Auto-negotiate: check if any prices are overpriced and counter-offer
    from .pricing import evaluate_asking_price
    counter_sent_this_cycle = False
    
    for offering in parsed.get("link_offerings", []):
        link_type = map_link_type(offering.get("type", ""))
        price = offering.get("price")
        if not link_type or not price or price <= 0:
            continue
        
        dr = domain.domain_rating or 0
        traffic = domain.organic_traffic or 0
        if dr <= 0 or traffic <= 0:
            continue
        
        evaluation = evaluate_asking_price(db, dr, traffic, price, link_type, domain.domain)
        
        if evaluation["action"] == "counter" and contact_email:
            counter = evaluation["counter_offer"]
            # Check we haven't already sent a counter for this domain recently
            recent_counter = db.query(SentEmail).filter(
                SentEmail.domain_id == domain.id,
                SentEmail.body.like("%(auto counter-offer%"),
                SentEmail.sent_at > datetime.utcnow() - timedelta(days=7),
            ).first()
            
            if not recent_counter:
                # Check IMAP Sent folder — maybe R already replied manually
                if _check_imap_sent_recently(contact_email, domain.domain, days=3):
                    results["actions"].append(f"Skipped counter-offer for {link_type} ${price}: recent manual email found in Sent folder")
                    continue
                try:
                    name = parsed.get("contact_name") or "there"
                    await send_followup_custom(
                        contact_email,
                        domain.domain,
                        name,
                        FOLLOWUP_TEMPLATES["counter_offer"].format(
                            name=name,
                            domain=domain.domain,
                            counter_offer=int(counter),
                            link_type=link_type,
                        ),
                        domain_id=domain.id,
                        db=db,
                        log_body=f"(auto counter-offer: {link_type} ${price} → ${counter})",
                        in_reply_to=original_message_id,
                        references=reply_references,
                    )
                    domain.status = DomainStatus.NEGOTIATING
                    db.commit()
                    counter_sent_this_cycle = True
                    results["actions"].append(
                        f"Auto counter-offer: {link_type} ${price} → ${int(counter)} "
                        f"(fair: ${evaluation['fair_price']}, verdict: {evaluation['verdict']})"
                    )
                except Exception as e:
                    results["actions"].append(f"Failed to send counter-offer: {e}")
        elif evaluation["action"] == "accept":
            results["actions"].append(
                f"Price OK: {link_type} ${price} (fair: ${evaluation['fair_price']}, {evaluation['verdict']})"
            )
    
    # --- Auto-verification: detect published URLs in the reply ---
    # Only scan the NEW part of the reply — strip quoted text (lines starting with ">",
    # and everything after common quote markers like "On ... wrote:" or "-----Original Message-----")
    reply_body_only = re.split(r'\n[>\-]{2}|On .+wrote:|-----Original Message-----|_{5,}', body, maxsplit=1)[0]
    url_pattern = re.findall(r'https?://[^\s<>"\']+', reply_body_only)
    publisher_domain = domain.domain.lower().replace("www.", "")
    published_urls = [u for u in url_pattern if publisher_domain in u.lower()]

    if published_urls:
        # Check if there's an active order for this domain (sent, paid, or content_ready)
        sent_orders = db.query(Order).filter(
            Order.domain_id == domain.id,
            Order.status.in_(["sent", "paid", "content_ready", "payment_sent"]),
        ).all()

        for sent_order in sent_orders:
            pub_url = published_urls[0]  # Use first matching URL
            try:
                from .link_monitor import verify_live_url
                from .slack_notifier import send_slack_alert
                from urllib.parse import urlparse

                vresult = await verify_live_url(sent_order.id, pub_url, db, auto_update_status=True)
                results["actions"].append(f"Auto-verified {pub_url}: {vresult['status']}")

                if vresult["verified"]:
                    # Get payment info for slack
                    pm = db.query(DomainPaymentMethod).filter(
                        DomainPaymentMethod.domain_id == domain.id,
                    ).first()
                    payment_info = f"{pm.method}: {pm.details}" if pm and pm.details else (pm.method if pm else "")
                    await send_slack_alert("VERIFIED", sent_order, domain, extra={
                        "url": pub_url,
                        "payment_info": payment_info,
                    })
                else:
                    # Auto-email publisher about issues — but only for real link problems,
                    # not HTTP errors (403/429/503 = bot protection, not a publisher mistake)
                    # and not infrastructure/browser errors (our problem, not theirs)
                    INTERNAL_ISSUE_PATTERNS = {
                        'BROWSER_ERROR', 'VERIFICATION_ERROR', 'NOT_LIVE',
                    }
                    actionable_issues = [
                        i for i in (vresult.get("issues") or [])
                        if not re.match(r'^HTTP \d{3}$', i.strip())
                        and i.strip() not in INTERNAL_ISSUE_PATTERNS
                        and not any(kw in i.lower() for kw in [
                            'browser', 'playwright', 'chromium', 'failed to load',
                            'timeout', 'connection refused', 'agent-browser',
                            'unexpected error', 'automation failed',
                        ])
                    ]
                    parsed_pub = urlparse(pub_url)
                    is_homepage_url = parsed_pub.path in ("", "/")
                    if contact_email and actionable_issues:
                        if is_homepage_url and any("target url" in i.lower() for i in actionable_issues):
                            results["actions"].append("Skipped fix request: publication URL looks like homepage, waiting for exact article URL")
                            await send_slack_alert(vresult["status"], sent_order, domain, extra={
                                "url": pub_url,
                                "issues_text": "; ".join(vresult.get("issues", [])),
                            })
                            break
                        # Cooldown: don't send if we already sent a fix request in the last 3 days
                        recent_fix = db.query(SentEmail).filter(
                            SentEmail.domain_id == domain.id,
                            SentEmail.body.like("%(auto fix request%"),
                            SentEmail.sent_at > datetime.utcnow() - timedelta(days=3),
                        ).first()
                        if recent_fix:
                            results["actions"].append(f"Skipped fix request (sent {recent_fix.sent_at.strftime('%Y-%m-%d')} — cooldown active)")
                        else:
                            try:
                                c_name = parsed.get("contact_name") or "there"
                                await send_verification_fix_request(
                                    contact_email, domain.domain, c_name, actionable_issues,
                                    domain_id=domain.id, db=db,
                                    in_reply_to=original_message_id,
                                    references=reply_references,
                                )
                                db.commit()
                                results["actions"].append(f"Sent fix request email for: {vresult['status']}")
                                await send_slack_alert("AUTO_FIX_EMAIL_SENT", sent_order, domain, extra={
                                    "issues_text": "; ".join(actionable_issues),
                                })
                            except Exception as e:
                                results["actions"].append(f"Failed to send fix request: {e}")
                    elif vresult.get("issues"):
                        results["actions"].append(f"Skipped fix request (HTTP error only: {'; '.join(vresult['issues'])})")

                    await send_slack_alert(vresult["status"], sent_order, domain, extra={
                        "url": pub_url,
                        "issues_text": "; ".join(vresult.get("issues", [])),
                    })

            except Exception as e:
                results["actions"].append(f"Auto-verification failed: {e}")
            break  # Only verify first matching order

    # Auto-follow-ups based on what's missing
    # Skip if we just sent a counter-offer — don't send contradictory emails
    if counter_sent_this_cycle:
        results["actions"].append("Skipped follow-up (counter-offer already sent this cycle)")
        return results
    
    has_prices_now = len(parsed.get("link_offerings", [])) > 0
    has_payment_now = len(parsed.get("payment_methods", [])) > 0
    no_payment_in_db = db.query(DomainPaymentMethod).filter(
        DomainPaymentMethod.domain_id == domain.id
    ).count() == 0
    no_prices_in_db = db.query(LinkPrice).filter(
        LinkPrice.domain_id == domain.id,
        LinkPrice.deleted_at.is_(None),
    ).count() == 0
    
    sentiment = parsed.get("sentiment", "").lower()
    is_interested = sentiment in ("positive", "interested", "neutral", "negotiating")
    
    # Check we haven't already sent a follow-up recently (avoid spam)
    recent_followup = db.query(SentEmail).filter(
        SentEmail.domain_id == domain.id,
        SentEmail.body.like("%(auto follow-up%"),
        SentEmail.sent_at > datetime.utcnow() - timedelta(days=3),
    ).first()
    
    if not recent_followup and contact_email:
        followup_type = None
        
        has_prices_in_db = not no_prices_in_db
        
        if not has_prices_now and no_prices_in_db and is_interested:
            # Interested but no pricing at all → ask for rates
            followup_type = "pricing"
        elif (has_prices_now or has_prices_in_db) and not has_payment_now and no_payment_in_db and is_interested:
            # Has prices (either in this email or already in DB) but no payment methods → ask how to pay
            followup_type = "payment"
        
        if followup_type:
            # Check IMAP Sent folder — maybe R already replied manually
            if _check_imap_sent_recently(contact_email, domain.domain, days=3):
                results["actions"].append(f"Skipped {followup_type} follow-up: recent manual email found in Sent folder")
                return results
            try:
                await send_followup(contact_email, domain.domain, parsed.get("contact_name"), followup_type,
                                   domain_id=domain.id, db=db,
                                   in_reply_to=original_message_id,
                                   references=reply_references)
                db.commit()
                results["actions"].append(f"Auto-sent {followup_type} inquiry to {contact_email}")
            except Exception as e:
                results["actions"].append(f"Failed to send {followup_type} follow-up: {e}")
    
    return results


async def send_verification_fix_request(
    to_email: str, domain_name: str, contact_name: str, issues: list[str],
    domain_id: str = None, db: Session = None, in_reply_to: str = None, references: str = None,
):
    """
    Send a polite email listing verification issues that need fixing.
    Each issue string should be human-readable (e.g. "Link #2: anchor should be 'cam sites' but found 'click here'").
    """
    name = contact_name or "there"
    bullet_list = "\n".join(f"  • {issue}" for issue in issues)

    body = f"""Hi {name},

Thanks so much for publishing the article on {domain_name}! I noticed a couple of small things that need adjusting:

{bullet_list}

Could you please update these when you get a chance? Once everything looks good, payment will follow right away.

Thanks again for the great work!

Best,
Tony"""

    # Use thread subject if available
    subject = f"Re: Guest Post on {domain_name} — small fixes needed"
    if domain_id and db:
        ctx = get_thread_context(db, domain_id, to_email)
        if ctx["subject"]:
            thread_subj = ctx["subject"]
            subject = thread_subj if thread_subj.lower().startswith("re:") else f"Re: {thread_subj}"
        if not in_reply_to:
            in_reply_to = ctx["in_reply_to"]
            references = ctx["references"]

    _send_email_smtp(
        to_email,
        subject,
        body,
        domain_id=domain_id,
        db=db,
        log_body=f"(auto fix request: {'; '.join(issues)})",
        in_reply_to=in_reply_to,
        references=references,
    )


FOLLOWUP_TEMPLATES = {
    "pricing": """Hi {name},

Thanks for getting back to us! We're interested in advertising on {domain}.

Could you share your rates for the available options? We're open to guest posts, link placements, banners, or other advertising formats you offer.

Looking forward to hearing from you.

Best,
Tony""",

    "payment": """Hi {name},

Thanks for the pricing details! That all sounds great.

Could you let me know which payment methods you accept? (PayPal, wire transfer, crypto, etc.)

Best,
Tony""",

    "counter_offer": """Hi {name},

Thanks for the rates on {domain}! We're definitely interested in working together.

Based on our budget and the current market for similar placements, we'd be looking at around ${counter_offer} for a {link_type}. Would that work for you?

Let me know and we can move forward.

Best,
Tony""",

    "graceful_decline": """Hi {name},

No worries at all, totally understand! If anything changes down the road or you'd like to revisit, we'd love to work something out.

Thanks for your time and keep up the great work on {domain}.

Best,
Tony""",

    "no_upfront_1": """Hi {name},

Thanks for the details! We're definitely keen to work together on {domain}.

Just to clarify our process: we handle payment immediately after the article/link goes live. We've found this works well for both sides and we always pay promptly once everything's up.

Would that work for you? Happy to move forward as soon as we're aligned on this.

Best,
Tony""",

    "no_upfront_2": """Hi {name},

I totally understand your position. Just to reassure you, we have a solid track record of paying publishers promptly after publication.

Would you be open to a compromise? We could do payment via PayPal with buyer protection, which gives you full recourse if anything goes sideways. You can send the invoice to our PayPal address: {paypal_address}

Let me know what you think!

Best,
Tony""",

    "no_upfront_final": """Hi {name},

I appreciate you taking the time to discuss this. Unfortunately, upfront payment isn't something we're able to do on our end.

If you change your mind or would like to try the post-publication payment approach in the future, we'd love to work with you. The door's always open.

Thanks again for your time, and keep up the great work on {domain}!

Best,
Tony""",
}


def _check_imap_sent_recently(to_email: str, domain_name: str, days: int = 3) -> bool:
    """Check IMAP Sent folder for recent REPLY emails to this address.
    Only matches 'Re:' subjects to avoid false positives from article deliveries.
    Returns True if a recent reply was found (meaning we should NOT send)."""
    try:
        mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
        mail.login(settings.email_account, settings.email_password)
        # Try common Sent folder names
        for folder in ['"[Gmail]/Sent Mail"', "Sent", "INBOX.Sent"]:
            status, _ = mail.select(folder, readonly=True)
            if status == "OK":
                break
        else:
            mail.logout()
            return False
        
        since_date = (datetime.utcnow() - timedelta(days=days)).strftime("%d-%b-%Y")
        
        # Search for REPLY emails (Re: subject) to this address since the date
        # This avoids matching article delivery emails which have different subjects
        _, msg_nums = mail.search(None, f'(SINCE {since_date} TO "{to_email}" SUBJECT "Re:")')
        if msg_nums[0]:
            mail.logout()
            return True
        mail.logout()
        return False
    except Exception as e:
        print(f"IMAP sent check error: {e}")
        return False


def _send_email_smtp(to_email: str, subject: str, body: str, domain_id: str = None, db: Session = None, log_body: str = None, in_reply_to: str = None, references: str = None):
    """Centralized email sending. Always logs to sent_emails if db is provided.
    log_body: what to store in sent_emails.body (defaults to actual body if not set).
    in_reply_to: Message-ID we're replying to (sets In-Reply-To header).
    references: Space-separated Message-IDs for References header (thread chain).
    If in_reply_to is not provided but domain_id + db are, auto-fetches thread context
    (headers + subject) so all outbound emails land in the existing conversation thread."""
    # Auto-thread: if no explicit headers but we have a domain + db, look up the thread
    if not in_reply_to and domain_id and db:
        ctx = get_thread_context(db, domain_id, to_email)
        in_reply_to = ctx["in_reply_to"]
        references = ctx["references"]
        # Override subject with the thread's subject to stay in the same thread
        if ctx["subject"]:
            thread_subj = ctx["subject"]
            subject = thread_subj if thread_subj.lower().startswith("re:") else f"Re: {thread_subj}"
    import smtplib
    import ssl as _ssl
    from email.mime.text import MIMEText as _MIMEText
    from email.mime.multipart import MIMEMultipart as _MIMEMultipart
    from email.utils import formatdate as _formatdate, make_msgid as _make_msgid

    context = _ssl.create_default_context()
    smtp = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context)
    smtp.login(settings.email_account, settings.email_password)

    try:
        msg = _MIMEMultipart()
        msg["From"] = settings.email_account
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Date"] = _formatdate(localtime=True)
        # Generate Message-ID ourselves so we can store it for future threading
        sent_message_id = _make_msgid(domain=settings.smtp_host)
        msg["Message-ID"] = sent_message_id
        
        # Set threading headers if provided
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references
        
        msg.attach(_MIMEText(body, "plain"))
        smtp.send_message(msg)

        # Save to Gmail Sent folder so it shows in Gmail UI
        try:
            import imaplib as _imaplib
            imap = _imaplib.IMAP4_SSL("imap.gmail.com")
            imap.login(settings.email_account, settings.email_password)
            imap.append('"[Gmail]/Sent Mail"', "\\Seen", None, msg.as_bytes())
            imap.logout()
        except Exception as _imap_err:
            print(f"Warning: could not save to Gmail Sent folder: {_imap_err}")
    finally:
        smtp.quit()

    # Always log to sent_emails if we have a db session
    if db is not None:
        db.add(SentEmail(
            to_email=to_email,
            subject=subject,
            body=log_body or body,
            domain_id=domain_id,
            sent_at=datetime.utcnow(),
            message_id=sent_message_id,
        ))
        db.flush()


async def send_followup(to_email: str, domain_name: str, contact_name: str | None, followup_type: str, domain_id: str = None, db: Session = None, in_reply_to: str = None, references: str = None):
    """Send a follow-up email based on type (pricing, payment, etc.)."""
    name = contact_name or "there"
    template = FOLLOWUP_TEMPLATES.get(followup_type, FOLLOWUP_TEMPLATES["pricing"])
    body = template.format(name=name, domain=domain_name)
    
    # Use thread subject if available, otherwise fall back to generic
    subject = f"Re: Advertising on {domain_name}"
    if domain_id and db:
        ctx = get_thread_context(db, domain_id, to_email)
        if ctx["subject"]:
            thread_subj = ctx["subject"]
            subject = thread_subj if thread_subj.lower().startswith("re:") else f"Re: {thread_subj}"
        if not in_reply_to:
            in_reply_to = ctx["in_reply_to"]
            references = ctx["references"]
    
    _send_email_smtp(
        to_email,
        subject,
        body,
        domain_id=domain_id,
        db=db,
        log_body=f"(auto follow-up: {followup_type} inquiry)",
        in_reply_to=in_reply_to,
        references=references,
    )


async def send_followup_custom(to_email: str, domain_name: str, contact_name: str, body: str, domain_id: str = None, db: Session = None, log_body: str = None, in_reply_to: str = None, references: str = None):
    """Send a custom follow-up email (for counter-offers, etc.)."""
    # Use thread subject if available, otherwise fall back to generic
    subject = f"Re: Advertising on {domain_name}"
    if domain_id and db:
        ctx = get_thread_context(db, domain_id, to_email)
        if ctx["subject"]:
            thread_subj = ctx["subject"]
            subject = thread_subj if thread_subj.lower().startswith("re:") else f"Re: {thread_subj}"
        if not in_reply_to:
            in_reply_to = ctx["in_reply_to"]
            references = ctx["references"]
    
    _send_email_smtp(
        to_email,
        subject,
        body,
        domain_id=domain_id,
        db=db,
        log_body=log_body,
        in_reply_to=in_reply_to,
        references=references,
    )


def _mark_as_read(msg_id: bytes):
    """Mark an IMAP message as read."""
    try:
        mail2 = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
        mail2.login(settings.email_account, settings.email_password)
        mail2.select("INBOX")
        mail2.store(msg_id, '+FLAGS', '\\Seen')
        mail2.logout()
    except Exception as e:
        print(f"Warning: failed to mark message as read: {e}")


async def _handle_publication_confirmation(
    db: Session, domain: Domain, received_email, email_body: str,
    classified_url: str | None, from_email: str,
    message_id: str, references: str, summary: str,
) -> dict:
    """Handle a publication_confirmation email: verify backlink + update order status."""
    from .link_monitor import verify_live_url
    from .slack_notifier import send_slack_alert
    from urllib.parse import urlparse

    result = {"domain": domain.domain, "classification": "publication_confirmation", "actions": [], "summary": summary}

    # Find the published URL — prefer the classifier's extracted URL, fallback to body scan
    pub_url = classified_url
    if not pub_url:
        publisher_domain = domain.domain.lower().replace("www.", "")
        urls = re.findall(r'https?://[^\s<>"\']+', email_body)
        matching = [u for u in urls if publisher_domain in u.lower()]
        pub_url = matching[0] if matching else None

    if not pub_url:
        # No URL found — escalate
        await _escalate_to_slack(
            db, domain, from_email, received_email.subject, summary,
            "publication_confirmation", 0.7, "Publisher says article is live but no URL found. Ask for URL.",
        )
        received_email.processing_status = "escalated"
        received_email.processing_notes = f"Publication confirmation but no URL found — escalated"
        result["actions"].append("Escalated: no URL found in publication confirmation")
        return result

    # Find active orders for this domain
    active_orders = db.query(Order).filter(
        Order.domain_id == domain.id,
        Order.status.in_(["sent", "content_ready", "payment_sent"]),
        Order.deleted_at.is_(None),
    ).all()

    if not active_orders:
        # No active order — still log the URL and escalate
        await _escalate_to_slack(
            db, domain, from_email, received_email.subject, summary,
            "publication_confirmation", 0.8,
            f"Publisher confirmed publication at {pub_url} but no active order found.",
        )
        received_email.processing_status = "escalated"
        received_email.processing_notes = f"Publication confirmed ({pub_url}) but no active order"
        result["actions"].append(f"Escalated: URL {pub_url} but no active order")
        return result

    # Verify the backlink on the first matching order
    order = active_orders[0]
    try:
        vresult = await verify_live_url(order.id, pub_url, db, auto_update_status=True)
        result["actions"].append(f"Verified {pub_url}: {vresult['status']}")

        if vresult.get("verified"):
            order.status = "live"
            order.live_url = pub_url
            order.live_at = datetime.utcnow()
            received_email.processing_status = "processed"
            received_email.processing_notes = f"Publication confirmed + verified: {pub_url}"
            result["actions"].append(f"Order status → published")

            pm = db.query(DomainPaymentMethod).filter(
                DomainPaymentMethod.domain_id == domain.id,
            ).first()
            payment_info = f"{pm.method}: {pm.details}" if pm and pm.details else (pm.method if pm else "")
            await send_slack_alert("VERIFIED", order, domain, extra={
                "url": pub_url,
                "payment_info": payment_info,
            })
        else:
            # Verification found issues — send fix request
            # Filter out infrastructure/browser errors (our problem, not the publisher's)
            actionable_issues = [
                i for i in (vresult.get("issues") or [])
                if not re.match(r'^HTTP \d{3}$', i.strip())
                and i.strip() not in {'BROWSER_ERROR', 'VERIFICATION_ERROR', 'NOT_LIVE'}
                and not any(kw in i.lower() for kw in [
                    'browser', 'playwright', 'chromium', 'failed to load',
                    'timeout', 'connection refused', 'agent-browser',
                    'unexpected error', 'automation failed',
                ])
            ]
            parsed_pub = urlparse(pub_url)
            is_homepage_url = parsed_pub.path in ("", "/")
            if actionable_issues:
                if is_homepage_url and any("target url" in i.lower() for i in actionable_issues):
                    received_email.processing_status = "processed"
                    received_email.processing_notes = f"Homepage URL shared ({pub_url}); waiting for exact article URL"
                    result["actions"].append("Skipped fix request: homepage URL likely not article permalink")
                    await send_slack_alert(vresult["status"], order, domain, extra={
                        "url": pub_url,
                        "issues_text": "; ".join(vresult.get("issues", [])),
                    })
                    return result
                contact = db.query(Contact).filter(
                    Contact.domain_id == domain.id,
                    Contact.is_primary == True,
                ).first()
                contact_email = contact.email if contact else from_email
                try:
                    await send_verification_fix_request(
                        contact_email, domain.domain, contact.name if contact else "there",
                        actionable_issues, domain_id=domain.id, db=db,
                        in_reply_to=message_id, references=references,
                    )
                    result["actions"].append(f"Sent fix request: {'; '.join(actionable_issues)}")
                except Exception as e:
                    result["actions"].append(f"Failed to send fix request: {e}")

            received_email.processing_status = "processed"
            received_email.processing_notes = f"Publication confirmed but verification issues: {vresult['status']}"

            await send_slack_alert(vresult["status"], order, domain, extra={
                "url": pub_url,
                "issues_text": "; ".join(vresult.get("issues", [])),
            })
    except Exception as e:
        result["actions"].append(f"Verification failed: {e}")
        received_email.processing_status = "error"
        received_email.processing_notes = f"Publication confirmation verification error: {e}"

    return result


async def _handle_payment_receipt(
    db: Session, domain: Domain, received_email, summary: str,
) -> dict:
    """Handle a payment_receipt email: update order payment status."""
    from .slack_notifier import send_slack_alert

    result = {"domain": domain.domain, "classification": "payment_receipt", "actions": [], "summary": summary}

    # Find orders awaiting payment confirmation
    orders = db.query(Order).filter(
        Order.domain_id == domain.id,
        Order.status.in_(["live", "payment_sent"]),
        Order.deleted_at.is_(None),
    ).all()

    if orders:
        for order in orders:
            order.paid_at = datetime.utcnow()
            # If status is payment_sent, move to published (payment confirmed)
            # If status is published, payment is now confirmed
            if order.status == "payment_sent":
                order.status = "live"
            result["actions"].append(f"Order {order.id[:8]}... marked as paid")

        received_email.processing_status = "processed"
        received_email.processing_notes = f"Payment receipt processed for {len(orders)} order(s)"

        await send_slack_alert("PAYMENT_CONFIRMED", orders[0] if orders else None, domain, extra={
            "domain": domain.domain,
        })
    else:
        # No orders to update — log and notify
        received_email.processing_status = "processed"
        received_email.processing_notes = f"Payment receipt but no matching orders to update"
        result["actions"].append("Payment receipt logged but no orders in payment_sent/published status")

        await send_slack_alert("PAYMENT_CONFIRMED", None, domain, extra={
            "domain": domain.domain,
            "note": "No matching order found",
        })

    return result


async def _escalate_to_slack(
    db: Session, domain: Domain, from_email: str, subject: str,
    summary: str, email_type: str, confidence: float,
    suggested_action: str | None,
):
    """Escalate an email to Slack for human review."""
    from .slack_notifier import send_slack_alert

    text = (
        f"📬 *Email needs attention* — `{email_type}` (confidence: {confidence:.0%})\n"
        f"Domain: *{domain.domain}*\n"
        f"From: {from_email}\n"
        f"Subject: _{subject}_\n"
        f"Summary: {summary}\n"
    )
    if suggested_action:
        text += f"Suggested: {suggested_action}\n"

    try:
        import httpx
        webhook_url = settings.slack_webhook_url
        if webhook_url:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(webhook_url, json={"text": text})
    except Exception as e:
        print(f"Slack escalation failed: {e}")


async def scan_replies(db: Session) -> list[dict]:
    """Scan inbox for replies to our sent emails and process them."""
    mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
    mail.login(settings.email_account, settings.email_password)
    mail.select("INBOX", readonly=True)
    
    results = []
    
    try:
        # Get all sent email addresses
        sent_emails = db.query(SentEmail.to_email).distinct().all()
        sent_addresses = {e[0].lower() for e in sent_emails}
        
        if not sent_addresses:
            # Fallback: check all domains' emails
            domains_with_email = db.query(Domain).filter(Domain.email.isnot(None)).all()
            for d in domains_with_email:
                sent_addresses.add(d.email.lower())
        
        # Also match by domain name in subject "Re: Advertising on <domain>"
        all_domains = {d.domain.lower(): d for d in db.query(Domain).all()}
        
        # Scan UNSEEN emails: subject-based + FROM-based (catches post-publication,
        # payment receipts, and any email from a known domain)
        all_msg_ids = set()
        
        # Subject-based searches (existing)
        for search_query in ['UNSEEN SUBJECT "Re:"', 'UNSEEN SUBJECT "advertising"', 'UNSEEN SUBJECT "guest post"', 'UNSEEN SUBJECT "link"', 'UNSEEN SUBJECT "published"', 'UNSEEN SUBJECT "article"', 'UNSEEN SUBJECT "payment"', 'UNSEEN SUBJECT "live"']:
            status, data = mail.search(None, search_query)
            if status == "OK" and data[0]:
                all_msg_ids.update(data[0].split())
        
        # FROM-based searches: find emails from domains in our DB
        # Build unique email domains from known domain records + sent email addresses
        known_email_domains = set()
        for d_name in all_domains:
            known_email_domains.add(d_name)
        for addr in sent_addresses:
            email_d = addr.split("@")[-1].lower()
            known_email_domains.add(email_d)
        
        # Search IMAP for FROM each known domain (batch to avoid too many queries)
        # Limit to domains with active relationships (have contacts or orders)
        active_domain_ids = set()
        for d in db.query(Domain).filter(Domain.status.in_([
            DomainStatus.CONTACTED, DomainStatus.REPLIED, DomainStatus.NEGOTIATING,
            DomainStatus.DEAL_CLOSED, DomainStatus.ACCEPTED,
        ])).all():
            active_domain_ids.add(d.domain.lower())
        
        for email_domain in known_email_domains:
            if email_domain not in active_domain_ids:
                continue  # Skip domains we haven't engaged with
            try:
                status, data = mail.search(None, f'UNSEEN FROM "@{email_domain}"')
                if status == "OK" and data[0]:
                    all_msg_ids.update(data[0].split())
            except Exception:
                pass  # IMAP search can fail on some patterns, skip silently
        
        if not all_msg_ids:
            return results
        
        msg_ids = sorted(all_msg_ids)
        
        for msg_id in reversed(msg_ids):
            status, header_data = mail.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)] FLAGS)")
            if status != "OK":
                continue
            
            header_msg = email.message_from_bytes(header_data[0][1])
            _, from_email_addr = parseaddr(header_msg.get("From", ""))
            subject = decode_str(header_msg.get("Subject", ""))
            
            if not from_email_addr:
                continue
            
            # Match: sender is someone we emailed, or subject contains a domain we track
            domain = None
            
            if from_email_addr.lower() in sent_addresses:
                domain = find_domain_for_email(db, from_email_addr.lower(), subject=subject)
            
            if not domain:
                # Try to extract ANY tracked domain from subject line
                # Catches: "Re: Advertising on domain.com", "[www.domain.com] ...", etc.
                # Find all domain-like strings in subject
                subject_domains = re.findall(r'(?:www\.)?([a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)*\.[a-z]{2,})', subject, re.IGNORECASE)
                for subj_domain in subject_domains:
                    subj_domain = subj_domain.lower().lstrip("www.")
                    if subj_domain in all_domains:
                        domain = all_domains[subj_domain]
                        break
            
            if not domain:
                # Try matching sender email domain
                email_domain = from_email_addr.split("@")[-1].lower()
                if email_domain in all_domains:
                    domain = all_domains[email_domain]
            
            if not domain:
                continue
            
            # Parse email date
            email_date_str = header_msg.get("Date", "")
            email_date = None
            if email_date_str:
                try:
                    from email.utils import parsedate_to_datetime
                    email_date = parsedate_to_datetime(email_date_str)
                except:
                    pass
            
            # Extract Message-ID from headers
            header_message_id = header_msg.get("Message-ID", "").strip()
            
            # Store the received email BEFORE processing check
            imap_uid_str = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
            
            # Check for duplicate by imap_uid
            existing_received = db.query(ReceivedEmail).filter(
                ReceivedEmail.imap_uid == imap_uid_str,
                ReceivedEmail.domain_id == domain.id,
            ).first()
            
            if existing_received:
                continue  # Already processed this exact email
            
            received_email = ReceivedEmail(
                domain_id=domain.id,
                from_addr=from_email_addr,
                subject=subject[:500],
                received_at=email_date,
                imap_uid=imap_uid_str,
                message_id=header_message_id,
            )
            db.add(received_email)
            db.flush()  # Get the ID
            
            # ── AI Classification ──
            # Fetch the full email body for classification
            status2, msg_data2 = mail.fetch(msg_id, "(BODY.PEEK[])")
            email_body = ""
            email_full_msg = None
            if status2 == "OK":
                email_full_msg = email.message_from_bytes(msg_data2[0][1])
                email_body = extract_body(email_full_msg)
                received_email.body_text = email_body[:10000]
                # Update message ID from full headers
                full_message_id = email_full_msg.get("Message-ID", "").strip()
                full_references = email_full_msg.get("References", "").strip()
                if full_message_id:
                    received_email.message_id = full_message_id
            
            # Classify the email using Sonnet
            from .email_classifier import classify_email
            classification = await classify_email(
                from_addr=from_email_addr,
                subject=subject,
                body=email_body,
                domain_name=domain.domain,
            )
            
            email_type = classification.get("classification", "outreach_reply")
            confidence = classification.get("confidence", 0.5)
            classified_url = classification.get("published_url")
            summary = classification.get("summary", "")
            
            # Store classification in received_email
            received_email.parsed_data = received_email.parsed_data or {}
            if isinstance(received_email.parsed_data, dict):
                received_email.parsed_data = {**received_email.parsed_data, "_classification": classification}
            else:
                received_email.parsed_data = {"_classification": classification}
            
            # Build threading references
            if full_references and full_message_id:
                _cls_reply_refs = f"{full_references} {full_message_id}".strip()
            elif full_message_id:
                _cls_reply_refs = full_message_id
            else:
                full_message_id, _cls_reply_refs = _get_thread_headers(db, domain.id, from_email_addr)
            
            # ── Route by classification ──
            
            if email_type == "publication_confirmation" and confidence >= 0.7:
                # Handle publication confirmation — verify backlink + update order
                result = await _handle_publication_confirmation(
                    db, domain, received_email, email_body, classified_url,
                    from_email_addr, full_message_id, _cls_reply_refs, summary,
                )
                results.append(result)
                _mark_as_read(msg_id)
                db.commit()
                continue
            
            elif email_type == "payment_receipt" and confidence >= 0.85:
                # Handle payment receipt — update order payment status
                result = await _handle_payment_receipt(
                    db, domain, received_email, summary,
                )
                results.append(result)
                _mark_as_read(msg_id)
                db.commit()
                continue
            
            elif email_type == "question" or (email_type != "other" and confidence < 0.7):
                # Escalate to R via Slack — needs human judgment
                await _escalate_to_slack(
                    db, domain, from_email_addr, subject, summary,
                    email_type, confidence, classification.get("suggested_action"),
                )
                received_email.processing_status = "escalated"
                received_email.processing_notes = f"Escalated: {email_type} (conf: {confidence:.2f}) — {summary}"
                # Still process as outreach_reply to extract any data
                if email_type == "question":
                    _mark_as_read(msg_id)
                    db.commit()
                    results.append({"domain": domain.domain, "status": "escalated", "classification": email_type, "summary": summary})
                    continue
            
            elif email_type == "other" and confidence >= 0.85:
                # Skip irrelevant emails (newsletters, auto-replies, etc.)
                received_email.processing_status = "skipped"
                received_email.processing_notes = f"Classified as 'other' (conf: {confidence:.2f}) — {summary}"
                _mark_as_read(msg_id)
                db.commit()
                results.append({"domain": domain.domain, "status": "skipped_other", "summary": summary})
                continue
            
            # ── outreach_reply or low-confidence fallback → existing full processing ──
            
            # Check if already processed (has contact + prices + payment)
            # BUT: always do full processing if there are active orders (sent/live)
            has_active_orders = db.query(Order).filter(
                Order.domain_id == domain.id,
                Order.status.in_(["sent", "content_ready"]),
                Order.deleted_at.is_(None),
            ).count() > 0
            if not has_active_orders and domain_already_processed(db, domain, from_email_addr.lower()):
                received_email.processing_status = "skipped"
                received_email.processing_notes = f"Domain already has contact+prices+payment. Classification: {email_type}"
                
                # Still check for published URLs (legacy behavior)
                url_pattern = re.findall(r'https?://[^\s<>"\']+', email_body)
                publisher_domain = domain.domain.lower().replace("www.", "")
                published_urls = [u for u in url_pattern if publisher_domain in u.lower()]
                
                if published_urls:
                    sent_orders = db.query(Order).filter(
                        Order.domain_id == domain.id,
                        Order.status == "sent",
                    ).all()
                    
                    for sent_order in sent_orders:
                        pub_url = published_urls[0]
                        try:
                            from .link_monitor import verify_live_url
                            from .slack_notifier import send_slack_alert
                            vresult = await verify_live_url(sent_order.id, pub_url, db, auto_update_status=True)
                            received_email.processing_status = "skipped_but_verified"
                            received_email.processing_notes = f"Auto-verified: {vresult['status']}"
                            
                            if vresult.get("verified"):
                                pm = db.query(DomainPaymentMethod).filter(
                                    DomainPaymentMethod.domain_id == domain.id,
                                ).first()
                                payment_info = f"{pm.method}: {pm.details}" if pm and pm.details else (pm.method if pm else "")
                                await send_slack_alert("VERIFIED", sent_order, domain, extra={
                                    "url": pub_url,
                                    "payment_info": payment_info,
                                })
                            else:
                                if vresult.get("issues"):
                                    # Filter out infrastructure/browser errors before emailing publisher
                                    _safe_issues = [
                                        i for i in vresult["issues"]
                                        if not re.match(r'^HTTP \d{3}$', i.strip())
                                        and i.strip() not in {'BROWSER_ERROR', 'VERIFICATION_ERROR', 'NOT_LIVE'}
                                        and not any(kw in i.lower() for kw in [
                                            'browser', 'playwright', 'chromium', 'failed to load',
                                            'timeout', 'connection refused', 'agent-browser',
                                            'unexpected error', 'automation failed',
                                        ])
                                    ]
                                    contact = db.query(Contact).filter(
                                        Contact.domain_id == domain.id,
                                        Contact.is_primary == True,
                                    ).first()
                                    if contact and contact.email and _safe_issues:
                                        try:
                                            await send_verification_fix_request(
                                                contact.email, domain.domain, contact.name or "there", _safe_issues,
                                                domain_id=domain.id, db=db,
                                                in_reply_to=full_message_id,
                                                references=_cls_reply_refs,
                                            )
                                            db.commit()
                                        except Exception:
                                            pass
                                
                                await send_slack_alert(vresult["status"], sent_order, domain, extra={
                                    "url": pub_url,
                                    "issues_text": "; ".join(vresult.get("issues", [])),
                                })
                        except Exception as e:
                            received_email.processing_notes += f"; Verification failed: {e}"
                        break
                
                _mark_as_read(msg_id)
                db.commit()
                results.append({"domain": domain.domain, "status": "skipped", "received_email_id": received_email.id})
                continue  # Skip full processing
            
            # Process this reply (outreach_reply flow)
            try:
                result = await process_reply(db, msg_id, mail, domain, received_email=received_email)
                results.append(result)
                _mark_as_read(msg_id)
                
            except Exception as e:
                received_email.processing_status = "error"
                received_email.processing_notes = str(e)
                db.commit()
                results.append({"domain": domain.domain, "error": str(e)})
    
    finally:
        mail.logout()
    
    return results
