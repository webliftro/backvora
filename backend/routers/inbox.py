"""
Inbox API router - IMAP/SMTP email operations.
"""

import imaplib
import email
import smtplib
import ssl
import re
import asyncio
import json
import threading
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import parseaddr, formatdate, make_msgid
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr

from datetime import datetime
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import SentEmail, ReceivedEmail

router = APIRouter()


# Schemas
class EmailListItem(BaseModel):
    id: str
    from_addr: str
    to_addr: str
    subject: str
    date: str
    snippet: str
    is_read: bool
    has_attachments: bool


class EmailAttachment(BaseModel):
    filename: str
    content_type: str
    size: int


class EmailDetail(BaseModel):
    id: str
    from_addr: str
    to_addr: str
    subject: str
    date: str
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    is_read: bool
    attachments: List[EmailAttachment] = []


class ReplyRequest(BaseModel):
    body: str
    quote_original: bool = True


class ComposeRequest(BaseModel):
    to: EmailStr
    subject: str
    body: str
    domain_id: Optional[str] = None


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


def get_imap_connection():
    try:
        mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
        mail.login(settings.email_account, settings.email_password)
        return mail
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"IMAP connection failed: {str(e)}")


def get_smtp_connection():
    try:
        context = ssl.create_default_context()
        smtp = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context)
        smtp.login(settings.email_account, settings.email_password)
        return smtp
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SMTP connection failed: {str(e)}")


def extract_body(msg: email.message.Message) -> tuple[Optional[str], Optional[str]]:
    html_body = None
    text_body = None
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            try:
                body = part.get_payload(decode=True)
                if body:
                    charset = part.get_content_charset() or 'utf-8'
                    body = body.decode(charset, errors='replace')
                    if ct == "text/plain" and not text_body:
                        text_body = body
                    elif ct == "text/html" and not html_body:
                        html_body = body
            except:
                continue
    else:
        try:
            body = msg.get_payload(decode=True)
            if body:
                charset = msg.get_content_charset() or 'utf-8'
                body = body.decode(charset, errors='replace')
                if msg.get_content_type() == "text/html":
                    html_body = body
                else:
                    text_body = body
        except:
            pass
    return html_body, text_body


def extract_attachments(msg: email.message.Message) -> List[EmailAttachment]:
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                filename = part.get_filename()
                if filename:
                    payload = part.get_payload(decode=True)
                    attachments.append(EmailAttachment(
                        filename=decode_str(filename),
                        content_type=part.get_content_type(),
                        size=len(payload) if payload else 0
                    ))
    return attachments


