"""
Email Classifier Service — Uses Claude Sonnet to classify ALL inbound emails
from known domains, not just outreach replies.

Classification types:
- publication_confirmation: publisher confirms article is live (extract URL)
- payment_receipt: publisher confirms payment received
- outreach_reply: reply to our outreach (pricing, availability, etc.) — existing flow
- question: publisher asks something requiring human judgment
- other: newsletters, spam, irrelevant
"""

import json
import re
import logging
import httpx

from ..config import settings

log = logging.getLogger(__name__)

CLASSIFICATION_PROMPT = """You are classifying an inbound email from a website publisher/owner. We do link building outreach — we buy guest posts and link placements on websites.

Classify this email into exactly ONE category:

1. **publication_confirmation** — The publisher is telling us an article/post has been published or is live. They usually share a URL where our content/link is now live. Keywords: "published", "live", "article is up", "post is ready", "link has been placed", "here is the URL", etc.

2. **payment_receipt** — The publisher confirms they received our payment, or sends a payment receipt/invoice confirmation. Keywords: "payment received", "thank you for the payment", "invoice paid", "received the transfer", etc.

3. **outreach_reply** — A reply to our advertising/guest post outreach. They're discussing pricing, availability, link types, content requirements, or negotiating terms. This is the DEFAULT for any business discussion about link placements.

4. **question** — The publisher is asking us something that needs a human decision: content revisions, clarification about requirements, scheduling questions, or anything that doesn't fit the other categories and needs judgment.

5. **other** — Newsletters, auto-replies (vacation/OOO), spam, unsubscribe confirmations, unrelated emails.

EMAIL:
From: {from_addr}
Subject: {subject}
Domain: {domain}

{body}

Respond with ONLY valid JSON:
{{
  "classification": "publication_confirmation|payment_receipt|outreach_reply|question|other",
  "confidence": 0.0 to 1.0,
  "published_url": "URL if found in email (null if not)",
  "summary": "one-line summary of the email",
  "suggested_action": "what should be done (for question/other types)"
}}"""


async def classify_email(
    from_addr: str,
    subject: str,
    body: str,
    domain_name: str,
) -> dict:
    """Classify an inbound email using Claude Sonnet.
    
    Returns dict with: classification, confidence, published_url, summary, suggested_action
    """
    import os
    api_key = getattr(settings, 'anthropic_api_key', None) or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("No Anthropic API key — falling back to outreach_reply")
        return {
            "classification": "outreach_reply",
            "confidence": 0.5,
            "published_url": None,
            "summary": "No API key for classification",
            "suggested_action": None,
        }

    prompt = CLASSIFICATION_PROMPT.format(
        from_addr=from_addr,
        subject=subject,
        domain=domain_name,
        body=body[:3000],
    )

    try:
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
                    "max_tokens": 512,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            data = response.json()
            text = data["content"][0]["text"]

            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                result = json.loads(json_match.group())
                log.info(f"Email classified: {result.get('classification')} (conf: {result.get('confidence')}) — {result.get('summary', '')[:80]}")
                return result

            log.warning(f"No JSON in classifier response: {text[:200]}")
    except Exception as e:
        log.error(f"Email classification failed: {e}")

    # Fallback: outreach_reply (existing behavior)
    return {
        "classification": "outreach_reply",
        "confidence": 0.5,
        "published_url": None,
        "summary": "Classification failed, defaulting to outreach_reply",
        "suggested_action": None,
    }
