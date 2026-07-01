"""
Email service - sending outreach emails via Resend API.
https://resend.com/docs
"""

import httpx
from typing import Optional

from ..config import settings


class EmailError(Exception):
    """Email sending error."""
    pass


class EmailService:
    """Service for sending outreach emails via Resend."""
    
    RESEND_API_URL = "https://api.resend.com/emails"
    
    def __init__(self):
        self.api_key = settings.resend_api_key
        self.from_name = settings.email_from_name
        self.from_email = settings.email_from_address
        
        if not self.api_key:
            raise EmailError("RESEND_API_KEY not configured")
    
    async def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        reply_to: Optional[str] = None,
        tags: Optional[list[dict]] = None,
    ) -> dict:
        """
        Send an email via Resend.
        
        Args:
            to_email: Recipient email
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            reply_to: Optional reply-to address
            tags: Optional tags for tracking [{"name": "category", "value": "outreach"}]
            
        Returns:
            Resend API response with email ID
        """
        payload = {
            "from": f"{self.from_name} <{self.from_email}>",
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
        
        if html_body:
            payload["html"] = html_body
        
        if reply_to:
            payload["reply_to"] = [reply_to]
        
        if tags:
            payload["tags"] = tags
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.RESEND_API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=30.0,
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    error_data = response.json()
                    raise EmailError(f"Resend error: {error_data.get('message', response.text)}")
                    
            except httpx.HTTPError as e:
                raise EmailError(f"HTTP error: {str(e)}")
    
    async def send_batch(
        self,
        emails: list[dict],
    ) -> dict:
        """
        Send multiple emails in a batch (up to 100).
        
        Args:
            emails: List of email dicts with to, subject, text, html (optional)
            
        Returns:
            Resend batch response
        """
        batch_payload = []
        
        for email in emails[:100]:  # Resend limit
            payload = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [email["to"]],
                "subject": email["subject"],
                "text": email["text"],
            }
            if "html" in email:
                payload["html"] = email["html"]
            if "reply_to" in email:
                payload["reply_to"] = [email["reply_to"]]
            batch_payload.append(payload)
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.RESEND_API_URL}/batch",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=batch_payload,
                    timeout=60.0,
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    error_data = response.json()
                    raise EmailError(f"Resend batch error: {error_data.get('message', response.text)}")
                    
            except httpx.HTTPError as e:
                raise EmailError(f"HTTP error: {str(e)}")
    
    def render_template(
        self,
        template: str,
        variables: dict[str, str],
    ) -> str:
        """
        Render an email template with variables.
        
        Supports {variable} and {{variable}} syntax.
        
        Args:
            template: Template string with placeholders
            variables: Dict of variable values
            
        Returns:
            Rendered string
        """
        result = template
        for key, value in variables.items():
            result = result.replace(f"{{{key}}}", str(value))
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result
