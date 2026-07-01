"""
Slack Notifier Service - Sends alerts to Slack via webhook.
"""

import httpx
from typing import Optional, Dict, Any
from ..config import settings
from ..models import Order, Domain, DomainPaymentMethod


async def send_slack_alert(
    alert_type: str,
    order: Optional[Order] = None,
    domain: Optional[Domain] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Send a formatted Slack alert.

    alert_type: VERIFIED, WRONG_ANCHORS, MISSING_LINKS, NOFOLLOW,
                IMAGES_MISSING, ARTICLE_INCOMPLETE, NOT_LIVE,
                AUTO_FIX_EMAIL_SENT, PAYMENT_CONFIRMED, LINK_REMOVED,
                PUBLISHER_STALE
    """
    extra = extra or {}
    webhook_url = settings.slack_webhook_url
    if not webhook_url:
        return False

    domain_name = domain.domain if domain else (extra.get("domain") or "unknown")
    price_str = f"${order.price} {order.currency}" if order and order.price else ""
    live_url = extra.get("url") or (order.live_url if order else "")

    # Get payment details
    payment_info = ""
    if order and domain:
        from sqlalchemy.orm import Session
        # Try to get payment method from extra or build generic
        payment_info = extra.get("payment_info", "")

    text = _format_message(alert_type, domain_name, price_str, live_url, payment_info, extra)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json={"text": text})
            return resp.status_code == 200
    except Exception as e:
        print(f"Slack alert failed: {e}")
        return False


async def send_article_for_review(
    order: Order,
    domain: Domain,
    article_content: str,
    campaign,
) -> bool:
    """Send article preview to Slack for approval."""
    webhook_url = settings.slack_webhook_url
    if not webhook_url:
        return False

    # Extract title
    title = "Untitled"
    if article_content and "TITLE:" in article_content:
        title = article_content.split("TITLE:", 1)[1].split("\n")[0].strip()

    word_count = len(article_content.split()) if article_content else 0
    preview = article_content[:200] if article_content else ""
    price_str = f"${order.price}" if order.price else "N/A"

    base_url = "https://backvora.com"
    approve_url = f"{base_url}/api/v1/internal/orders/{order.id}/approve"
    reject_url = f"{base_url}/api/v1/internal/orders/{order.id}/reject"

    text = (
        f"📝 *Article Review Required*\n"
        f"Campaign: *{campaign.name}*\n"
        f"Domain: *{domain.domain}* ({price_str})\n"
        f"Title: _{title}_\n"
        f"Words: {word_count}\n\n"
        f"Preview: {preview}...\n\n"
        f"✅ <{approve_url}|Approve> | ❌ <{reject_url}|Reject>"
    )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json={"text": text})
            return resp.status_code == 200
    except Exception as e:
        print(f"Slack review alert failed: {e}")
        return False


def _format_message(
    alert_type: str, domain: str, price: str, url: str,
    payment_info: str, extra: dict,
) -> str:
    issues_text = extra.get("issues_text", "")

    if alert_type == "VERIFIED":
        msg = f"✅ *{domain}* is live & verified!"
        if url:
            msg += f"\n🔗 {url}"
        if price:
            msg += f"\n💰 {price}"
        if payment_info:
            msg += f" → {payment_info}"
        msg += "\n🎯 Pay now?"
        return msg

    if alert_type == "PAYMENT_CONFIRMED":
        msg = f"💰 *Payment confirmed* for *{domain}*!"
        if price:
            msg += f" ({price})"
        if payment_info:
            msg += f"\n📤 Sent to: {payment_info}"
        return msg

    if alert_type == "LINK_REMOVED":
        msg = f"🔴 *Link removed* on *{domain}*!"
        if url:
            msg += f"\nWas live at: {url}"
        return msg

    if alert_type == "AUTO_FIX_EMAIL_SENT":
        msg = f"📧 Emailed publisher about issues on *{domain}*"
        if issues_text:
            msg += f"\n⚠️ {issues_text}"
        return msg

    if alert_type == "PUBLISHER_STALE":
        msg = f"⏰ No response from *{domain}* publisher after 2 follow-ups"
        return msg

    if alert_type == "BUDGET_EXHAUSTED":
        name = extra.get("domain", "Unknown")
        total = extra.get("budget_total", 0)
        spent = extra.get("budget_spent", 0)
        return f"💰 *Campaign {name} paused* — budget exhausted (${spent:.0f}/${total:.0f} spent)"

    if alert_type == "CAMPAIGN_GRADUATED":
        name = extra.get("domain", "Unknown")
        threshold = extra.get("threshold", 10)
        return f"🎓 *Campaign {name}* has graduated to full auto mode after {threshold} consecutive approvals!"

    # Generic issue alert (WRONG_ANCHORS, MISSING_LINKS, NOFOLLOW, etc.)
    msg = f"⚠️ Issues found on *{domain}*: `{alert_type}`"
    if url:
        msg += f"\n🔗 {url}"
    if issues_text:
        msg += f"\n{issues_text}"
    if price:
        msg += f"\n💰 {price}"
    return msg