@router.get("", response_model=List[EmailListItem])
async def list_emails(
    folder: str = Query("INBOX"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    search: Optional[str] = Query(None),
):
    """List emails - headers only for speed."""
    mail = get_imap_connection()
    try:
        mail.select(folder, readonly=True)

        # Use IMAP SEARCH for server-side filtering
        criteria_parts = []
        if unread_only:
            criteria_parts.append("UNSEEN")
        if search:
            # Search in subject and from via IMAP OR
            criteria_parts.append(f'(OR SUBJECT "{search}" FROM "{search}")')
        
        criteria = " ".join(criteria_parts) if criteria_parts else "ALL"
        status, data = mail.search(None, criteria)
        if status != "OK":
            raise HTTPException(status_code=500, detail="Search failed")

        msg_ids = data[0].split()
        if not msg_ids:
            return []

        # Newest first, paginate
        msg_ids = list(reversed(msg_ids))
        msg_ids = msg_ids[offset:offset + limit]

        if not msg_ids:
            return []

        # Batch fetch headers + flags only (no body!)
        id_range = b",".join(msg_ids)
        status, response = mail.fetch(id_range, "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE CONTENT-TYPE)] FLAGS BODYSTRUCTURE)")
        if status != "OK":
            raise HTTPException(status_code=500, detail="Fetch failed")

        # Parse response pairs: each message has (flags_line, header_bytes), b')'
        emails = []
        i = 0
        while i < len(response):
            item = response[i]
            if isinstance(item, tuple) and len(item) == 2:
                flags_line = item[0].decode() if isinstance(item[0], bytes) else str(item[0])
                header_bytes = item[1]

                # Extract UID (sequence number) from flags line
                seq_match = re.match(r"(\d+)", flags_line)
                seq_id = seq_match.group(1) if seq_match else "0"

                is_read = "\\Seen" in flags_line
                has_attach = "attachment" in flags_line.lower() or ("mixed" in flags_line.lower() and "BODYSTRUCTURE" in flags_line)

                msg = email.message_from_bytes(header_bytes)
                from_name, from_email_addr = parseaddr(msg.get("From", ""))
                from_addr = from_email_addr or decode_str(msg.get("From", ""))
                to_name, to_email_addr = parseaddr(msg.get("To", ""))
                to_addr = to_email_addr or decode_str(msg.get("To", ""))

                emails.append(EmailListItem(
                    id=seq_id,
                    from_addr=from_addr,
                    to_addr=to_addr,
                    subject=decode_str(msg.get("Subject", "(no subject)")),
                    date=msg.get("Date", ""),
                    snippet="",  # No snippet in list view for speed
                    is_read=is_read,
                    has_attachments=has_attach,
                ))
            i += 1

        # Sort newest first (highest sequence number first)
        emails.sort(key=lambda e: int(e.id), reverse=True)
        return emails
    finally:
        mail.logout()


@router.get("/stats")
async def inbox_stats(db: Session = Depends(get_db)):
    """Get email stats: sent count from BackVora DB."""
    sent_count = db.query(SentEmail).count()
    return {"sent_count": sent_count}


@router.get("/stream")
async def stream_emails():
    """SSE endpoint: checks IMAP every 15s for new emails, pushes notifications."""
    async def event_generator():
        last_count = 0
        last_unseen = 0
        first = True
        while True:
            try:
                mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
                mail.login(settings.email_account, settings.email_password)
                mail.select("INBOX", readonly=True)

                status, data = mail.search(None, "ALL")
                total = len(data[0].split()) if data[0] else 0
                status2, data2 = mail.search(None, "UNSEEN")
                unseen = len(data2[0].split()) if data2[0] else 0

                mail.logout()

                if first:
                    last_count = total
                    last_unseen = unseen
                    first = False
                    yield f"data: {json.dumps({'type': 'init', 'total': total, 'unseen': unseen})}\n\n"
                elif total > last_count or unseen != last_unseen:
                    new_emails = max(0, total - last_count)
                    last_count = total
                    last_unseen = unseen
                    yield f"data: {json.dumps({'type': 'new_email', 'new': new_emails, 'total': total, 'unseen': unseen})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            await asyncio.sleep(15)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{uid}", response_model=EmailDetail)
async def get_email(
    uid: str,
    folder: str = Query("INBOX"),
):
    mail = get_imap_connection()
    try:
        mail.select(folder, readonly=True)
        status, msg_data = mail.fetch(uid.encode(), "(BODY.PEEK[] FLAGS)")
        if status != "OK":
            raise HTTPException(status_code=404, detail="Email not found")
        raw = msg_data[0][1]
        flags_str = msg_data[0][0].decode() if msg_data[0][0] else ""
        is_read = "\\Seen" in flags_str
        msg = email.message_from_bytes(raw)
        html_body, text_body = extract_body(msg)
        attachments = extract_attachments(msg)
        from_name, from_email_addr = parseaddr(msg.get("From", ""))
        to_name, to_email_addr = parseaddr(msg.get("To", ""))
        return EmailDetail(
            id=uid,
            from_addr=from_email_addr or decode_str(msg.get("From", "")),
            to_addr=to_email_addr or decode_str(msg.get("To", "")),
            subject=decode_str(msg.get("Subject", "(no subject)")),
            date=msg.get("Date", ""),
            body_html=html_body,
            body_text=text_body,
            is_read=is_read,
            attachments=attachments,
        )
    finally:
        mail.logout()


@router.post("/{uid}/mark-read")
async def mark_as_read(uid: str, folder: str = Query("INBOX")):
    mail = get_imap_connection()
    try:
        mail.select(folder)
        status, _ = mail.store(uid.encode(), '+FLAGS', '\\Seen')
        if status != "OK":
            raise HTTPException(status_code=500, detail="Failed to mark as read")
        return {"success": True}
    finally:
        mail.logout()


