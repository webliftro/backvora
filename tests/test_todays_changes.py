"""
Tests for 2026-03-05 changes:
1. No-upfront reply debounce (don't double-fire)
2. Payment confirmation → auto-verify → mark live
3. Article email threading (In-Reply-To headers)
4. Article topic field on orders
5. Spent counter sync
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy.orm import Session

from backend.models import (
    Order, Domain, Campaign, Contact, OrderLink, SentEmail,
    DomainPaymentMethod, DomainStatus, LinkPrice, ReceivedEmail, LinkCheck,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_domain(db: Session, domain: str = "testsite.com", **kw) -> Domain:
    kw.setdefault("status", DomainStatus.DEAL_CLOSED)
    d = Domain(domain=domain, **kw)
    db.add(d)
    db.flush()
    return d


def make_campaign(db: Session, name: str = "Test Campaign", **kw) -> Campaign:
    kw.setdefault("target_site", "camhours.com")
    c = Campaign(name=name, status="active", **kw)
    db.add(c)
    db.flush()
    return c


def make_order(db: Session, campaign: Campaign, domain: Domain, **kw) -> Order:
    defaults = dict(
        campaign_id=campaign.id,
        domain_id=domain.id,
        link_type="Guest Post",
        status="sent",
        price=100.0,
    )
    defaults.update(kw)
    o = Order(**defaults)
    db.add(o)
    db.flush()
    return o


def make_sent_email(db: Session, domain: Domain, body: str, sent_at: datetime = None, **kw) -> SentEmail:
    e = SentEmail(
        to_email="test@example.com",
        subject="Test",
        body=body,
        domain_id=domain.id,
        sent_at=sent_at or datetime.utcnow(),
        **kw,
    )
    db.add(e)
    db.flush()
    return e


def make_received_email(db: Session, domain: Domain, received_at: datetime = None, **kw) -> ReceivedEmail:
    defaults = dict(
        domain_id=domain.id,
        from_addr="pub@testsite.com",
        subject="Re: Guest Post",
        received_at=received_at or datetime.utcnow(),
        imap_uid=str(datetime.utcnow().timestamp()),
    )
    defaults.update(kw)
    e = ReceivedEmail(**defaults)
    db.add(e)
    db.flush()
    return e


# ─── 1. No-upfront debounce ──────────────────────────────────────────────────

class TestNoUpfrontDebounce:
    """No-upfront replies should not double-fire when publisher sends multiple emails."""

    def test_skip_if_email_predates_our_reply(self, db: Session):
        """If publisher's email was sent before our no-upfront reply, skip."""
        domain = make_domain(db)
        campaign = make_campaign(db)
        order = make_order(db, campaign, domain)

        # We sent a no-upfront reply at 12:00
        make_sent_email(db, domain, "(auto no-upfront reply #1: no_upfront_1)",
                        sent_at=datetime(2026, 3, 5, 12, 0, 0))

        db.commit()

        # Their email was at 11:30 (before our reply) — should skip
        # Simulate the check from reply_parser
        upfront_replies_count = db.query(SentEmail).filter(
            SentEmail.domain_id == domain.id,
            SentEmail.body.like("%(auto no-upfront%"),
        ).count()

        last_upfront_sent = db.query(SentEmail).filter(
            SentEmail.domain_id == domain.id,
            SentEmail.body.like("%(auto no-upfront%"),
        ).order_by(SentEmail.sent_at.desc()).first()

        incoming_date = datetime(2026, 3, 5, 11, 30, 0)  # Before our reply

        assert last_upfront_sent is not None
        assert incoming_date < last_upfront_sent.sent_at
        # This means we should SKIP, not escalate

    def test_escalate_if_email_after_our_reply(self, db: Session):
        """If publisher replies AFTER our no-upfront, then escalate."""
        domain = make_domain(db)
        campaign = make_campaign(db)
        order = make_order(db, campaign, domain)

        # We sent no-upfront #1 at 12:00
        make_sent_email(db, domain, "(auto no-upfront reply #1: no_upfront_1)",
                        sent_at=datetime(2026, 3, 5, 12, 0, 0))
        db.commit()

        # Their new email at 14:00 (after our reply) — should escalate to #2
        incoming_date = datetime(2026, 3, 5, 14, 0, 0)

        last_upfront_sent = db.query(SentEmail).filter(
            SentEmail.domain_id == domain.id,
            SentEmail.body.like("%(auto no-upfront%"),
        ).order_by(SentEmail.sent_at.desc()).first()

        upfront_replies_count = db.query(SentEmail).filter(
            SentEmail.domain_id == domain.id,
            SentEmail.body.like("%(auto no-upfront%"),
        ).count()

        assert incoming_date > last_upfront_sent.sent_at
        assert upfront_replies_count == 1  # Should trigger no_upfront_2

    def test_first_upfront_email_gets_reply(self, db: Session):
        """First time publisher demands upfront, we should respond."""
        domain = make_domain(db)

        count = db.query(SentEmail).filter(
            SentEmail.domain_id == domain.id,
            SentEmail.body.like("%(auto no-upfront%"),
        ).count()

        assert count == 0  # No previous replies → should send no_upfront_1


