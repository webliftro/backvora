"""
Unit tests for reply_parser.py — verification fix request emails.
"""

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
    async def test_sends_email_with_issues(self):
        mock_smtp = MagicMock()

        issues = [
            "Link #1: anchor should be 'best cam sites' but found 'click here'",
            "Link #2: target URL 'https://mysite.com/girls' not found on page",
        ]
        with patch("smtplib.SMTP_SSL", return_value=mock_smtp):
            await send_verification_fix_request(
                "admin@pub.com", "pub.com", "John", issues
            )

        mock_smtp.send_message.assert_called_once()
        sent_msg = mock_smtp.send_message.call_args[0][0]
        assert sent_msg["To"] == "admin@pub.com"
        assert "fixes needed" in sent_msg["Subject"]
        body = _get_body_text(sent_msg)
        assert "best cam sites" in body
        assert "click here" in body
        assert "mysite.com/girls" in body
        mock_smtp.quit.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_fallback_name(self):
        mock_smtp = MagicMock()

        with patch("smtplib.SMTP_SSL", return_value=mock_smtp):
            await send_verification_fix_request(
                "x@y.com", "y.com", None, ["some issue"]
            )
        sent_msg = mock_smtp.send_message.call_args[0][0]
        body = _get_body_text(sent_msg)
        assert "Hi there" in body
