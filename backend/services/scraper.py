"""
Email scraper and contacts grabber service.
"""

import re
import asyncio
import random
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import settings


class ScraperError(Exception):
    pass


class EmailScraper:
    """Service for scraping emails from websites."""
    
    CONTACT_PATHS = [
        "/contact", "/contact-us", "/contactus", "/about", "/about-us",
        "/privacy", "/privacy-policy", "/terms", "/terms-of-service",
        "/dmca", "/legal", "/imprint", "/impressum",
    ]
    
    EMAIL_PATTERN = re.compile(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    )
    
    BLACKLIST_PATTERNS = [
        r'.*@example\.com', r'.*@test\.com', r'.*@localhost',
        r'noreply@.*', r'no-reply@.*', r'abuse@.*',
        r'postmaster@.*', r'hostmaster@.*', r'privacy@.*',
        r'legal@.*', r'dmca@.*', r'copyright@.*',
    ]
    
    # File extensions that get falsely matched as emails (e.g. sprite@2x.png)
    FAKE_EMAIL_EXTENSIONS = {
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico', '.bmp',
        '.css', '.js', '.map', '.woff', '.woff2', '.ttf', '.eot',
        '.pdf', '.zip', '.mp4', '.mp3', '.webm',
    }
    
    def __init__(self):
        self.delay = settings.scrape_delay_seconds
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
    
    async def scrape_domain(self, domain: str) -> list[dict[str, str]]:
        results = []
        seen_emails = set()
        base_url = f"https://{domain}"
        
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=self.headers) as client:
            for path in self.CONTACT_PATHS:
                url = urljoin(base_url, path)
                try:
                    response = await client.get(url)
                    if response.status_code == 200:
                        emails = self._extract_emails(response.text)
                        source_type = self._get_source_type(path)
                        for email in emails:
                            if email.lower() not in seen_emails and not self._is_blacklisted(email):
                                seen_emails.add(email.lower())
                                results.append({"email": email.lower(), "source_url": url, "source_type": source_type})
                    await asyncio.sleep(self.delay)
                except httpx.HTTPError:
                    continue
            
            try:
                response = await client.get(base_url)
                if response.status_code == 200:
                    for email in self._extract_emails(response.text):
                        if email.lower() not in seen_emails and not self._is_blacklisted(email):
                            seen_emails.add(email.lower())
                            results.append({"email": email.lower(), "source_url": base_url, "source_type": "homepage"})
            except httpx.HTTPError:
                pass
        
        return results
    
    # Patterns for obfuscated emails: [at] [dot] (at) (dot) {at} {dot} and variants
    OBFUSCATED_PATTERN = re.compile(
        r'\b([A-Za-z0-9._%+-]+)\s*'
        r'[\[\(\{]?\s*(?:at|AT|@)\s*[\]\)\}]?\s*'
        r'([A-Za-z0-9.-]+)\s*'
        r'[\[\(\{]?\s*(?:dot|DOT|\.)\s*[\]\)\}]?\s*'
        r'([A-Za-z]{2,})\b'
    )

    def _extract_emails(self, html: str) -> list[str]:
        text_emails = self.EMAIL_PATTERN.findall(html)
        soup = BeautifulSoup(html, "html.parser")
        mailto_emails = []
        for link in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
            email = link.get("href", "").replace("mailto:", "").split("?")[0].strip()
            if email:
                mailto_emails.append(email)
        
        # Extract obfuscated emails: "user [at] domain [dot] com"
        page_text = soup.get_text(separator=" ")
        obfuscated = []
        for match in self.OBFUSCATED_PATTERN.finditer(page_text):
            user, domain, tld = match.groups()
            email = f"{user.strip()}@{domain.strip()}.{tld.strip()}".lower()
            if self.EMAIL_PATTERN.match(email):  # Validate the reconstructed email
                obfuscated.append(email)
        
        return list(set(text_emails + mailto_emails + obfuscated))
    
    def _is_blacklisted(self, email: str) -> bool:
        e = email.lower()
        # Filter out file references that look like emails (e.g. sprite@2x.png)
        for ext in self.FAKE_EMAIL_EXTENSIONS:
            if e.endswith(ext):
                return True
        for pattern in self.BLACKLIST_PATTERNS:
            if re.match(pattern, e):
                return True
        return False
    
    def _get_source_type(self, path: str) -> str:
        p = path.lower()
        if "contact" in p: return "contact_page"
        if "privacy" in p: return "privacy_policy"
        if "terms" in p: return "terms_of_service"
        if "dmca" in p: return "dmca"
        if "about" in p: return "about_page"
        if "legal" in p or "imprint" in p: return "legal"
        return "other"
    
    async def scrape_single_url(self, url: str) -> list[dict[str, str]]:
        results = []
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=self.headers) as client:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    for email in self._extract_emails(response.text):
                        if not self._is_blacklisted(email):
                            results.append({"email": email.lower(), "source_url": url, "source_type": "manual"})
            except httpx.HTTPError as e:
                raise ScraperError(f"Failed to fetch URL: {str(e)}")
        return results