@router.post("/{uid}/reply")
async def reply_to_email(uid: str, reply: ReplyRequest, folder: str = Query("INBOX"), db: Session = Depends(get_db)):
    mail = get_imap_connection()
    try:
        mail.select(folder, readonly=True)
        status, msg_data = mail.fetch(uid.encode(), "(BODY.PEEK[])")
        if status != "OK":
            raise HTTPException(status_code=404, detail="Original email not found")
        original_msg = email.message_from_bytes(msg_data[0][1])
        original_from = original_msg.get("From", "")
        original_subject = decode_str(original_msg.get("Subject", ""))
        original_date = original_msg.get("Date", "")
        _, from_email_addr = parseaddr(original_from)
        reply_to = from_email_addr or original_from

        reply_subject = original_subject
        if not reply_subject.lower().startswith("re:"):
            reply_subject = f"Re: {reply_subject}"

        reply_body = reply.body
        if reply.quote_original:
            html_body, text_body = extract_body(original_msg)
            original_body = text_body or ""
            if not original_body and html_body:
                original_body = re.sub(r'<[^>]+>', '', html_body)
            quoted = f"\n\n{'—'*40}\nOn {original_date}, {original_from} wrote:\n\n"
            quoted += "\n".join(["> " + line for line in original_body.split("\n")])
            reply_body += quoted
    finally:
        mail.logout()

    smtp = get_smtp_connection()
    try:
        msg = MIMEMultipart()
        msg["From"] = settings.email_account
        msg["To"] = reply_to
        msg["Subject"] = reply_subject
        msg["Date"] = formatdate(localtime=True)
        msg["In-Reply-To"] = original_msg.get("Message-ID", "")
        msg["References"] = original_msg.get("Message-ID", "")
        msg.attach(MIMEText(reply_body, "plain"))
        smtp.send_message(msg)

        db.add(SentEmail(to_email=reply_to, subject=reply_subject, body=reply.body, sent_at=datetime.utcnow()))
        db.commit()

        return {"success": True, "message": "Reply sent"}
    finally:
        smtp.quit()


@router.post("/scan-replies")
async def scan_replies_endpoint(db: Session = Depends(get_db)):
    """Scan inbox for replies to sent emails, parse with Sonnet, and auto-populate domain data."""
    from ..services.reply_parser import scan_replies
    results = await scan_replies(db)
    return {"processed": len(results), "results": results}


@router.post("/compose")
async def compose_email(compose: ComposeRequest, db: Session = Depends(get_db)):
    subject = compose.subject
    in_reply_to = None
    references = None

    # Auto-thread: if domain_id provided, look up the most recent email in the conversation
    # (received or sent) so this email lands in the existing thread, not a new one.
    if compose.domain_id:
        last_received = db.query(ReceivedEmail).filter(
            ReceivedEmail.domain_id == compose.domain_id,
            ReceivedEmail.message_id.isnot(None),
        ).order_by(ReceivedEmail.received_at.desc()).first()

        last_sent = db.query(SentEmail).filter(
            SentEmail.domain_id == compose.domain_id,
            SentEmail.message_id.isnot(None),
        ).order_by(SentEmail.sent_at.desc()).first()

        # Pick whichever is more recent
        thread_anchor = None
        if last_received and last_sent:
            received_time = last_received.received_at or datetime.min
            sent_time = last_sent.sent_at or datetime.min
            thread_anchor = last_received if received_time >= sent_time else last_sent
        elif last_received:
            thread_anchor = last_received
        elif last_sent:
            thread_anchor = last_sent

        if thread_anchor:
            in_reply_to = thread_anchor.message_id
            references = thread_anchor.message_id
            # Mirror the thread subject so email clients keep it in the same conversation
            anchor_subject = thread_anchor.subject or ""
            if anchor_subject:
                subject = anchor_subject if anchor_subject.lower().startswith("re:") else f"Re: {anchor_subject}"

    smtp = get_smtp_connection()
    try:
        msg = MIMEMultipart()
        msg["From"] = settings.email_account
        msg["To"] = compose.to
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        # Generate Message-ID ourselves so we can store it for future threading
        sent_message_id = make_msgid(domain=settings.smtp_host)
        msg["Message-ID"] = sent_message_id
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = references
        msg.attach(MIMEText(compose.body, "plain"))
        smtp.send_message(msg)

        # Save to Gmail Sent folder via IMAP
        try:
            imap = imaplib.IMAP4_SSL("imap.gmail.com")
            imap.login(settings.email_account, settings.email_password)
            imap.select('"[Gmail]/Sent Mail"')
            imap.append('"[Gmail]/Sent Mail"', "\\Seen", None, msg.as_bytes())
            imap.logout()
        except Exception as imap_err:
            print(f"Warning: Could not save to Sent folder: {imap_err}")

        db.add(SentEmail(
            to_email=compose.to,
            subject=subject,
            body=compose.body,
            domain_id=compose.domain_id,
            sent_at=datetime.utcnow(),
            message_id=sent_message_id,
        ))
        db.commit()

        return {"success": True, "message": "Email sent", "threaded": bool(in_reply_to)}
    finally:
        smtp.quit()


@router.get("/received")
async def get_received_emails(domain_id: str = None, limit: int = 50, db: Session = Depends(get_db)):
    """Get received emails, optionally filtered by domain."""
    query = db.query(ReceivedEmail).order_by(ReceivedEmail.created_at.desc())
    if domain_id:
        query = query.filter(ReceivedEmail.domain_id == domain_id)
    return query.limit(limit).all()
