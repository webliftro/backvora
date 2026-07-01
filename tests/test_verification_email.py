"""Tests for send_verification_fix_request in reply_parser.py."""

import pytest
from unittest.mock import patch, MagicMock

from backend.services.reply_parser import send_verification_fix_request


def _get_body_text(sent_msg):
    """Extract plain text body from a MIMEMultipart message (handles base64)."""
    for part in sent_msg.walk():
        if part.get_content_type() == "text/plain":
            return part.get_payload(decode=True).decode("utf-8")
    return sent_msg.get_payload(decode=True).decode("utf-8")


class TestSendVerificationFixRequest:

    @pytest.mark.asyncio
    async def test_single_issue(self):
        mock_smtp_instance = MagicMock()

        with patch("smtplib.SMTP_SSL", return_value=mock_smtp_instance):
            await send_verification_fix_request(
                "pub@example.com", "example.com", "John",
                ["Link #1: anchor should be 'my site' but found 'click here'"],
            )

        mock_smtp_instance.send_message.assert_called_once()
        sent_msg = mock_smtp_instance.send_message.call_args[0][0]
        body = _get_body_text(sent_msg)
        assert "John" in body
        assert "example.com" in body
        assert "anchor should be" in body
        assert "small fixes needed" in sent_msg["Subject"]
        mock_smtp_instance.quit.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_issues(self):
        mock_smtp_instance = MagicMock()

        issues = [
            "Link #1: anchor should be 'my site' but found 'click here'",
            'Link #2: has rel="nofollow" (expected dofollow)',
            "Order had images but none found on published page",
        ]

        with patch("smtplib.SMTP_SSL", return_value=mock_smtp_instance):
            await send_verification_fix_request(
                "pub@example.com", "example.com", "Jane", issues,
            )

        sent_msg = mock_smtp_instance.send_message.call_args[0][0]
        body = _get_body_text(sent_msg)
        for issue in issues:
            assert issue in body

    @pytest.mark.asyncio
    async def test_no_contact_name(self):
        mock_smtp_instance = MagicMock()

        with patch("smtplib.SMTP_SSL", return_value=mock_smtp_instance):
            await send_verification_fix_request(
                "pub@example.com", "example.com", None,
                ["Link missing"],
            )

        sent_msg = mock_smtp_instance.send_message.call_args[0][0]
        body = _get_body_text(sent_msg)
        assert "Hi there" in body

    @pytest.mark.asyncio
    async def test_smtp_settings_used(self):
        mock_smtp_instance = MagicMock()

        with patch("smtplib.SMTP_SSL", return_value=mock_smtp_instance) as mock_cls:
            await send_verification_fix_request(
                "pub@example.com", "example.com", "Bob", ["issue"],
            )

        mock_cls.assert_called_once()
        mock_smtp_instance.login.assert_called_once()
        mock_smtp_instance.quit.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_headers(self):
        mock_smtp_instance = MagicMock()

        with patch("smtplib.SMTP_SSL", return_value=mock_smtp_instance):
            await send_verification_fix_request(
                "pub@example.com", "example.com", "Alice", ["issue"],
            )

        sent_msg = mock_smtp_instance.send_message.call_args[0][0]
        assert sent_msg["To"] == "pub@example.com"
        assert "example.com" in sent_msg["Subject"]