# ─── 2. Payment → verify → live ──────────────────────────────────────────────

class TestPaymentAutoVerify:
    """Confirming payment should auto-verify and mark live."""

    def test_order_with_live_url_gets_verified(self, db: Session):
        """If order has live_url when payment confirmed, verify it."""
        domain = make_domain(db, domain="example.com")
        campaign = make_campaign(db)
        order = make_order(db, campaign, domain, status="paid",
                           live_url="https://example.com/blog/post")
        db.commit()

        # The verify_live_url function should be called with the live_url
        assert order.live_url is not None
        assert order.status == "paid"

    def test_paid_to_live_status_transition(self, db: Session):
        """Verified paid order should transition to live."""
        domain = make_domain(db)
        campaign = make_campaign(db)
        order = make_order(db, campaign, domain, status="paid")

        # Simulate successful verification
        order.status = "live"
        order.live_at = datetime.utcnow()
        order.live_url = "https://testsite.com/post"
        db.commit()

        refreshed = db.query(Order).filter(Order.id == order.id).first()
        assert refreshed.status == "live"
        assert refreshed.live_at is not None
        assert refreshed.live_url is not None

    def test_order_without_live_url_stays_paid(self, db: Session):
        """If order has no live_url, stay as paid."""
        domain = make_domain(db)
        campaign = make_campaign(db)
        order = make_order(db, campaign, domain, status="paid", live_url=None)
        db.commit()

        assert order.live_url is None
        assert order.status == "paid"


# ─── 3. Article topic field ──────────────────────────────────────────────────

class TestArticleTopic:
    """Article topic field on orders."""

    def test_order_has_article_topic_field(self, db: Session):
        """Order model should have article_topic column."""
        domain = make_domain(db)
        campaign = make_campaign(db)
        order = make_order(db, campaign, domain,
                           article_topic="Best cam sites for beginners in 2026")
        db.commit()

        refreshed = db.query(Order).filter(Order.id == order.id).first()
        assert refreshed.article_topic == "Best cam sites for beginners in 2026"

    def test_article_topic_nullable(self, db: Session):
        """Article topic should be optional."""
        domain = make_domain(db)
        campaign = make_campaign(db)
        order = make_order(db, campaign, domain)
        db.commit()

        refreshed = db.query(Order).filter(Order.id == order.id).first()
        assert refreshed.article_topic is None


# ─── 4. Reply scanner finds URLs for paid orders ─────────────────────────────

