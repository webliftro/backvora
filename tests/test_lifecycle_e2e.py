"""
Integration / E2E tests for the full BackVora lifecycle pipeline.
"""

import pytest
import respx
import httpx
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from backend.models import Order, OrderLink, LinkCheck, DomainPaymentMethod, Campaign
from backend.services.link_monitor import verify_live_url, check_all_live_links
from backend.services.slack_notifier import send_slack_alert
from tests.conftest import make_html

# Good HTML matching sample_order's links
GOOD_HTML = make_html(
    links=[
        ("https://mysite.com/page", "my site", ""),
        ("https://mysite.com/other", "click here", ""),
    ],
    text="word " * 300,
)


@pytest.mark.asyncio
class TestFullLifecycle:
    """order sent → verify → Slack → payment → confirmation email."""

    @respx.mock
    async def test_happy_path(self, db, sample_order, sample_domain, sample_payment_method):
        # Step 1: Verify URL
        respx.get("https://example.com/great-article").mock(
            return_value=httpx.Response(200, text=GOOD_HTML)
        )
        result = await verify_live_url(
            sample_order.id, "https://example.com/great-article", db, retry_count=0
        )
        assert result["verified"] is True
        db.refresh(sample_order)
        # sent → published (live requires paid status)
        assert sample_order.status == "published"

        # Step 2: Slack alert
        slack_route = respx.post("https://hooks.slack.com/test/webhook").mock(
            return_value=httpx.Response(200, text="ok")
        )
        ok = await send_slack_alert("VERIFIED", sample_order, sample_domain, extra={
            "url": sample_order.live_url,
            "payment_info": "PayPal: pub@example.com",
        })
        assert ok is True
        assert slack_route.called

        # Step 3: Payment
        sample_order.paid_at = datetime.utcnow()
        sample_order.status = "paid"
        db.commit()

        # Step 4: Confirmation email
        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value = mock_smtp
            from backend.services.reply_parser import send_followup_custom
            await send_followup_custom(
                "pub@example.com", "example.com", "John Publisher", "Payment sent!"
            )
            mock_smtp.send_message.assert_called_once()

        # Step 5: Payment Slack alert
        ok = await send_slack_alert("PAYMENT_CONFIRMED", sample_order, sample_domain, extra={
            "payment_info": "PayPal: pub@example.com",
        })
        assert ok is True


