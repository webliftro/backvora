"""
Playwright-based contact grabber for JavaScript-rendered content and modal forms.
"""

import re
import asyncio
from typing import Optional
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup


class PlaywrightGrabber:
    """Browser-based grabber using Playwright for JS-rendered content and modals."""
    
    CONTACT_KEYWORDS = [
        "contact", "feedback", "advertise", "advertising", "write us",
        "get in touch", "reach out", "support", "help", "inquiries"
    ]
    
    CONTACT_PATHS = [
        "/contact", "/contact-us", "/contactus",
        "/about", "/about-us",
        "/advertise", "/advertising",
        "/feedback",
    ]
    
    def __init__(self, headless: bool = True, timeout_seconds: int = 30):
        self.headless = headless
        self.timeout = timeout_seconds * 1000  # Convert to ms
        self.browser_path = "/home/slither/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome"
        
    async def grab_all(self, domain: str) -> dict:
        """
        Grab contacts using Playwright browser automation.
        Returns data in the same format as ContactsGrabber.grab_all()
        """
        base_url = f"https://{domain}"
        result = {
            "emails": [],
            "socials": {"twitter": [], "linkedin": [], "telegram": []},
            "names": [],
            "forms": [],
        }
        
        seen_emails = set()
        seen_socials = {"twitter": set(), "linkedin": set(), "telegram": set()}
        
        async with async_playwright() as p:
            try:
                # Launch browser with real user agent
                browser = await p.chromium.launch(
                    headless=self.headless,
                    executable_path=self.browser_path,
                    args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage']
                )
                
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={'width': 1920, 'height': 1080},
                )
                
                page = await context.new_page()
                page.set_default_timeout(self.timeout)
                
                # Try homepage first
                try:
                    await page.goto(base_url, wait_until="domcontentloaded", timeout=self.timeout)
                    await asyncio.sleep(1)  # Wait for JS to render
                    
                    # Extract from homepage
                    await self._extract_from_page(page, base_url, result, seen_emails, seen_socials)
                    
                    # Click contact-like links to trigger modals (only on homepage, with timeout)
                    try:
                        await asyncio.wait_for(
                            self._click_contact_links(page, result, seen_emails),
                            timeout=10
                        )
                    except asyncio.TimeoutError:
                        pass
                    
                except PlaywrightTimeoutError:
                    pass
                except Exception as e:
                    # Check for Cloudflare challenge
                    if "cloudflare" in str(e).lower() or await self._is_cloudflare_challenge(page):
                        result["_error"] = "Cloudflare challenge detected"
                
                # Try contact pages (extract only, no clicking)
                for path in self.CONTACT_PATHS:
                    url = urljoin(base_url, path)
                    try:
                        response = await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                        if response and response.status == 200:
                            await asyncio.sleep(0.5)
                            await self._extract_from_page(page, url, result, seen_emails, seen_socials)
                    except:
                        continue
                
                await browser.close()
                
            except Exception as e:
                result["_error"] = str(e)
        
        return result
    
    async def _is_cloudflare_challenge(self, page) -> bool:
        """Check if page shows Cloudflare challenge."""
        try:
            content = await page.content()
            return any(indicator in content.lower() for indicator in [
                "cloudflare", "checking your browser", "ddos protection",
                "just a moment", "ray id"
            ])
        except:
            return False
    
    async def _extract_from_page(self, page, url: str, result: dict, seen_emails: set, seen_socials: dict):
        """Extract emails, socials, and forms from current page."""
        try:
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # Import patterns from parent
            from .scraper import EmailScraper, ContactsGrabber
            
            email_scraper = EmailScraper()
            grabber = ContactsGrabber()
            
            # Extract emails
            emails = email_scraper._extract_emails(html)
            for email in emails:
                if email.lower() not in seen_emails and not email_scraper._is_blacklisted(email):
                    seen_emails.add(email.lower())
                    source_type = email_scraper._get_source_type(urlparse(url).path)
                    if url.endswith(urlparse(url).netloc) or url == f"https://{urlparse(url).netloc}":
                        source_type = "homepage"
                    result["emails"].append({
                        "email": email.lower(),
                        "source_url": url,
                        "source_type": source_type,
                    })
            
            # Extract socials
            for platform, pattern in grabber.SOCIAL_PATTERNS.items():
                for match in pattern.finditer(html):
                    handle = match.group(1).lower()
                    full_url = match.group(0)
                    if handle not in seen_socials[platform] and handle not in ("share", "intent", "search", "hashtag"):
                        seen_socials[platform].add(handle)
                        result["socials"][platform].append(full_url)
            
            # Extract names/roles
            if any(p in url for p in ["/about", "/contact", "/team"]):
                grabber._extract_names_roles(soup, result["names"])
            
            # Detect forms
            forms = grabber._detect_forms(soup, url)
            result["forms"].extend(forms)
            
        except Exception:
            pass
    
    async def _click_contact_links(self, page, result: dict, seen_emails: set):
        """
        Find contact/feedback links and extract their modal/ajax content.
        Handles: data-fancybox="ajax", data-href, hidden modals, JS-triggered popups.
        """
        from .scraper import EmailScraper, ContactsGrabber
        scraper = EmailScraper()
        grabber = ContactsGrabber()
        current_url = page.url
        
        try:
            # Strategy 1: Find AJAX modal links (data-href, data-fancybox="ajax", etc.)
            ajax_links = await page.evaluate("""() => {
                const results = [];
                const els = document.querySelectorAll('a[data-href], a[data-fancybox="ajax"], [data-modal-url], [data-ajax-url]');
                for (const el of els) {
                    const text = el.textContent.trim().toLowerCase();
                    const url = el.getAttribute('data-href') || el.getAttribute('data-modal-url') || el.getAttribute('data-ajax-url') || '';
                    if (url) results.push({ text, url });
                }
                return results;
            }""")
            
            for link in ajax_links:
                if not any(kw in link["text"] for kw in self.CONTACT_KEYWORDS):
                    continue
                # Fetch the AJAX content directly
                try:
                    ajax_html = await page.evaluate(f"() => fetch('{link['url']}').then(r => r.text()).catch(() => '')")
                    if ajax_html and ('email' in ajax_html.lower() or 'message' in ajax_html.lower() or 'textarea' in ajax_html.lower()):
                        soup = BeautifulSoup(ajax_html, "html.parser")
                        forms = grabber._detect_forms(soup, current_url + link["url"])
                        
                        # Also detect form-like containers without <form> tag
                        if not forms:
                            # Try to find real submit endpoint from page JS
                            js_endpoint = await self._find_js_submit_endpoint(page, link["text"])
                            forms = self._detect_formless_inputs(soup, current_url, link["url"], js_endpoint)
                        
                        for form in forms:
                            form["form_url"] = current_url  # Source page
                            form["notes"] = f"AJAX modal from {link['url']}"
                        result["forms"].extend(forms)
                        
                        # Extract emails from ajax content
                        for email in scraper._extract_emails(ajax_html):
                            if email.lower() not in seen_emails and not scraper._is_blacklisted(email):
                                seen_emails.add(email.lower())
                                result["emails"].append({
                                    "email": email.lower(),
                                    "source_url": current_url,
                                    "source_type": "modal",
                                })
                except Exception:
                    continue
            
            # Strategy 2: Force-click visible contact buttons/links that are modal triggers
            contact_els = await page.evaluate("""() => {
                const results = [];
                const els = document.querySelectorAll('a, button, [role="button"]');
                for (const el of els) {
                    const text = el.textContent.trim().toLowerCase();
                    if (text.length < 3 || text.length > 30) continue;
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) continue;
                    const href = el.getAttribute('href') || '';
                    const isModal = !href || href === '#' || href.startsWith('javascript:') || 
                                    el.hasAttribute('data-toggle') || el.hasAttribute('data-modal') ||
                                    el.hasAttribute('data-popup') || el.classList.toString().includes('modal');
                    if (isModal) results.push({ text, index: results.length });
                }
                return results;
            }""")
            
            clicked = 0
            for info in contact_els:
                if clicked >= 2:
                    break
                if not any(kw in info["text"] for kw in self.CONTACT_KEYWORDS):
                    continue
                try:
                    # Use force click via JS to bypass visibility issues
                    await page.evaluate(f"""() => {{
                        const els = document.querySelectorAll('a, button, [role="button"]');
                        let idx = 0;
                        for (const el of els) {{
                            const text = el.textContent.trim().toLowerCase();
                            if (text.length < 3 || text.length > 30) continue;
                            const rect = el.getBoundingClientRect();
                            if (rect.width === 0 || rect.height === 0) continue;
                            const href = el.getAttribute('href') || '';
                            const isModal = !href || href === '#' || href.startsWith('javascript:') || 
                                            el.hasAttribute('data-toggle') || el.hasAttribute('data-modal') ||
                                            el.hasAttribute('data-popup') || el.classList.toString().includes('modal');
                            if (isModal && idx === {info['index']}) {{ el.click(); return; }}
                            if (isModal) idx++;
                        }}
                    }}""")
                    await asyncio.sleep(1.5)
                    clicked += 1
                    
                    if page.url != current_url:
                        await page.go_back(timeout=5000)
                        await asyncio.sleep(0.5)
                        continue
                    
                    await self._extract_modal_forms(page, result)
                    
                    html = await page.content()
                    for email in scraper._extract_emails(html):
                        if email.lower() not in seen_emails and not scraper._is_blacklisted(email):
                            seen_emails.add(email.lower())
                            result["emails"].append({
                                "email": email.lower(),
                                "source_url": current_url,
                                "source_type": "modal",
                            })
                    
                    await page.keyboard.press('Escape')
                    await asyncio.sleep(0.3)
                except Exception:
                    continue
                    
        except Exception:
            pass
    
    async def _find_js_submit_endpoint(self, page, link_text: str) -> str | None:
        """Search page JS for the real POST endpoint associated with a form submit function."""
        try:
            endpoint = await page.evaluate("""() => {
                // Strategy 1: Check known submit function names
                const funcNames = ['send_feedback', 'sendFeedback', 'submitContact', 'sendContact', 'submitForm', 'send_message', 'sendMessage'];
                for (const fn of funcNames) {
                    if (typeof window[fn] === 'function') {
                        const src = window[fn].toString();
                        // Extract POST URLs from function source
                        const matches = [...src.matchAll(/(?:post|fetch|ajax)\\s*\\(\\s*['"]([^'"]+)['"]/gi)];
                        for (const m of matches) {
                            if (m[1].startsWith('/')) return m[1];
                        }
                    }
                }
                // Strategy 2: Search inline scripts
                const scripts = document.querySelectorAll('script');
                const candidates = [];
                for (const s of scripts) {
                    const text = s.textContent;
                    if (!text.includes('contact') && !text.includes('feedback') && !text.includes('send')) continue;
                    const matches = [...text.matchAll(/(?:post|fetch|ajax)\\s*\\(\\s*['"]([^'"]+)['"]/gi)];
                    for (const m of matches) {
                        if (m[1].startsWith('/')) candidates.push(m[1]);
                    }
                }
                if (!candidates.length) return null;
                return candidates.find(u => u.includes('.php') || u.includes('/api') || u.includes('submit') || u.includes('include')) || candidates[0];
            }""")
            return endpoint
        except Exception:
            return None
    
    def _detect_formless_inputs(self, soup: BeautifulSoup, page_url: str, ajax_path: str, js_endpoint: str | None = None) -> list:
        """Detect form-like input groups that aren't wrapped in <form> tags."""
        inputs = soup.find_all(["input", "textarea"])
        meaningful = [i for i in inputs if i.get("name") and i.get("type", "text") not in ("hidden", "submit", "button")]
        
        if len(meaningful) < 2:
            return []
        
        # Use JS-discovered endpoint, or build from page URL
        if js_endpoint:
            base = page_url.split('/', 3)[:3]  # https://domain.com
            form_action = '/'.join(base) + js_endpoint
        else:
            form_action = page_url.rstrip("/") + ajax_path
        
        # The JS might use different field names than the HTML inputs
        # Map HTML input names to the JS POST params by looking at the submit function
        fields = []
        for inp in meaningful:
            name = inp.get("name", "")
            inp_type = inp.get("type", "text") if inp.name != "textarea" else "textarea"
            label = inp.get("placeholder", "") or name
            fields.append({
                "name": name,
                "type": inp_type,
                "required": inp.get("required") is not None,
                "label": label,
            })
        
        return [{
            "form_url": page_url,
            "form_action": form_action,
            "form_method": "POST",
            "fields": fields,
            "has_captcha": False,
            "captcha_type": "none",
            "captcha_site_key": None,
        }]
    
    async def _extract_modal_forms(self, page, result: dict):
        """Extract forms from modals/popups that just appeared."""
        try:
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            from .scraper import ContactsGrabber
            grabber = ContactsGrabber()
            
            # Look for forms in common modal containers
            modal_selectors = [
                '[class*="modal"]', '[class*="popup"]', '[class*="fancybox"]',
                '[class*="overlay"]', '[class*="dialog"]', '[id*="modal"]',
                '[id*="popup"]', '[role="dialog"]'
            ]
            
            for selector in modal_selectors:
                modals = soup.select(selector)
                for modal in modals:
                    # Check if modal contains a form
                    forms = modal.find_all("form")
                    for form_element in forms:
                        # Convert back to full soup for detection
                        temp_soup = BeautifulSoup(str(modal), "html.parser")
                        detected_forms = grabber._detect_forms(temp_soup, await page.url)
                        
                        # Add forms if not already detected
                        for form_info in detected_forms:
                            # Check if form already in results
                            is_duplicate = any(
                                f["form_action"] == form_info["form_action"] and
                                f["form_url"] == form_info["form_url"]
                                for f in result["forms"]
                            )
                            if not is_duplicate:
                                result["forms"].append(form_info)
        
        except Exception:
            pass
