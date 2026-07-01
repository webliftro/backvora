"""
Unit tests for link_monitor.py — verification checks.
"""

import pytest
import respx
import httpx
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

from backend.services.link_monitor import verify_live_url, check_all_live_links
from backend.models import Order, OrderLink, LinkCheck
from tests.conftest import make_html

# The sample_order fixture has:
#   domain = "example.com"
#   OrderLink 1: target_url="https://mysite.com/page", anchor="my site", slot=1
#   OrderLink 2: target_url="https://mysite.com/other", anchor="click here", slot=2
#   article_content ~ 200 words

GOOD_HTML = make_html(
    links=[
        ("https://mysite.com/page", "my site", ""),
        ("https://mysite.com/other", "click here", ""),
    ],
    text="word " * 300,
)


@pytest.mark.asyncio
class TestVerifyLiveUrl:

    @respx.mock
    async def test_verified_all_good(self, db, sample_order):
        respx.get("https://example.com/article-1").mock(
            return_value=httpx.Response(200, text=GOOD_HTML)
        )
        result = await verify_live_url(sample_order.id, "https://example.com/article-1", db, retry_count=0)
        assert result["verified"] is True
        assert result["status"] == "VERIFIED"
        db.refresh(sample_order)
        # sent → published (not live, since live requires paid status)
        assert sample_order.status == "published"
        assert sample_order.live_url == "https://example.com/article-1"

    @respx.mock
    async def test_wrong_anchors(self, db, sample_order):
        html = make_html(
            links=[
                ("https://mysite.com/page", "WRONG ANCHOR", ""),
                ("https://mysite.com/other", "click here", ""),
            ],
            text="word " * 300,
        )
        respx.get("https://example.com/art").mock(return_value=httpx.Response(200, text=html))
        result = await verify_live_url(sample_order.id, "https://example.com/art", db, retry_count=0)
        assert result["verified"] is False
        assert "WRONG_ANCHORS" in result["status"]
        assert any("WRONG ANCHOR" in i for i in result["issues"])

    @respx.mock
    async def test_missing_links(self, db, sample_order):
        html = make_html(
            links=[("https://mysite.com/page", "my site", "")],
            text="word " * 300,
        )
        respx.get("https://example.com/art").mock(return_value=httpx.Response(200, text=html))
        result = await verify_live_url(sample_order.id, "https://example.com/art", db, retry_count=0)
        assert result["verified"] is False
        assert "MISSING_LINKS" in result["status"]

    @respx.mock
    async def test_nofollow(self, db, sample_order):
        html = make_html(
            links=[
                ("https://mysite.com/page", "my site", "nofollow"),
                ("https://mysite.com/other", "click here", ""),
            ],
            text="word " * 300,
        )
        respx.get("https://example.com/art").mock(return_value=httpx.Response(200, text=html))
        result = await verify_live_url(sample_order.id, "https://example.com/art", db, retry_count=0)
        assert result["verified"] is False
        assert "NOFOLLOW" in result["status"]

    @respx.mock
    async def test_sponsored_rel(self, db, sample_order):
        html = make_html(
            links=[
                ("https://mysite.com/page", "my site", "sponsored"),
                ("https://mysite.com/other", "click here", ""),
            ],
            text="word " * 300,
        )
        respx.get("https://example.com/art").mock(return_value=httpx.Response(200, text=html))
        result = await verify_live_url(sample_order.id, "https://example.com/art", db, retry_count=0)
        assert "NOFOLLOW" in result["status"]

    @respx.mock
    async def test_images_missing(self, db, sample_order):
        html = make_html(
            links=[
                ("https://mysite.com/page", "my site", ""),
                ("https://mysite.com/other", "click here", ""),
            ],
            text="word " * 300, images=0,
        )
        respx.get("https://example.com/art").mock(return_value=httpx.Response(200, text=html))
        with patch("backend.services.link_monitor._has_images_dir", return_value=True):
            result = await verify_live_url(sample_order.id, "https://example.com/art", db, retry_count=0)
        assert "IMAGES_MISSING" in result["status"]

    @respx.mock
    async def test_images_present_ok(self, db, sample_order):
        html = make_html(
            links=[
                ("https://mysite.com/page", "my site", ""),
                ("https://mysite.com/other", "click here", ""),
            ],
            text="word " * 300, images=2,
        )
        respx.get("https://example.com/art").mock(return_value=httpx.Response(200, text=html))
        with patch("backend.services.link_monitor._has_images_dir", return_value=True):
            result = await verify_live_url(sample_order.id, "https://example.com/art", db, retry_count=0)
        assert "IMAGES_MISSING" not in result.get("status", "")

    @respx.mock
    async def test_truncated_content(self, db, sample_order):
        html = make_html(
            links=[
                ("https://mysite.com/page", "my site", ""),
                ("https://mysite.com/other", "click here", ""),
            ],
            text="short",  # way less than 70% of ~200 word article
        )
        respx.get("https://example.com/art").mock(return_value=httpx.Response(200, text=html))
        result = await verify_live_url(sample_order.id, "https://example.com/art", db, retry_count=0)
        assert "ARTICLE_INCOMPLETE" in result["status"]

    @respx.mock
    async def test_not_live_404(self, db, sample_order):
        respx.get("https://example.com/art").mock(return_value=httpx.Response(404, text="nope"))
        result = await verify_live_url(sample_order.id, "https://example.com/art", db, retry_count=0)
        assert result["verified"] is False
        assert "NOT_LIVE" in result["status"]
        assert result["http_status"] == 404

    @respx.mock
    async def test_not_live_timeout(self, db, sample_order):
        respx.get("https://example.com/art").mock(side_effect=httpx.ConnectError("timeout"))
        result = await verify_live_url(sample_order.id, "https://example.com/art", db, retry_count=0)
        assert result["verified"] is False
        assert "NOT_LIVE" in result["status"]

    async def test_wrong_domain(self, db, sample_order):
        result = await verify_live_url(sample_order.id, "https://wrong.com/art", db, retry_count=0)
        assert result["verified"] is False
        assert "NOT_LIVE" in result["status"]

    @respx.mock
    async def test_multiple_issues(self, db, sample_order):
        html = make_html(
            links=[("https://mysite.com/page", "WRONG", "nofollow")],
            text="word " * 300,
        )
        respx.get("https://example.com/art").mock(return_value=httpx.Response(200, text=html))
        result = await verify_live_url(sample_order.id, "https://example.com/art", db, retry_count=0)
        assert "WRONG_ANCHORS" in result["status"]
        assert "NOFOLLOW" in result["status"]
        assert "MISSING_LINKS" in result["status"]

    @respx.mock
    async def test_link_check_saved(self, db, sample_order):
        respx.get("https://example.com/art").mock(return_value=httpx.Response(200, text=GOOD_HTML))
        await verify_live_url(sample_order.id, "https://example.com/art", db, retry_count=0)
        checks = db.query(LinkCheck).filter(LinkCheck.order_id == sample_order.id).all()
        assert len(checks) == 1
        assert checks[0].status == "VERIFIED"

    async def test_order_not_found(self, db):
        with pytest.raises(ValueError, match="not found"):
            await verify_live_url("fake-id", "https://x.com", db, retry_count=0)

    @respx.mock
    async def test_legacy_single_link_order(self, db, sample_domain, sample_campaign):
        """Order with target_url/anchor_text but no OrderLinks."""
        o = Order(
            id="order-legacy", campaign_id=sample_campaign.id,
            domain_id=sample_domain.id, link_type="Guest Post",
            status="sent", target_url="https://mysite.com/page", anchor_text="my site",
        )
        db.add(o)
        db.commit()
        html = make_html(links=[("https://mysite.com/page", "my site", "")], text="word " * 100)
        respx.get("https://example.com/art").mock(return_value=httpx.Response(200, text=html))
        result = await verify_live_url(o.id, "https://example.com/art", db, retry_count=0)
        assert result["verified"] is True

    @respx.mock
    async def test_url_without_scheme(self, db, sample_order):
        respx.get("https://example.com/art").mock(return_value=httpx.Response(200, text=GOOD_HTML))
        result = await verify_live_url(sample_order.id, "example.com/art", db, retry_count=0)
        assert result["verified"] is True


