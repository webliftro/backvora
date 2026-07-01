"""E2E tests for Campaign Auto-Pilot pipeline."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from backend.models import (
    Campaign, Domain, Contact, LinkPrice, Order, OrderLink,
    DomainStatus,
)
from backend.services.campaign_autopilot import (
    run_campaign_cycle,
    handle_article_approval,
    should_create_order,
)


def make_campaign(db, **kwargs):
    defaults = dict(
        name="E2E Campaign",
        target_site="mysite.com",
        status="active",
        mode="auto",
        approval_mode="review",
        velocity_period_days=7,
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


def make_domain_with_pricing(db, name, price=100.0, dr=40, traffic=5000):
    d = Domain(
        domain=name,
        domain_rating=dr,
        organic_traffic=traffic,
        status=DomainStatus.DEAL_CLOSED,
        email=f"pub@{name}",
    )
    db.add(d)
    db.commit()
    Contact(domain_id=d.id, email=f"pub@{name}", name="Pub", is_primary=True)
    c = Contact(domain_id=d.id, email=f"pub@{name}", name="Pub", is_primary=True)
    db.add(c)
    lp = LinkPrice(domain_id=d.id, link_type="Guest Post", price=price, currency="USD")
    db.add(lp)
    db.commit()
    return d


class TestFullAutoCycle:
    @pytest.mark.asyncio
    @patch("backend.services.order_sender.send_order", new_callable=AsyncMock)
    @patch("backend.services.slack_notifier.send_article_for_review", new_callable=AsyncMock)
    @patch("backend.services.article_writer.generate_article", new_callable=AsyncMock)
    async def test_full_cycle_review_then_approve(self, mock_gen, mock_slack, mock_send, db):
        """Full: campaign → pick domain → article → slack review → approve → send."""
        campaign = make_campaign(db)
        d = make_domain_with_pricing(db, "pub-e2e.com", price=100)
        mock_gen.return_value = {"success": True, "article_content": "Article"}
        mock_send.return_value = {"success": True}

        # Run cycle - should go to review
        result = await run_campaign_cycle(campaign.id, db)
        assert result["success"] is True
        assert result["action"] == "pending_review"
        mock_slack.assert_called_once()

        # Approve
        order_id = result["order_id"]
        approve_result = await handle_article_approval(order_id, True, False, db)
        assert approve_result["success"] is True
        assert approve_result["action"] == "approved_and_sent"
        mock_send.assert_called_once()

        db.refresh(campaign)
        assert campaign.budget_spent == 100
        assert campaign.last_order_sent_at is not None


class TestBudgetExhaustion:
    @pytest.mark.asyncio
    @patch("backend.services.slack_notifier.send_slack_alert", new_callable=AsyncMock)
    @patch("backend.services.order_sender.send_order", new_callable=AsyncMock)
    @patch("backend.services.article_writer.generate_article", new_callable=AsyncMock)
    async def test_budget_exhaustion_pauses_campaign(self, mock_gen, mock_send, mock_slack, db):
        """Multiple cycles until budget runs out → campaign pauses."""
        campaign = make_campaign(db, budget_total=250, budget_spent=0, approval_mode="auto")

        for i in range(5):
            d = make_domain_with_pricing(db, f"site{i}.com", price=100)

        mock_gen.return_value = {"success": True}
        mock_send.return_value = {"success": True}

        # First cycle: spend 100, budget_spent=100
        r1 = await run_campaign_cycle(campaign.id, db)
        assert r1["success"] is True
        db.refresh(campaign)
        assert campaign.budget_spent == 100
        # Reset velocity for next cycle
        campaign.last_order_sent_at = datetime.utcnow() - timedelta(days=8)
        db.commit()

        # Second cycle: spend 100, budget_spent=200
        r2 = await run_campaign_cycle(campaign.id, db)
        assert r2["success"] is True
        db.refresh(campaign)
        assert campaign.budget_spent == 200
        campaign.last_order_sent_at = datetime.utcnow() - timedelta(days=8)
        db.commit()

        # Third cycle: spend 100, budget_spent=300 >= 250 → paused
        r3 = await run_campaign_cycle(campaign.id, db)
        assert r3["success"] is True
        db.refresh(campaign)
        assert campaign.status == "paused"

        # Fourth cycle: should fail because paused
        campaign.last_order_sent_at = datetime.utcnow() - timedelta(days=8)
        db.commit()
        r4 = await run_campaign_cycle(campaign.id, db)
        assert r4["success"] is False


class TestVelocityEnforcement:
    @pytest.mark.asyncio
    async def test_cant_send_faster_than_velocity(self, db):
        """Velocity enforcement: can't send faster than configured."""
        campaign = make_campaign(db, velocity_period_days=7,
                                 last_order_sent_at=datetime.utcnow() - timedelta(days=3))
        d = make_domain_with_pricing(db, "vel.com")

        result = await run_campaign_cycle(campaign.id, db)
        assert result["success"] is False
        assert "Not eligible" in result["reason"]