class ContactsGrabber:
    """Full contacts grabber: emails + socials + names + forms."""
    
    SOCIAL_PATTERNS = {
        "twitter": re.compile(r'https?://(?:www\.)?(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)', re.I),
        "linkedin": re.compile(r'https?://(?:www\.)?linkedin\.com/(?:in|company)/([A-Za-z0-9_-]+)', re.I),
        "telegram": re.compile(r'https?://(?:www\.)?t\.me/([A-Za-z0-9_]+)', re.I),
    }
    
    ROLE_KEYWORDS = {
        "editor": ["editor", "editorial"],
        "webmaster": ["webmaster", "web master", "site admin"],
        "owner": ["owner", "founder", "ceo"],
        "marketing": ["marketing", "advertising", "ads manager"],
        "content": ["content manager", "content director", "writer"],
    }
    
    CONTACT_PATHS = [
        "/contact", "/contact-us", "/contactus",
        "/about", "/about-us", "/advertise", "/advertising",
    ]
    
    def __init__(self):
        self.email_scraper = EmailScraper()
        self.headers = self.email_scraper.headers
        self.delay = self.email_scraper.delay
    
    async def grab_all(self, domain: str, use_browser: bool = False) -> dict:
        """
        Grab emails, socials, names/roles, and detect forms.
        
        Args:
            domain: Domain to scrape
            use_browser: Force Playwright browser mode. If False, will auto-fallback
                        to browser mode if static scraping finds no emails AND no forms.
        """
        base_url = f"https://{domain}"
        result = {
            "emails": [],
            "socials": {"twitter": [], "linkedin": [], "telegram": []},
            "names": [],
            "forms": [],
            "method": "static",  # Track which method was used
        }
        
        seen_emails = set()
        seen_socials = {"twitter": set(), "linkedin": set(), "telegram": set()}
        pages_html = {}
        
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=self.headers) as client:
            # Fetch all relevant pages
            urls_to_check = [base_url] + [urljoin(base_url, p) for p in self.CONTACT_PATHS]
            
            for url in urls_to_check:
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        pages_html[url] = resp.text
                    await asyncio.sleep(self.delay)
                except httpx.HTTPError:
                    continue
            
            # Process all pages
            for url, html in pages_html.items():
                soup = BeautifulSoup(html, "html.parser")
                
                # Emails
                for email in self.email_scraper._extract_emails(html):
                    if email.lower() not in seen_emails and not self.email_scraper._is_blacklisted(email):
                        seen_emails.add(email.lower())
                        source_type = self.email_scraper._get_source_type(urlparse(url).path)
                        if url == base_url:
                            source_type = "homepage"
                        result["emails"].append({
                            "email": email.lower(),
                            "source_url": url,
                            "source_type": source_type,
                        })
                
                # Socials
                for platform, pattern in self.SOCIAL_PATTERNS.items():
                    for match in pattern.finditer(html):
                        handle = match.group(1).lower()
                        full_url = match.group(0)
                        if handle not in seen_socials[platform] and handle not in ("share", "intent", "search", "hashtag"):
                            seen_socials[platform].add(handle)
                            result["socials"][platform].append(full_url)
                
                # Names/roles from about/contact pages
                if any(p in url for p in ["/about", "/contact", "/team"]):
                    self._extract_names_roles(soup, result["names"])
                
                # Form detection
                forms = self._detect_forms(soup, url)
                result["forms"].extend(forms)
        
        # Playwright fallback: if use_browser is forced OR we found nothing useful
        should_use_browser = use_browser or (len(result["emails"]) == 0 and len(result["forms"]) == 0)
        
        if should_use_browser:
            try:
                from .browser_grabber import PlaywrightGrabber
                
                browser_grabber = PlaywrightGrabber(headless=True, timeout_seconds=30)
                browser_result = await browser_grabber.grab_all(domain)
                
                # Merge results - deduplicate emails
                existing_emails = {e["email"].lower() for e in result["emails"]}
                for email_info in browser_result.get("emails", []):
                    if email_info["email"].lower() not in existing_emails:
                        result["emails"].append(email_info)
                        existing_emails.add(email_info["email"].lower())
                
                # Merge socials - deduplicate
                for platform in ["twitter", "linkedin", "telegram"]:
                    existing = set(result["socials"][platform])
                    for social_url in browser_result.get("socials", {}).get(platform, []):
                        if social_url not in existing:
                            result["socials"][platform].append(social_url)
                
                # Merge names
                result["names"].extend(browser_result.get("names", []))
                
                # Merge forms - deduplicate by action+url
                existing_forms = {(f["form_url"], f["form_action"]) for f in result["forms"]}
                for form_info in browser_result.get("forms", []):
                    key = (form_info["form_url"], form_info["form_action"])
                    if key not in existing_forms:
                        result["forms"].append(form_info)
                
                result["method"] = "browser"
                
                # Report errors if any
                if "_error" in browser_result:
                    result["_browser_error"] = browser_result["_error"]
                    
            except Exception as e:
                # If browser fails, still return static results
                result["_browser_error"] = f"Playwright fallback failed: {str(e)}"
        
        return result
    
    def _extract_names_roles(self, soup: BeautifulSoup, names_list: list):
        """Try to extract names and roles from page."""
        # Look for common patterns: h2/h3 + p, or specific classes
        for tag in soup.find_all(["h2", "h3", "h4", "strong"]):
            text = tag.get_text(strip=True)
            # Skip very long or very short text
            if len(text) < 3 or len(text) > 60:
                continue
            # Check if next sibling has a role
            next_el = tag.find_next_sibling()
            if next_el:
                next_text = next_el.get_text(strip=True).lower()
                for role, keywords in self.ROLE_KEYWORDS.items():
                    if any(kw in next_text for kw in keywords):
                        names_list.append({"name": text, "role": role})
                        break
    
    def _detect_forms(self, soup: BeautifulSoup, page_url: str) -> list[dict]:
        """Detect contact forms on the page."""
        forms = []
        page_html = str(soup)
        
        for form in soup.find_all("form"):
            action = form.get("action", "")
            method = (form.get("method", "POST") or "POST").upper()
            
            # Resolve relative action URLs
            if action and not action.startswith(("http", "//")):
                action = urljoin(page_url, action)
            elif not action:
                action = page_url
            
            # Detect CAPTCHA and extract site key
            has_captcha = False
            captcha_type = "none"
            captcha_site_key = None
            form_html = str(form)
            
            # Check for reCAPTCHA
            if any(pattern in form_html.lower() for pattern in ["g-recaptcha", "grecaptcha", "recaptcha"]):
                has_captcha = True
                # Distinguish between v2 and v3
                if "g-recaptcha" in form_html.lower() and "sitekey" in form_html.lower():
                    captcha_type = "recaptcha_v2"
                elif "grecaptcha.execute" in form_html.lower():
                    captcha_type = "recaptcha_v3"
                else:
                    captcha_type = "recaptcha_v2"  # Default to v2
                
                # Extract site key
                site_key_match = re.search(r'data-sitekey=["\']([^"\']+)["\']', form_html, re.IGNORECASE)
                if site_key_match:
                    captcha_site_key = site_key_match.group(1)
                else:
                    # Try to find in grecaptcha.execute/render calls
                    site_key_match = re.search(r'grecaptcha\.(?:execute|render)\(["\']([^"\']+)["\']', form_html)
                    if site_key_match:
                        captcha_site_key = site_key_match.group(1)
            
            # Check for hCaptcha
            elif any(pattern in form_html.lower() for pattern in ["h-captcha", "hcaptcha"]):
                has_captcha = True
                captcha_type = "hcaptcha"
                # Extract hCaptcha site key
                site_key_match = re.search(r'data-sitekey=["\']([^"\']+)["\']', form_html, re.IGNORECASE)
                if site_key_match:
                    captcha_site_key = site_key_match.group(1)
            
            # Also check in parent container or page-level scripts
            if not has_captcha:
                # Check parent div and siblings
                parent = form.parent
                if parent:
                    parent_html = str(parent)
                    if any(pattern in parent_html.lower() for pattern in ["g-recaptcha", "grecaptcha", "recaptcha"]):
                        has_captcha = True
                        if "grecaptcha.execute" in parent_html.lower():
                            captcha_type = "recaptcha_v3"
                        else:
                            captcha_type = "recaptcha_v2"
                        # Extract site key from parent
                        site_key_match = re.search(r'data-sitekey=["\']([^"\']+)["\']', parent_html, re.IGNORECASE)
                        if site_key_match:
                            captcha_site_key = site_key_match.group(1)
                    elif any(pattern in parent_html.lower() for pattern in ["h-captcha", "hcaptcha"]):
                        has_captcha = True
                        captcha_type = "hcaptcha"
                        site_key_match = re.search(r'data-sitekey=["\']([^"\']+)["\']', parent_html, re.IGNORECASE)
                        if site_key_match:
                            captcha_site_key = site_key_match.group(1)
            
            # Map fields
            fields = []
            for inp in form.find_all(["input", "textarea", "select"]):
                inp_type = inp.get("type", "text")
                inp_name = inp.get("name", "")
                if not inp_name or inp_type in ("hidden", "submit", "button", "image"):
                    continue
                
                label_text = ""
                # Try to find associated label
                inp_id = inp.get("id")
                if inp_id:
                    label = soup.find("label", attrs={"for": inp_id})
                    if label:
                        label_text = label.get_text(strip=True)
                
                if not label_text:
                    label_text = inp.get("placeholder", "") or inp_name
                
                fields.append({
                    "name": inp_name,
                    "type": inp_type if inp.name != "textarea" else "textarea",
                    "required": inp.get("required") is not None,
                    "label": label_text,
                })
            
            # Skip forms with no meaningful fields or non-contact forms
            if len(fields) < 2:
                continue
            field_names = " ".join(f["name"].lower() for f in fields)
            field_labels = " ".join(f.get("label", "").lower() for f in fields)
            all_text = f"{field_names} {field_labels}"
            
            # Skip search forms
            if "search" in field_names or any(f["type"] == "search" for f in fields) or "phrase" in field_names:
                continue
            # Skip AJAX search plugins (e.g. Ajax Search Lite)
            if "asl_" in field_names or "customset" in field_names:
                continue
            # Skip login/register forms
            if "password" in field_names and "message" not in field_names:
                continue
            # Must have at least one contact-like field (email, message, name, subject)
            contact_indicators = ["email", "mail", "message", "body", "comment", "inquiry", "subject", "textarea"]
            has_contact_field = any(ind in all_text for ind in contact_indicators) or any(f["type"] == "textarea" for f in fields)
            if not has_contact_field:
                continue
            
            forms.append({
                "form_url": page_url,
                "form_action": action,
                "form_method": method,
                "fields": fields,
                "has_captcha": has_captcha,
                "captcha_type": captcha_type,
                "captcha_site_key": captcha_site_key,
            })
        
        return forms
    
    async def submit_form(self, form_action: str, form_method: str, fields_json: list, 
                          template_body: str, template_subject: str, domain: str,
                          sender_name: str = "Tony", sender_email: Optional[str] = None) -> dict:
        """Submit a contact form with template data."""
        sender_email = sender_email or settings.email_account
        subject = template_subject.replace("$domain", domain)
        body = template_body.replace("$domain", domain)
        
        # Build form data by mapping fields
        form_data = {}
        for field in fields_json:
            name = field["name"].lower()
            label = field.get("label", "").lower()
            combined = f"{name} {label}"
            
            if any(k in combined for k in ["email", "e-mail", "mail"]):
                form_data[field["name"]] = sender_email
            elif any(k in combined for k in ["name", "your name", "full name", "author"]):
                form_data[field["name"]] = sender_name
            elif any(k in combined for k in ["subject", "topic", "regarding"]):
                form_data[field["name"]] = subject
            elif any(k in combined for k in ["message", "body", "content", "comment", "text", "inquiry", "details"]):
                form_data[field["name"]] = body
            elif field["type"] == "textarea":
                form_data[field["name"]] = body
            elif any(k in combined for k in ["url", "website", "site"]):
                form_data[field["name"]] = f"https://{domain}"
            elif any(k in combined for k in ["phone", "tel"]):
                form_data[field["name"]] = ""
            else:
                form_data[field["name"]] = ""
        
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=self.headers) as client:
            try:
                if form_method.upper() == "GET":
                    resp = await client.get(form_action, params=form_data)
                else:
                    # Try form-data first
                    resp = await client.post(form_action, data=form_data)
                
                return {
                    "success": resp.status_code < 400,
                    "status_code": resp.status_code,
                    "form_data_sent": form_data,
                }
            except httpx.HTTPError as e:
                return {"success": False, "error": str(e), "form_data_sent": form_data}
