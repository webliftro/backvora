"""Tests for slack_notifier.py."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from backend.services.slack_notifier import send_slack_alert, _format_message
from backend.models import Order, Domain


# ── Message formatting ──

class TestFormatMessage:
    def test_verified(self):
        msg = _format_message("VERIFIED", "example.com", "$100 USD", "https://example.com/post", "PayPal: pub@ex.com", {})
        assert "✅" in msg
        assert "example.com" in msg
        assert "$100 USD" in msg
        assert "https://example.com/post" in msg
        assert "Pay now?" in msg

    def test_payment_confirmed(self):
        msg = _format_message("PAYMENT_CONFIRMED", "example.com", "$100 USD", "", "PayPal", {})
        assert "💰" in msg
        assert "Payment confirmed" in msg

    def test_link_removed(self):
        msg = _format_message("LINK_REMOVED", "example.com", "", "https://example.com/post", "", {})
        assert "🔴" in msg
        assert "removed" in msg.lower()

    def test_auto_fix_email_sent(self):
        msg = _format_message("AUTO_FIX_EMAIL_SENT", "example.com", "", "", "", {"issues_text": "wrong anchor"})
        assert "📧" in msg
        assert "wrong anchor" in msg

    def test_publisher_stale(self):
        msg = _format_message("PUBLISHER_STALE", "example.com", "", "", "", {})
        assert "⏰" in msg
        assert "No response" in msg

    def test_generic_issue(self):
        msg = _format_message("WRONG_ANCHORS", "example.com", "$50 USD", "https://example.com/post", "", {"issues_text": "bad anchor"})
        assert "⚠️" in msg
        assert "WRONG_ANCHORS" in msg


# ── Webhook calls ──

class TestSendSlackAlert:
    @pytest.mark.asyncio
    async def test_successful_send(self):
        order = MagicMock(spec=Order)
        order.price = 100
        order.currency = "USD"
        order.live_url = "https://example.com/post"
        domain = MagicMock(spec=Domain)
        domain.domain = "example.com"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        client = AsyncMock()
        client.post = AsyncMock(return_value=mock_resp)
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.services.slack_notifier.httpx.AsyncClient", return_value=cm), \
             patch("backend.services.slack_notifier.settings") as mock_settings:
            mock_settings.slack_webhook_url = "https://hooks.slack.com/test"
            result = await send_slack_alert("VERIFIED", order, domain)

        assert result is True
        client.post.assert_called_once()
        call_kwargs = client.post.call_args
        assert "text" in call_kwargs.kwargs.get("json", call_kwargs[1].get("json", {}))

    @pytest.mark.asyncio
    async def test_no_webhook_url(self):
        with patch("backend.services.slack_notifier.settings") as mock_settings:
            mock_settings.slack_webhook_url = ""
            result = await send_slack_alert("VERIFIED")
        assert result is False

    @pytest.mark.asyncio
    async def test_webhook_failure_500(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        client = AsyncMock()
        client.post = AsyncMock(return_value=mock_resp)
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.services.slack_notifier.httpx.AsyncClient", return_value=cm), \
             patch("backend.services.slack_notifier.settings") as mock_settings:
            mock_settings.slack_webhook_url = "https://hooks.slack.com/test"
            result = await send_slack_alert("VERIFIED")
        assert result is False

    @pytest.mark.asyncio
    async def test_webhook_timeout(self):
        client = AsyncMock()
        client.post = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.services.slack_notifier.httpx.AsyncClient", return_value=cm), \
             patch("backend.services.slack_notifier.settings") as mock_settings:
            mock_settings.slack_webhook_url = "https://hooks.slack.com/test"
            result = await send_slack_alert("VERIFIED")
        assert result is False

    @pytest.mark.asyncio
    async def test_webhook_network_error(self):
        client = AsyncMock()
        client.post = AsyncMock(side_effect=Exception("network error"))
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.services.slack_notifier.httpx.AsyncClient", return_value=cm), \
             patch("backend.services.slack_notifier.settings") as mock_settings:
            mock_settings.slack_webhook_url = "https://hooks.slack.com/test"
            result = await send_slack_alert("LINK_REMOVED")
        assert result is False
