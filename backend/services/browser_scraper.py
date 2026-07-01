"""
Browser-based form submission using Selenium.
Handles CAPTCHA-protected forms by integrating with CaptchaSolver.
"""

import json
import re
import time
from datetime import datetime
from typing import Optional, Dict, List
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

from .captcha_solver import CaptchaSolver, CaptchaSolverError
from .agent_browser import AgentBrowser, AgentBrowserError


class BrowserFormSubmitterError(Exception):
    """Raised when browser form submission fails."""
    pass


class BrowserFormSubmitter:
    """
    Browser-based form submitter with CAPTCHA solving support.
    Uses Selenium WebDriver with headless Chrome.
    """
    
    def __init__(self, headless: bool = True, page_load_timeout: int = 30):
        """
        Initialize the browser form submitter.
        
        Args:
            headless: Run Chrome in headless mode
            page_load_timeout: Maximum time to wait for page loads (seconds)
        """
        self.headless = headless
        self.page_load_timeout = page_load_timeout
        self.driver: Optional[webdriver.Chrome] = None
    
    def _create_driver(self) -> webdriver.Chrome:
        """Create and configure Chrome WebDriver."""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless=new")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # User agent to appear more legitimate
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Prevent detection
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        try:
            # Try using webdriver-manager to handle chromedriver
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception:
            # Fallback: assume chromedriver is in PATH or use system Chrome
            driver = webdriver.Chrome(options=chrome_options)
        
        driver.set_page_load_timeout(self.page_load_timeout)
        
        # Execute CDP commands to prevent detection
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """
        })
        
        return driver
    
    def _extract_site_key(self, driver: webdriver.Chrome, captcha_type: str) -> Optional[str]:
        """
        Extract reCAPTCHA or hCaptcha site key from the page.
        
        Args:
            driver: Selenium WebDriver instance
            captcha_type: Type of CAPTCHA (recaptcha_v2, recaptcha_v3, hcaptcha)
            
        Returns:
            The site key if found, None otherwise
        """
        page_source = driver.page_source
        
        if "recaptcha" in captcha_type:
            # Look for data-sitekey attribute
            match = re.search(r'data-sitekey=["\']([^"\']+)["\']', page_source, re.IGNORECASE)
            if match:
                return match.group(1)
            
            # Look for grecaptcha.execute or render calls
            match = re.search(r'grecaptcha\.(?:execute|render)\(["\']([^"\']+)["\']', page_source)
            if match:
                return match.group(1)
            
            # Try to find in script src
            match = re.search(r'https://www\.google\.com/recaptcha/api\.js\?.*render=([^&"\']+)', page_source)
            if match:
                return match.group(1)
        
        elif captcha_type == "hcaptcha":
            # Look for hCaptcha data-sitekey
            match = re.search(r'data-sitekey=["\']([^"\']+)["\']', page_source, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _inject_captcha_token(self, driver: webdriver.Chrome, token: str, captcha_type: str):
        """
        Inject solved CAPTCHA token into the page.
        
        Args:
            driver: Selenium WebDriver instance
            token: Solved CAPTCHA token
            captcha_type: Type of CAPTCHA
        """
        if "recaptcha" in captcha_type:
            # Inject token into all g-recaptcha-response textareas
            script = """
                var token = arguments[0];
                
                // Set all g-recaptcha-response elements
                document.querySelectorAll('[id^="g-recaptcha-response"]').forEach(function(el) {
                    el.style.display = 'block';
                    el.innerHTML = token;
                    el.value = token;
                });
                
                // Also try textarea with name
                document.querySelectorAll('textarea[name="g-recaptcha-response"]').forEach(function(el) {
                    el.style.display = 'block';
                    el.innerHTML = token;
                    el.value = token;
                });
                
                // Try to trigger callback
                if (typeof ___grecaptcha_cfg !== 'undefined') {
                    var clients = ___grecaptcha_cfg.clients;
                    for (var key in clients) {
                        var client = clients[key];
                        var walkObject = function(obj, depth) {
                            if (depth > 5 || !obj) return;
                            for (var k in obj) {
                                try {
                                    if (typeof obj[k] === 'function' && k.toLowerCase().includes('callback')) {
                                        obj[k](token);
                                    }
                                    if (typeof obj[k] === 'object' && obj[k] !== null) {
                                        walkObject(obj[k], depth + 1);
                                    }
                                } catch(e) {}
                            }
                        };
                        walkObject(client, 0);
                    }
                }
            """
            driver.execute_script(script, token)
        
        elif captcha_type == "hcaptcha":
            # Inject token for hCaptcha
            script = """
                var token = arguments[0];
                document.querySelectorAll('[name="h-captcha-response"]').forEach(function(el) {
                    el.innerHTML = token;
                    el.value = token;
                });
                document.querySelectorAll('textarea[name="g-recaptcha-response"]').forEach(function(el) {
                    el.innerHTML = token;
                    el.value = token;
                });
            """
            driver.execute_script(script, token)
    
    def _fill_form_field(self, driver: webdriver.Chrome, field: Dict, value: str):
        """
        Fill a form field with the given value.
        
        Args:
            driver: Selenium WebDriver instance
            field: Field info dict with 'name' and 'type'
            value: Value to fill
        """
        field_name = field["name"]
        field_type = field.get("type", "text")
        
        try:
            # Try by name first
            element = driver.find_element(By.NAME, field_name)
        except NoSuchElementException:
            # Try by ID
            try:
                element = driver.find_element(By.ID, field_name)
            except NoSuchElementException:
                # Skip this field
                return
        
        # Clear and fill
        try:
            element.clear()
            element.send_keys(value)
        except WebDriverException:
            # Field might not be clearable/fillable
            pass
    
    async def submit_form_with_captcha(
        self,
        form_url: str,
        form_data: Dict[str, str],
        fields: List[Dict],
        captcha_site_key: Optional[str] = None,
        captcha_type: str = "recaptcha_v2",
        form_action: Optional[str] = None,
    ) -> Dict:
        """
        Submit a form with CAPTCHA protection using browser automation.
        
        Args:
            form_url: URL of the page containing the form
            form_data: Data to fill into the form (field_name -> value)
            fields: List of field definitions from ContactForm
            captcha_site_key: reCAPTCHA/hCaptcha site key (auto-detected if None)
            captcha_type: Type of CAPTCHA (recaptcha_v2, recaptcha_v3, hcaptcha, none)
            form_action: Form action URL (optional, for validation)
            
        Returns:
            Dict with success status and details
        """
        try:
            # Create driver
            self.driver = self._create_driver()
            
            # Navigate to form page
            self.driver.get(form_url)
            time.sleep(2)  # Wait for page to load
            
            # Extract site key if not provided
            if captcha_type != "none" and not captcha_site_key:
                captcha_site_key = self._extract_site_key(self.driver, captcha_type)
                if not captcha_site_key:
                    # No CAPTCHA found, proceed without solving
                    captcha_type = "none"
            
            # Solve CAPTCHA if needed
            captcha_token = None
            if captcha_type != "none" and captcha_site_key:
                try:
                    solver = CaptchaSolver(timeout=60)
                    captcha_token = await solver.solve(
                        site_key=captcha_site_key,
                        page_url=form_url,
                        captcha_type=captcha_type
                    )
                except CaptchaSolverError as e:
                    raise BrowserFormSubmitterError(f"CAPTCHA solving failed: {str(e)}")
            
            # Fill form fields
            for field in fields:
                field_name = field["name"]
                if field_name in form_data:
                    value = form_data[field_name]
                    if value:  # Only fill non-empty values
                        self._fill_form_field(self.driver, field, value)
            
            time.sleep(1)  # Brief pause before CAPTCHA injection
            
            # Inject CAPTCHA token if solved
            if captcha_token:
                self._inject_captcha_token(self.driver, captcha_token, captcha_type)
                time.sleep(1)  # Wait for token injection to take effect
            
            # Find and submit the form
            try:
                # Try to find submit button
                submit_button = None
                try:
                    submit_button = self.driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
                except NoSuchElementException:
                    try:
                        submit_button = self.driver.find_element(By.CSS_SELECTOR, 'input[type="submit"]')
                    except NoSuchElementException:
                        # Try generic submit button
                        submit_button = self.driver.find_element(By.XPATH, '//button[contains(text(), "Submit") or contains(text(), "Send")]')
                
                if submit_button:
                    submit_button.click()
                else:
                    # Last resort: submit the first form on the page
                    form_element = self.driver.find_element(By.TAG_NAME, "form")
                    form_element.submit()
                
                # Wait for submission to complete (check for URL change or success message)
                time.sleep(3)
                
                final_url = self.driver.current_url
                page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                
                # Check for success indicators
                success_indicators = ["thank", "success", "submitted", "received", "sent", "message sent"]
                error_indicators = ["error", "failed", "invalid", "required"]
                
                has_success = any(indicator in page_text for indicator in success_indicators)
                has_error = any(indicator in page_text for indicator in error_indicators)
                
                # Success if we see success messages or URL changed away from form
                if has_success or (final_url != form_url and not has_error):
                    return {
                        "success": True,
                        "final_url": final_url,
                        "captcha_solved": captcha_token is not None,
                        "message": "Form submitted successfully"
                    }
                else:
                    return {
                        "success": False,
                        "final_url": final_url,
                        "captcha_solved": captcha_token is not None,
                        "error": "Form submission may have failed (no clear success indicator)",
                        "page_excerpt": page_text[:500]
                    }
                
            except NoSuchElementException as e:
                raise BrowserFormSubmitterError(f"Could not find form or submit button: {str(e)}")
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "captcha_solved": captcha_token is not None if 'captcha_token' in locals() else False
            }
        
        finally:
            # Always close the driver
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
    
    def __del__(self):
        """Cleanup: ensure driver is closed."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass


