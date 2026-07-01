"""Unit tests for Campaign Auto-Pilot service."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from backend.models import (
    Campaign, Domain, Contact, LinkPrice, Order, OrderLink,
    DomainStatus, TargetSite, TargetURL, AnchorText,
)
from backend.services.campaign_autopilot import (
    get_eligible_domains,
    should_create_order,
    run_campaign_cycle,
    handle_article_approval,
)


# ============ Helpers ============

def make_campaign(db, **kwargs):
    defaults = dict(
        id="camp-auto",
        name="Auto Campaign",
        target_site="mysite.com",
        status="active",
        mode="auto",
        approval_mode="review",
        velocity_period_days=7,
        velocity_count=1,
        budget_total=500.0,
        budget_spent=0.0,
        consecutive_approvals=0,
        approval_threshold=10,
    )
    defaults.update(kwargs)
    c = Campaign(**defaults)
    db.add(c)
    db.commit()
    return c


def make_domain(db, domain_name="publisher.com", dr=40, traffic=5000, status=DomainStatus.DEAL_CLOSED, email="pub@publisher.com", **kwargs):
    d = Domain(
        domain=domain_name,
        domain_rating=dr,
        organic_traffic=traffic,
        status=status,
        email=email,
        niche_tags=kwargs.get("niche_tags"),
        tags=kwargs.get("tags"),
        category=kwargs.get("category"),
    )
    db.add(d)
    db.commit()
    return d


def make_contact(db, domain, email=None):
    c = Contact(
        domain_id=domain.id,
        email=email or domain.email or "contact@test.com",
        name="Publisher",
        is_primary=True,
    )
    db.add(c)
    db.commit()
    return c


def make_price(db, domain, link_type="Guest Post", price=100.0):
    lp = LinkPrice(
        domain_id=domain.id,
        link_type=link_type,
        price=price,
        currency="USD",
    )
    db.add(lp)
    db.commit()
    return lp


# ============ get_eligible_domains ============

class TestGetEligibleDomains:
    def test_filters_by_traffic(self, db):
        campaign = make_campaign(db, filter_traffic_min=3000, filter_traffic_max=10000)
        d1 = make_domain(db, "good.com", traffic=5000)
        make_contact(db, d1)
        make_price(db, d1)
        d2 = make_domain(db, "low.com", traffic=100)
        make_contact(db, d2)
        make_price(db, d2)
        d3 = make_domain(db, "high.com", traffic=50000)
        make_contact(db, d3)
        make_price(db, d3)

        results = get_eligible_domains(campaign, db)
        domains = [r["domain"].domain for r in results]
        assert "good.com" in domains
        assert "low.com" not in domains
        assert "high.com" not in domains

    def test_filters_by_dr(self, db):
        campaign = make_campaign(db, filter_dr_min=30, filter_dr_max=60)
        d1 = make_domain(db, "mid.com", dr=45)
        make_contact(db, d1)
        make_price(db, d1)
        d2 = make_domain(db, "low-dr.com", dr=10)
        make_contact(db, d2)
        make_price(db, d2)

        results = get_eligible_domains(campaign, db)
        domains = [r["domain"].domain for r in results]
        assert "mid.com" in domains
        assert "low-dr.com" not in domains

    def test_filters_by_price(self, db):
        campaign = make_campaign(db, filter_price_min=50, filter_price_max=200)
        d1 = make_domain(db, "cheap.com")
        make_contact(db, d1)
        make_price(db, d1, price=100)
        d2 = make_domain(db, "expensive.com")
        make_contact(db, d2)
        make_price(db, d2, price=500)

        results = get_eligible_domains(campaign, db)
        domains = [r["domain"].domain for r in results]
        assert "cheap.com" in domains
        assert "expensive.com" not in domains

    def test_filters_by_niche_tags(self, db):
        campaign = make_campaign(db, filter_niche_tags="adult,entertainment")
        d1 = make_domain(db, "adult-site.com", niche_tags="adult,lifestyle")
        make_contact(db, d1)
        make_price(db, d1)
        d2 = make_domain(db, "tech-site.com", niche_tags="technology,software")
        make_contact(db, d2)
        make_price(db, d2)

        results = get_eligible_domains(campaign, db)
        domains = [r["domain"].domain for r in results]
        assert "adult-site.com" in domains
        assert "tech-site.com" not in domains

    def test_filters_by_link_type(self, db):
        campaign = make_campaign(db, filter_link_type="Guest Post")
        d1 = make_domain(db, "gp.com")
        make_contact(db, d1)
        make_price(db, d1, link_type="Guest Post")
        d2 = make_domain(db, "header.com")
        make_contact(db, d2)
        make_price(db, d2, link_type="Header")

        results = get_eligible_domains(campaign, db)
        domains = [r["domain"].domain for r in results]
        assert "gp.com" in domains
        assert "header.com" not in domains

    def test_excludes_domains_used_for_same_target(self, db):
        campaign = make_campaign(db)
        d1 = make_domain(db, "used.com")
        make_contact(db, d1)
        make_price(db, d1)

        # Create an existing order using this domain for same target
        order = Order(
            campaign_id=campaign.id,
            domain_id=d1.id,
            link_type="Guest Post",
            target_url="https://mysite.com/page",
            status="sent",
        )
        db.add(order)
        db.flush()  # get order.id
        ol = OrderLink(
            order_id=order.id,
            target_url="https://mysite.com/page",
            anchor_text="test",
            slot=1,
        )
        db.add(ol)
        db.commit()

        d2 = make_domain(db, "fresh.com")
        make_contact(db, d2)
        make_price(db, d2)

        results = get_eligible_domains(campaign, db)
        domains = [r["domain"].domain for r in results]
        assert "used.com" not in domains
        assert "fresh.com" in domains

    def test_allows_same_domain_different_target_sites(self, db):
        # Campaign targeting siteA.com
        campaign_a = make_campaign(db, id="camp-a", target_site="siteA.com")
        d1 = make_domain(db, "shared.com")
        make_contact(db, d1)
        make_price(db, d1)

        # Order for siteB.com (different target)
        campaign_b = make_campaign(db, id="camp-b", target_site="siteB.com")
        order = Order(
            campaign_id=campaign_b.id,
            domain_id=d1.id,
            link_type="Guest Post",
            target_url="https://siteB.com/page",
            status="sent",
        )
        db.add(order)
        db.flush()
        ol = OrderLink(
            order_id=order.id,
            target_url="https://siteB.com/page",
            anchor_text="test",
            slot=1,
        )
        db.add(ol)
        db.commit()

        # shared.com should still be eligible for siteA.com
        results = get_eligible_domains(campaign_a, db)
        domains = [r["domain"].domain for r in results]
        assert "shared.com" in domains

    def test_requires_contact_email(self, db):
        campaign = make_campaign(db)
        d1 = make_domain(db, "no-email.com", email=None)
        make_price(db, d1)
        # No contact either

        results = get_eligible_domains(campaign, db)
        domains = [r["domain"].domain for r in results]
        assert "no-email.com" not in domains

    def test_requires_pricing(self, db):
        campaign = make_campaign(db)
        d1 = make_domain(db, "no-price.com")
        make_contact(db, d1)
        # No price

        results = get_eligible_domains(campaign, db)
        domains = [r["domain"].domain for r in results]
        assert "no-price.com" not in domains

    def test_sorted_by_value(self, db):
        campaign = make_campaign(db)
        d1 = make_domain(db, "expensive.com", dr=20)
        make_contact(db, d1)
        make_price(db, d1, price=200)  # 200/20 = 10

        d2 = make_domain(db, "cheap.com", dr=40)
        make_contact(db, d2)
        make_price(db, d2, price=80)  # 80/40 = 2

        results = get_eligible_domains(campaign, db)
        assert results[0]["domain"].domain == "cheap.com"  # better value


# ============ should_create_order ============

class TestShouldCreateOrder:
    def test_only_auto_mode(self, db):
        campaign = make_campaign(db, mode="manual")
        assert should_create_order(campaign, db) is False

    def test_respects_velocity_too_soon(self, db):
        campaign = make_campaign(db, last_order_sent_at=datetime.utcnow() - timedelta(days=2), velocity_period_days=7)
        assert should_create_order(campaign, db) is False

    def test_respects_velocity_ready(self, db):
        campaign = make_campaign(db, last_order_sent_at=datetime.utcnow() - timedelta(days=8), velocity_period_days=7)
        assert should_create_order(campaign, db) is True

    def test_first_order_no_last_sent(self, db):
        campaign = make_campaign(db, last_order_sent_at=None)
        assert should_create_order(campaign, db) is True

    def test_budget_exceeded_auto_pause(self, db):
        campaign = make_campaign(db, budget_total=100, budget_spent=150)
        result = should_create_order(campaign, db)
        assert result is False
        db.refresh(campaign)
        assert campaign.status == "paused"

    def test_no_budget_limit(self, db):
        campaign = make_campaign(db, budget_total=None, budget_spent=0)
        assert should_create_order(campaign, db) is True

    def test_paused_campaign(self, db):
        campaign = make_campaign(db, status="paused")
        assert should_create_order(campaign, db) is False


# ============ run_campaign_cycle ============

class TestRunCampaignCycle:
    @pytest.mark.asyncio
    @patch("backend.services.slack_notifier.send_article_for_review", new_callable=AsyncMock)
    @patch("backend.services.article_writer.generate_article", new_callable=AsyncMock)
    async def test_review_mode_sends_to_slack(self, mock_gen, mock_slack, db):
        campaign = make_campaign(db, approval_mode="review")
        d = make_domain(db, "pub.com")
        make_contact(db, d)
        make_price(db, d, price=100)

        mock_gen.return_value = {"success": True, "article_content": "Test article"}

        result = await run_campaign_cycle(campaign.id, db)
        assert result["success"] is True
        assert result["action"] == "pending_review"
        mock_slack.assert_called_once()

        # Order should be pending_review
        order = db.query(Order).filter(Order.id == result["order_id"]).first()
        assert order.status == "pending_review"

    @pytest.mark.asyncio
    @patch("backend.services.order_sender.send_order", new_callable=AsyncMock)
    @patch("backend.services.article_writer.generate_article", new_callable=AsyncMock)
    async def test_auto_mode_sends_directly(self, mock_gen, mock_send, db):
        campaign = make_campaign(db, approval_mode="auto")
        d = make_domain(db, "pub2.com")
        make_contact(db, d)
        make_price(db, d, price=100)

        mock_gen.return_value = {"success": True}
        mock_send.return_value = {"success": True}

        result = await run_campaign_cycle(campaign.id, db)
        assert result["success"] is True
        assert result["action"] == "sent"
        mock_send.assert_called_once()

        db.refresh(campaign)
        assert campaign.last_order_sent_at is not None
        assert campaign.budget_spent == 100

    @pytest.mark.asyncio
    async def test_no_eligible_domains(self, db):
        campaign = make_campaign(db)
        # No domains in DB
        result = await run_campaign_cycle(campaign.id, db)
        assert result["success"] is False
        assert "No eligible" in result["reason"]


# ============ handle_article_approval ============

class TestHandleArticleApproval:
    @pytest.mark.asyncio
    @patch("backend.services.order_sender.send_order", new_callable=AsyncMock)
    async def test_clean_approval_increments_counter(self, mock_send, db):
        campaign = make_campaign(db, consecutive_approvals=5)
        d = make_domain(db, "pub3.com")
        order = Order(
            id="order-approve-1",
            campaign_id=campaign.id,
            domain_id=d.id,
            link_type="Guest Post",
            price=50,
            status="pending_review",
            article_content="Test article",
        )
        db.add(order)
        db.commit()
        mock_send.return_value = {"success": True}

        result = await handle_article_approval(order.id, approved=True, modified=False, db=db)
        assert result["success"] is True
        assert result["consecutive_approvals"] == 6
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.services.order_sender.send_order", new_callable=AsyncMock)
    async def test_modified_approval_resets_counter(self, mock_send, db):
        campaign = make_campaign(db, consecutive_approvals=8)
        d = make_domain(db, "pub4.com")
        order = Order(
            id="order-mod-1",
            campaign_id=campaign.id,
            domain_id=d.id,
            link_type="Guest Post",
            price=50,
            status="pending_review",
            article_content="Test",
        )
        db.add(order)
        db.commit()
        mock_send.return_value = {"success": True}

        result = await handle_article_approval(order.id, approved=True, modified=True, db=db)
        assert result["consecutive_approvals"] == 0

    @pytest.mark.asyncio
    async def test_rejection_resets_counter(self, db):
        campaign = make_campaign(db, consecutive_approvals=7)
        d = make_domain(db, "pub5.com")
        order = Order(
            id="order-rej-1",
            campaign_id=campaign.id,
            domain_id=d.id,
            link_type="Guest Post",
            status="pending_review",
            article_content="Test",
        )
        db.add(order)
        db.commit()

        result = await handle_article_approval(order.id, approved=False, modified=False, db=db)
        assert result["action"] == "rejected"
        db.refresh(campaign)
        assert campaign.consecutive_approvals == 0
        db.refresh(order)
        assert order.status == "rejected"

    @pytest.mark.asyncio
    @patch("backend.services.slack_notifier.send_slack_alert", new_callable=AsyncMock)
    @patch("backend.services.order_sender.send_order", new_callable=AsyncMock)
    async def test_graduates_to_auto_at_threshold(self, mock_send, mock_slack, db):
        campaign = make_campaign(db, consecutive_approvals=9, approval_threshold=10)
        d = make_domain(db, "pub6.com")
        order = Order(
            id="order-grad-1",
            campaign_id=campaign.id,
            domain_id=d.id,
            link_type="Guest Post",
            price=50,
            status="pending_review",
            article_content="Test",
        )
        db.add(order)
        db.commit()
        mock_send.return_value = {"success": True}

        result = await handle_article_approval(order.id, approved=True, modified=False, db=db)
        assert result["approval_mode"] == "auto"
        db.refresh(campaign)
        assert campaign.approval_mode == "auto"
        assert campaign.consecutive_approvals == 10
        # Should have sent graduation slack alert
        mock_slack.assert_called()