@pytest.mark.asyncio
class TestVerificationFailureFlow:
    """Bad anchors → fix email → publisher fixes → re-verify → success."""

    @respx.mock
    async def test_fail_then_fix(self, db, sample_order, sample_domain):
        # Step 1: Wrong anchors
        bad_html = make_html(
            links=[
                ("https://mysite.com/page", "WRONG TEXT", ""),
                ("https://mysite.com/other", "click here", ""),
            ],
            text="word " * 300,
        )
        respx.get("https://example.com/article").mock(
            return_value=httpx.Response(200, text=bad_html)
        )
        result = await verify_live_url(
            sample_order.id, "https://example.com/article", db, retry_count=0
        )
        assert result["verified"] is False
        assert "WRONG_ANCHORS" in result["status"]

        # Step 2: Send fix request
        with patch("smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value = mock_smtp
            from backend.services.reply_parser import send_verification_fix_request
            await send_verification_fix_request(
                "pub@example.com", "example.com", "John Publisher", result["issues"]
            )
            mock_smtp.send_message.assert_called_once()
            sent_msg = mock_smtp.send_message.call_args[0][0]
            # Decode body from MIME
            for part in sent_msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode("utf-8")
                    break
            assert "WRONG TEXT" in body or "my site" in body

        # Step 3: Slack alert
        slack_route = respx.post("https://hooks.slack.com/test/webhook").mock(
            return_value=httpx.Response(200, text="ok")
        )
        await send_slack_alert("AUTO_FIX_EMAIL_SENT", sample_order, sample_domain, extra={
            "issues_text": "; ".join(result["issues"]),
        })
        assert slack_route.called

        # Step 4: Publisher fixes, re-verify
        respx.reset()
        respx.get("https://example.com/article").mock(
            return_value=httpx.Response(200, text=GOOD_HTML)
        )
        result2 = await verify_live_url(
            sample_order.id, "https://example.com/article", db, retry_count=0
        )
        assert result2["verified"] is True

        # 2 LinkCheck records
        checks = db.query(LinkCheck).filter(LinkCheck.order_id == sample_order.id).all()
        assert len(checks) == 2


@pytest.mark.asyncio
class TestMonthlyHealthCheck:

    @respx.mock
    async def test_link_still_live(self, db, sample_order, sample_domain):
        sample_order.status = "live"
        sample_order.live_url = "https://example.com/article"
        sample_order.last_checked_at = datetime.utcnow() - timedelta(days=45)
        db.commit()

        respx.get("https://example.com/article").mock(
            return_value=httpx.Response(200, text=GOOD_HTML)
        )
        with patch("backend.services.slack_notifier.send_slack_alert", return_value=True):
            result = await check_all_live_links(db)
        assert result["verified"] == 1
        assert result["removed"] == 0

    @respx.mock
    async def test_link_removed(self, db, sample_order, sample_domain):
        sample_order.status = "live"
        sample_order.live_url = "https://example.com/article"
        sample_order.last_checked_at = None
        db.commit()

        respx.get("https://example.com/article").mock(
            return_value=httpx.Response(404, text="gone")
        )
        with patch("backend.services.slack_notifier.send_slack_alert", new_callable=AsyncMock, return_value=True) as mock_slack, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = await check_all_live_links(db)
        assert result["removed"] == 1
        db.refresh(sample_order)
        assert sample_order.status == "offline"
        mock_slack.assert_called_once()


@pytest.mark.asyncio
class TestEdgeCases:

    async def test_wrong_domain_url(self, db, sample_order):
        result = await verify_live_url(
            sample_order.id, "https://totally-wrong.com/article", db
        )
        assert result["verified"] is False
        assert "NOT_LIVE" in result["status"]
        assert "doesn't match" in result["issues"][0]

    @respx.mock
    async def test_page_timeout(self, db, sample_order):
        respx.get("https://example.com/slow").mock(
            side_effect=httpx.ConnectTimeout("timeout")
        )
        result = await verify_live_url(
            sample_order.id, "https://example.com/slow", db
        )
        assert result["verified"] is False
        assert "NOT_LIVE" in result["status"]

    @respx.mock
    async def test_url_without_scheme(self, db, sample_order):
        respx.get("https://example.com/article").mock(
            return_value=httpx.Response(200, text=GOOD_HTML)
        )
        result = await verify_live_url(
            sample_order.id, "example.com/article", db
        )
        assert result["verified"] is True

    @respx.mock
    async def test_no_target_urls(self, db, sample_domain, sample_campaign):
        o = Order(
            id="order-empty", campaign_id=sample_campaign.id,
            domain_id=sample_domain.id, link_type="Guest Post", status="sent",
        )
        db.add(o)
        db.commit()
        respx.get("https://example.com/art").mock(
            return_value=httpx.Response(200, text="<html><body>hi</body></html>")
        )
        result = await verify_live_url(o.id, "https://example.com/art", db, retry_count=0)
        assert result["verified"] is False
        assert "MISSING_LINKS" in result["status"]

    @respx.mock
    async def test_multiple_orders_health_check(self, db, sample_domain, sample_campaign):
        for i in range(3):
            o = Order(
                id=f"order-hc-{i}", campaign_id=sample_campaign.id,
                domain_id=sample_domain.id, link_type="Guest Post",
                status="live", live_url=f"https://example.com/art-{i}",
                last_checked_at=None, target_url="https://mysite.com/page",
                anchor_text="my site",
            )
            db.add(o)
        db.commit()

        html = make_html(links=[("https://mysite.com/page", "my site", "")], text="word " * 100)
        for i in range(3):
            respx.get(f"https://example.com/art-{i}").mock(
                return_value=httpx.Response(200, text=html)
            )
        with patch("backend.services.slack_notifier.send_slack_alert", return_value=True):
            result = await check_all_live_links(db)
        assert result["total_checked"] == 3
        assert result["verified"] == 3