class TestSelfLearningGraduation:
    @pytest.mark.asyncio
    @patch("backend.services.slack_notifier.send_slack_alert", new_callable=AsyncMock)
    @patch("backend.services.order_sender.send_order", new_callable=AsyncMock)
    @patch("backend.services.slack_notifier.send_article_for_review", new_callable=AsyncMock)
    @patch("backend.services.article_writer.generate_article", new_callable=AsyncMock)
    async def test_graduation_after_threshold(self, mock_gen, mock_slack_review, mock_send, mock_slack_alert, db):
        """10 clean approvals → auto mode → next article sent without review."""
        campaign = make_campaign(db, approval_threshold=10, consecutive_approvals=0)
        mock_gen.return_value = {"success": True}
        mock_send.return_value = {"success": True}

        # Create 11 domains
        for i in range(11):
            make_domain_with_pricing(db, f"grad{i}.com", price=10)

        # Run 10 cycles + approve each
        for i in range(10):
            campaign.last_order_sent_at = None
            db.commit()
            result = await run_campaign_cycle(campaign.id, db)
            assert result["success"] is True
            await handle_article_approval(result["order_id"], True, False, db)

        db.refresh(campaign)
        assert campaign.approval_mode == "auto"
        assert campaign.consecutive_approvals == 10

        # 11th cycle should send directly (auto mode)
        campaign.last_order_sent_at = None
        db.commit()
        result = await run_campaign_cycle(campaign.id, db)
        assert result["success"] is True
        assert result["action"] == "sent"


class TestSelfLearningReset:
    @pytest.mark.asyncio
    @patch("backend.services.order_sender.send_order", new_callable=AsyncMock)
    @patch("backend.services.slack_notifier.send_article_for_review", new_callable=AsyncMock)
    @patch("backend.services.article_writer.generate_article", new_callable=AsyncMock)
    async def test_rejection_resets_counter(self, mock_gen, mock_slack, mock_send, db):
        """8 approvals → rejection → counter resets → back to review."""
        campaign = make_campaign(db, consecutive_approvals=0, approval_threshold=10)
        mock_gen.return_value = {"success": True}
        mock_send.return_value = {"success": True}

        for i in range(10):
            make_domain_with_pricing(db, f"reset{i}.com", price=10)

        # 8 clean approvals
        for i in range(8):
            campaign.last_order_sent_at = None
            db.commit()
            result = await run_campaign_cycle(campaign.id, db)
            assert result["success"] is True
            await handle_article_approval(result["order_id"], True, False, db)

        db.refresh(campaign)
        assert campaign.consecutive_approvals == 8
        assert campaign.approval_mode == "review"

        # 9th: reject
        campaign.last_order_sent_at = None
        db.commit()
        result = await run_campaign_cycle(campaign.id, db)
        await handle_article_approval(result["order_id"], False, False, db)

        db.refresh(campaign)
        assert campaign.consecutive_approvals == 0
        assert campaign.approval_mode == "review"