@pytest.mark.asyncio
class TestCheckAllLiveLinks:

    @respx.mock
    async def test_picks_up_old_orders(self, db, sample_order):
        sample_order.status = "live"
        sample_order.live_url = "https://example.com/art"
        sample_order.last_checked_at = datetime.utcnow() - timedelta(days=45)
        db.commit()

        respx.get("https://example.com/art").mock(return_value=httpx.Response(200, text=GOOD_HTML))
        with patch("backend.services.slack_notifier.send_slack_alert", new_callable=AsyncMock, return_value=True):
            result = await check_all_live_links(db)
        assert result["total_checked"] == 1
        assert result["verified"] == 1

    async def test_skips_recent_orders(self, db, sample_order):
        sample_order.status = "live"
        sample_order.live_url = "https://example.com/art"
        sample_order.last_checked_at = datetime.utcnow() - timedelta(days=5)
        db.commit()

        result = await check_all_live_links(db)
        assert result["total_checked"] == 0

    @respx.mock
    async def test_removed_link_updates_status(self, db, sample_order, sample_domain):
        sample_order.status = "live"
        sample_order.live_url = "https://example.com/art"
        sample_order.last_checked_at = None
        db.commit()

        respx.get("https://example.com/art").mock(return_value=httpx.Response(404, text="gone"))
        with patch("backend.services.slack_notifier.send_slack_alert", new_callable=AsyncMock, return_value=True) as mock_slack, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = await check_all_live_links(db)
        assert result["removed"] == 1
        db.refresh(sample_order)
        assert sample_order.status == "offline"
        mock_slack.assert_called_once()
        assert mock_slack.call_args[0][0] == "LINK_OFFLINE"