class AgentBrowserFormSubmitter:
    """
    Agent-browser based form submitter with smart field discovery.
    
    Uses agent-browser CLI for headless browser automation:
    - Discovers form fields via snapshot
    - Smart field matching (name/email/subject/message)
    - Handles CAPTCHAs via 2Captcha integration
    - Falls back to Selenium on failure
    """
    
    def __init__(self, timeout: int = 45):
        """
        Initialize agent-browser form submitter.
        
        Args:
            timeout: Maximum time for form submission (seconds)
        """
        self.timeout = timeout
    
    def _match_field(
        self,
        element_text: str,
        field_name: str,
        field_type: str = "text",
    ) -> bool:
        """
        Check if an element matches a form field we want to fill.
        
        Args:
            element_text: Element description from snapshot (role + name)
            field_name: Field we're looking for (name/email/subject/message)
            field_type: Expected field type
            
        Returns:
            True if this element likely matches the field
        """
        text_lower = element_text.lower()
        
        # Common patterns for each field type
        patterns = {
            "name": ["name", "your name", "full name", "contact name"],
            "email": ["email", "e-mail", "your email", "contact email"],
            "subject": ["subject", "topic", "regarding"],
            "message": ["message", "comment", "your message", "description", "inquiry", "details"],
            "phone": ["phone", "telephone", "mobile"],
            "website": ["website", "site", "url"],
        }
        
        # Check if any pattern matches
        if field_name in patterns:
            for pattern in patterns[field_name]:
                if pattern in text_lower:
                    # Also check type hint if available
                    if field_type == "textarea" and "textbox" in text_lower:
                        return True
                    if field_type in ("text", "email") and "textbox" in text_lower:
                        return True
                    if "textbox" in text_lower or "input" in text_lower:
                        return True
        
        return False
    
    async def submit_form_with_captcha(
        self,
        form_url: str,
        form_data: Dict[str, str],
        fields: List[Dict],
        captcha_site_key: Optional[str] = None,
        captcha_type: str = "recaptcha_v2",
        form_action: Optional[str] = None,
    ) -> Dict:
        """
        Submit form using agent-browser with CAPTCHA support.
        
        Args:
            form_url: URL of the page containing the form
            form_data: Data to fill (field_name -> value)
            fields: Field definitions from ContactForm
            captcha_site_key: CAPTCHA site key (auto-detected if None)
            captcha_type: Type of CAPTCHA (recaptcha_v2, recaptcha_v3, hcaptcha, none)
            form_action: Form action URL (optional)
            
        Returns:
            Dict with success status and details
        """
        session_id = f"form-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        try:
            async with AgentBrowser(session=session_id, timeout=self.timeout) as browser:
                # Navigate to form page
                try:
                    await browser.open(form_url, wait_load=True)
                    await browser.wait(milliseconds=2000)  # Wait for dynamic content
                except AgentBrowserError as e:
                    raise BrowserFormSubmitterError(f"Failed to load form page: {str(e)}")
                
                # Detect CAPTCHA if needed
                captcha_token = None
                if captcha_type != "none":
                    # Try to extract site key from page if not provided
                    if not captcha_site_key:
                        try:
                            page_html = await browser.get_text("body")
                            # Simple regex patterns for site key detection
                            if "recaptcha" in captcha_type:
                                match = re.search(r'data-sitekey=["\']([^"\']+)["\']', page_html, re.IGNORECASE)
                                if match:
                                    captcha_site_key = match.group(1)
                            elif captcha_type == "hcaptcha":
                                match = re.search(r'data-sitekey=["\']([^"\']+)["\']', page_html, re.IGNORECASE)
                                if match:
                                    captcha_site_key = match.group(1)
                        except Exception:
                            pass  # Site key detection is best-effort
                    
                    # Solve CAPTCHA
                    if captcha_site_key:
                        try:
                            solver = CaptchaSolver(timeout=60)
                            captcha_token = await solver.solve(
                                site_key=captcha_site_key,
                                page_url=form_url,
                                captcha_type=captcha_type,
                            )
                        except CaptchaSolverError as e:
                            # Non-fatal: try submitting without CAPTCHA
                            pass
                
                # Take snapshot to discover form fields
                try:
                    snapshot = await browser.snapshot(interactive=True, json_output=True)
                except Exception as e:
                    raise BrowserFormSubmitterError(f"Failed to snapshot form: {str(e)}")
                
                # Parse snapshot to find form fields
                # snapshot['text'] contains the accessibility tree with refs
                snapshot_text = snapshot.get("text", "")
                
                # Build mapping of field_name -> ref
                field_mapping = {}
                
                # Parse snapshot lines looking for interactive elements
                # Format: @e1 textbox "Email" (or similar)
                ref_pattern = re.compile(r'(@e\d+)\s+(\w+)\s+"?([^"]+)"?')
                
                for line in snapshot_text.split('\n'):
                    match = ref_pattern.search(line)
                    if match:
                        ref = match.group(1)
                        element_type = match.group(2)
                        element_label = match.group(3)
                        element_desc = f"{element_type} {element_label}"
                        
                        # Try to match to our fields
                        for field in fields:
                            field_name = field["name"]
                            field_type = field.get("type", "text")
                            
                            if field_name not in field_mapping:
                                if self._match_field(element_desc, field_name, field_type):
                                    field_mapping[field_name] = ref
                
                # Fill form fields
                filled_count = 0
                for field in fields:
                    field_name = field["name"]
                    if field_name in form_data and field_name in field_mapping:
                        value = form_data[field_name]
                        if value:  # Only fill non-empty values
                            ref = field_mapping[field_name]
                            try:
                                await browser.fill(ref, value)
                                filled_count += 1
                            except Exception as e:
                                # Continue even if one field fails
                                pass
                
                if filled_count == 0:
                    raise BrowserFormSubmitterError("Could not fill any form fields (field detection failed)")
                
                # Inject CAPTCHA token if solved
                if captcha_token:
                    try:
                        inject_script = f"""
                        (function() {{
                            var token = {json.dumps(captcha_token)};
                            document.querySelectorAll('[id^="g-recaptcha-response"], textarea[name="g-recaptcha-response"], [name="h-captcha-response"]').forEach(function(el) {{
                                el.style.display = 'block';
                                el.innerHTML = token;
                                el.value = token;
                            }});
                            
                            // Try to trigger callback
                            if (typeof ___grecaptcha_cfg !== 'undefined') {{
                                var clients = ___grecaptcha_cfg.clients;
                                for (var key in clients) {{
                                    var client = clients[key];
                                    if (client && typeof client.callback === 'function') {{
                                        client.callback(token);
                                    }}
                                }}
                            }}
                        }})();
                        """
                        await browser.eval_js(inject_script)
                        await browser.wait(milliseconds=1000)
                    except Exception:
                        pass  # Best effort
                
                # Find and click submit button
                try:
                    # Try common submit button texts
                    submit_texts = ["submit", "send", "send message", "send inquiry", "contact us"]
                    submitted = False
                    
                    for text in submit_texts:
                        try:
                            await browser.find_and_click(text)
                            submitted = True
                            break
                        except Exception:
                            continue
                    
                    if not submitted:
                        # Last resort: look for button in snapshot
                        button_pattern = re.compile(r'(@e\d+)\s+button\s+"?([^"]+)"?', re.IGNORECASE)
                        for line in snapshot_text.split('\n'):
                            match = button_pattern.search(line)
                            if match:
                                ref = match.group(1)
                                button_text = match.group(2).lower()
                                if any(kw in button_text for kw in ["submit", "send", "contact"]):
                                    try:
                                        await browser.click(ref)
                                        submitted = True
                                        break
                                    except Exception:
                                        continue
                    
                    if not submitted:
                        raise BrowserFormSubmitterError("Could not find submit button")
                    
                except Exception as e:
                    raise BrowserFormSubmitterError(f"Failed to submit form: {str(e)}")
                
                # Wait for submission
                await browser.wait(milliseconds=3000)
                
                # Check result
                try:
                    final_url = await browser.get_url()
                    page_text = await browser.get_text("body")
                    page_text_lower = page_text.lower()
                    
                    # Success indicators
                    success_indicators = ["thank", "success", "submitted", "received", "sent", "message sent"]
                    error_indicators = ["error", "failed", "invalid", "required"]
                    
                    has_success = any(ind in page_text_lower for ind in success_indicators)
                    has_error = any(ind in page_text_lower for ind in error_indicators)
                    
                    if has_success or (final_url != form_url and not has_error):
                        return {
                            "success": True,
                            "final_url": final_url,
                            "captcha_solved": captcha_token is not None,
                            "message": "Form submitted successfully via agent-browser",
                            "fields_filled": filled_count,
                        }
                    else:
                        return {
                            "success": False,
                            "final_url": final_url,
                            "captcha_solved": captcha_token is not None,
                            "error": "Form submission may have failed (no clear success indicator)",
                            "page_excerpt": page_text[:500],
                            "fields_filled": filled_count,
                        }
                
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Failed to verify submission result: {str(e)}",
                        "captcha_solved": captcha_token is not None,
                        "fields_filled": filled_count,
                    }
        
        except BrowserFormSubmitterError as e:
            return {
                "success": False,
                "error": str(e),
                "captcha_solved": captcha_token is not None if 'captcha_token' in locals() else False,
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "captcha_solved": captcha_token is not None if 'captcha_token' in locals() else False,
            }