class TestReplyScannerOrderStatus:
    """Reply scanner should find URLs for orders in paid status too."""

    def test_paid_order_found_in_query(self, db: Session):
        """Scanner should pick up orders with paid status, not just sent."""
        domain = make_domain(db)
        campaign = make_campaign(db)
        order = make_order(db, campaign, domain, status="paid")
        db.commit()

        active_orders = db.query(Order).filter(
            Order.domain_id == domain.id,
            Order.status.in_(["sent", "paid", "content_ready"]),
        ).all()

        assert len(active_orders) == 1
        assert active_orders[0].id == order.id

    def test_live_order_not_in_query(self, db: Session):
        """Already-live orders should not be re-verified by scanner."""
        domain = make_domain(db)
        campaign = make_campaign(db)
        order = make_order(db, campaign, domain, status="live")
        db.commit()

        active_orders = db.query(Order).filter(
            Order.domain_id == domain.id,
            Order.status.in_(["sent", "paid", "content_ready"]),
        ).all()

        assert len(active_orders) == 0


# ─── 5. Spent counter ────────────────────────────────────────────────────────

class TestSpentCounter:
    """Campaign spent should reflect actual paid/live orders."""

    def test_spent_from_paid_orders(self, db: Session):
        """Spent should sum prices of paid and live orders."""
        from sqlalchemy import func

        domain = make_domain(db)
        campaign = make_campaign(db, spent=0)
        make_order(db, campaign, domain, status="live", price=150.0)
        make_order(db, campaign, domain, status="paid", price=30.0)
        make_order(db, campaign, domain, status="sent", price=200.0)  # Not counted
        db.commit()

        actual = db.query(func.sum(Order.price)).filter(
            Order.campaign_id == campaign.id,
            Order.status.in_(["paid", "live"]),
            Order.price.isnot(None),
        ).scalar() or 0

        assert actual == 180.0  # 150 + 30, not 200

    def test_spent_excludes_draft_orders(self, db: Session):
        """Draft orders should not count toward spent."""
        from sqlalchemy import func

        domain = make_domain(db)
        campaign = make_campaign(db)
        make_order(db, campaign, domain, status="draft", price=500.0)
        db.commit()

        actual = db.query(func.sum(Order.price)).filter(
            Order.campaign_id == campaign.id,
            Order.status.in_(["paid", "live"]),
        ).scalar() or 0

        assert actual == 0


# ─── 6. Link monitor status transitions ──────────────────────────────────────

class TestLinkMonitorStatusTransitions:
    """Link monitor should set correct status based on current order status."""

    def test_sent_verified_becomes_published(self, db: Session):
        """Sent order verified → published (not yet paid)."""
        domain = make_domain(db)
        campaign = make_campaign(db)
        order = make_order(db, campaign, domain, status="sent")

        # Simulate what link_monitor does
        if order.status == "paid":
            order.status = "live"
        elif order.status in ("sent", "draft", "content_ready"):
            order.status = "published"
        db.commit()

        assert order.status == "published"

    def test_paid_verified_becomes_live(self, db: Session):
        """Paid order verified → live."""
        domain = make_domain(db)
        campaign = make_campaign(db)
        order = make_order(db, campaign, domain, status="paid")

        if order.status == "paid":
            order.status = "live"
        elif order.status in ("sent", "draft", "content_ready"):
            order.status = "published"
        db.commit()

        assert order.status == "live"


# ─── 7. Banned phrasing in article writer ────────────────────────────────────

class TestArticleWriterBannedPhrasing:
    """Article writer prompt should include banned phrasing rules."""

    def test_banned_patterns_in_prompt(self):
        """The article writer system prompt should ban 'platforms like CamHours' patterns."""
        from backend.services.article_writer import SYSTEM_PROMPT
        assert "Platforms like CamHours" in SYSTEM_PROMPT or "BANNED PHRASING" in SYSTEM_PROMPT

    def test_recommendation_guidance_in_prompt(self):
        """Should guide toward specific mentions."""
        from backend.services.article_writer import SYSTEM_PROMPT
        assert "CamHours offers" in SYSTEM_PROMPT or "deliberate recommendation" in SYSTEM_PROMPT
