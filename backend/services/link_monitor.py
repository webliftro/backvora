"""
Link Monitor Service - Comprehensive verification of published guest posts.

Checks: HTTP status, domain match, anchor texts, target URLs, dofollow,
images, content completeness. Also provides monthly health checks.
"""

import httpx
import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from ..models import Order, Domain, OrderLink, LinkCheck
from .agent_browser import AgentBrowser, AgentBrowserError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_domain(url: str) -> str:
    """Extract bare domain from URL (no www, no path)."""
    m = re.search(r'https?://(?:www\.)?([^/]+)', url)
    return m.group(1).lower() if m else ""


def _normalize_url(url: str) -> str:
    """
    Normalize URL for comparison.
    - Lowercase
    - Strip trailing slash
    - Remove protocol differences (treat http/https same)
    - Remove www prefix
    """
    if not url:
        return ""
    url = url.lower().strip()
    # Remove protocol
    url = re.sub(r'^https?://', '', url)
    # Remove www
    url = re.sub(r'^www\.', '', url)
    # Strip trailing slash
    url = url.rstrip('/')
    return url


def _urls_match(url1: str, url2: str) -> bool:
    """
    Check if two URLs match, handling protocol/www/trailing slash variations.
    """
    norm1 = _normalize_url(url1)
    norm2 = _normalize_url(url2)
    if not norm1 or not norm2:
        return False
    # Exact match
    if norm1 == norm2:
        return True
    # One is a prefix of the other (for path matching)
    # But require at least domain level match (has a dot or is reasonably long)
    if '.' in norm1[:30] or '.' in norm2[:30]:  # Has domain component
        return norm1 in norm2 or norm2 in norm1
    return False


def _normalize_anchor(text: str) -> str:
    """Normalize anchor text for comparison: lowercase, collapse whitespace,
    normalize smart quotes/dashes/special chars to their ASCII equivalents."""
    t = " ".join(text.split()).lower()
    # Smart quotes → straight quotes
    t = t.replace("\u2018", "'").replace("\u2019", "'")  # ' '
    t = t.replace("\u201c", '"').replace("\u201d", '"')  # " "
    # Dashes
    t = t.replace("\u2013", "-").replace("\u2014", "-")  # – —
    # Non-breaking space
    t = t.replace("\u00a0", " ")
    # Ellipsis
    t = t.replace("\u2026", "...")
    return t


def _word_count(text: str) -> int:
    return len(text.split())


def _is_cloudflare_challenge(html: str, status_code: int) -> bool:
    """
    Detect Cloudflare bot-protection challenges that block regular HTTP clients.
    Indicators: 403/503 status, or 200 with JS challenge page.
    """
    if status_code in (403, 503):
        html_lower = html.lower()
        cf_markers = [
            "just a moment",
            "checking your browser",
            "cf-ray",
            "cloudflare",
            "enable javascript",
            "challenge-platform",
        ]
        if any(m in html_lower for m in cf_markers):
            return True
    # Also catch 200 CF challenges (older style)
    if status_code == 200:
        html_lower = html.lower()
        if "just a moment" in html_lower and "cloudflare" in html_lower:
            return True
    return False


def _has_images_dir(order_id: str) -> bool:
    """Check if data/images/{order_id}/ exists and has files."""
    img_dir = os.path.join("data", "images", order_id)
    if not os.path.isdir(img_dir):
        return False
    return len(os.listdir(img_dir)) > 0


def _should_try_deep_verify_for_shell_page(result: Dict[str, Any]) -> bool:
    """
    Heuristic: static HTTP fetch often returns only a JS app shell.
    In that case we can get false negatives (missing links/images, ~0% content).
    """
    if result.get("verified"):
        return False
    if result.get("_shell_page_suspected"):
        return True
    issues = set(result.get("status", "").split(","))
    if "MISSING_LINKS" not in issues:
        return False
    details = " ".join(result.get("issues") or []).lower()
    thin_content = "published vs" in details and "(0%)" in details
    images_missing = "none found on published page" in details
    return thin_content or images_missing


def _looks_like_js_shell_page(html: str, soup: BeautifulSoup) -> bool:
    """
    Detect common SPA shell responses where static HTTP verification is unreliable.
    """
    html_lower = html.lower()
    if "<app-root" in html_lower:
        return True
    has_base_root = bool(soup.find("base", href="/"))
    has_bundle_script = bool(
        soup.find("script", src=re.compile(r"(?:main|runtime|polyfills|vendor)\..*\.js", re.IGNORECASE))
    )
    return has_base_root and has_bundle_script


# ---------------------------------------------------------------------------
# Core verification
# ---------------------------------------------------------------------------

async def verify_live_url(
    order_id: str,
    submitted_url: str,
    db: Session,
    *,
    auto_update_status: bool = True,
    retry_count: int = 1,
    retry_delay: float = 2.0,
) -> Dict[str, Any]:
    """
    Comprehensive verification of a submitted live URL.
    Retries on non-VERIFIED results to handle slow page propagation.

    Returns dict with keys:
      - status: comma-separated issue codes or "VERIFIED"
      - issues: list of human-readable issue descriptions
      - details: per-link detail dicts
      - verified: bool (True only when status == "VERIFIED")
      - order_id, domain, live_url, checked_at
    """
    import asyncio as _asyncio

    for attempt in range(1 + retry_count):
        is_last = attempt == retry_count
        # Always allow auto_update: on success we want to mark live immediately,
        # on the final failed attempt we want to record the failure.
        result = await _verify_live_url_once(order_id, submitted_url, db,
                                              auto_update_status=auto_update_status)
        if result["verified"] or is_last:
            # If static fetch likely hit a JS shell, retry in real browser before returning failure.
            if not result["verified"] and _should_try_deep_verify_for_shell_page(result):
                try:
                    deep_result = await deep_verify_live_url(
                        order_id, submitted_url, db,
                        auto_update_status=auto_update_status,
                    )
                    if deep_result.get("status") not in ("BROWSER_ERROR", "VERIFICATION_ERROR"):
                        return deep_result
                    # Browser verification unavailable/unreliable: do not treat static-shell checks as publisher errors.
                    return {
                        **result,
                        "status": "VERIFICATION_ERROR",
                        "issues": ["Page appears JS-rendered/app-shell; automatic static verification is unreliable. Please verify manually."],
                        "verified": False,
                    }
                except Exception:
                    return {
                        **result,
                        "status": "VERIFICATION_ERROR",
                        "issues": ["Page appears JS-rendered/app-shell; automatic static verification is unreliable. Please verify manually."],
                        "verified": False,
                    }
            # If failed due to Cloudflare challenge, auto-escalate to deep verify
            if not result["verified"] and result.get("_cloudflare_blocked"):
                try:
                    deep_result = await deep_verify_live_url(
                        order_id, submitted_url, db,
                        auto_update_status=auto_update_status,
                    )
                    # If deep verify also failed with browser error, return a friendlier message
                    if deep_result.get("status") in ("BROWSER_ERROR", "VERIFICATION_ERROR"):
                        return {
                            **result,
                            "status": "CLOUDFLARE_BLOCKED",
                            "issues": ["Site is behind Cloudflare protection — automatic verification is not possible. Please verify manually."],
                            "verified": False,
                        }
                    return deep_result
                except Exception:
                    return {
                        **result,
                        "status": "CLOUDFLARE_BLOCKED",
                        "issues": ["Site is behind Cloudflare protection — automatic verification is not possible. Please verify manually."],
                        "verified": False,
                    }
            return result
        # Wait before retry — page might still be propagating
        await _asyncio.sleep(retry_delay)

    # Final fallback: deep verify if CF blocked
    if not result["verified"] and result.get("_cloudflare_blocked"):
        try:
            deep_result = await deep_verify_live_url(
                order_id, submitted_url, db,
                auto_update_status=auto_update_status,
            )
            if deep_result.get("status") in ("BROWSER_ERROR", "VERIFICATION_ERROR"):
                return {
                    **result,
                    "status": "CLOUDFLARE_BLOCKED",
                    "issues": ["Site is behind Cloudflare protection — automatic verification is not possible. Please verify manually."],
                    "verified": False,
                }
            return deep_result
        except Exception:
            return {
                **result,
                "status": "CLOUDFLARE_BLOCKED",
                "issues": ["Site is behind Cloudflare protection — automatic verification is not possible. Please verify manually."],
                "verified": False,
            }
    return result


async def _verify_live_url_once(
    order_id: str,
    submitted_url: str,
    db: Session,
    *,
    auto_update_status: bool = True,
) -> Dict[str, Any]:
    """Single verification attempt."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError(f"Order {order_id} not found")

    domain = db.query(Domain).filter(Domain.id == order.domain_id).first()
    if not domain:
        raise ValueError(f"Domain not found for order {order_id}")

    # Normalise URL
    submitted_url = submitted_url.strip()
    if not submitted_url.startswith("http"):
        submitted_url = "https://" + submitted_url

    issues: List[str] = []       # machine codes
    issue_details: List[str] = []  # human descriptions
    link_details: List[dict] = []

    # --- 1. Domain match ---
    url_domain = _extract_domain(submitted_url)
    expected_domain = domain.domain.lower().replace("www.", "")
    # Match if either domain contains the other, or they share the same base domain
    # Handles: en.devozki.com vs devozki.com, www.site.com vs site.com, etc.
    domains_match = (
        expected_domain in url_domain
        or url_domain in expected_domain
        or expected_domain.split(".")[-2:] == url_domain.split(".")[-2:]  # same base domain
    )
    if not domains_match:
        return _result(order_id, domain.domain, submitted_url, False,
                       ["NOT_LIVE"], [f"URL domain '{url_domain}' doesn't match '{expected_domain}'"],
                       [], db, order, auto_update_status)

    # --- 2. Fetch page ---
    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            resp = await client.get(
                submitted_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
    except Exception as e:
        return _result(order_id, domain.domain, submitted_url, False,
                       ["NOT_LIVE"], [f"Failed to fetch: {e}"], [], db, order, auto_update_status)

    if resp.status_code != 200:
        result = _result(order_id, domain.domain, submitted_url, False,
                         ["NOT_LIVE"], [f"HTTP {resp.status_code}"], [], db, order, auto_update_status,
                         http_status=resp.status_code)
        if _is_cloudflare_challenge(resp.text, resp.status_code):
            result["_cloudflare_blocked"] = True
        return result

    html = resp.text

    # Even a 200 can be a Cloudflare JS challenge page
    if _is_cloudflare_challenge(html, 200):
        result = _result(order_id, domain.domain, submitted_url, False,
                         ["NOT_LIVE"], ["Cloudflare bot challenge — browser render required"],
                         [], db, order, auto_update_status, http_status=200)
        result["_cloudflare_blocked"] = True
        return result
    # Try lxml first (more robust), fall back to html.parser
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    # Collect expected links
    order_links: List[OrderLink] = db.query(OrderLink).filter(OrderLink.order_id == order.id).order_by(OrderLink.slot).all()
    if not order_links and order.target_url and order.anchor_text:
        # Legacy single-link orders
        class _Fake:
            def __init__(self, t, a):
                self.target_url = t
                self.anchor_text = a
                self.slot = 1
        order_links = [_Fake(order.target_url, order.anchor_text)]

    if not order_links:
        return _result(order_id, domain.domain, submitted_url, False,
                       ["MISSING_LINKS"], ["No target URLs configured for this order"],
                       [], db, order, auto_update_status, http_status=200)

    # --- 3. Check each link ---
    all_page_links = soup.find_all("a", href=True)

    for olink in order_links:
        expected_url = olink.target_url
        expected_anchor = olink.anchor_text.strip()
        detail: dict = {
            "slot": olink.slot,
            "expected_url": olink.target_url,
            "expected_anchor": expected_anchor,
            "found": False,
            "found_url": None,
            "found_anchor": None,
            "is_dofollow": None,
            "issues": [],
        }

        # Find matching <a> by href
        matched_tag = None
        for a in all_page_links:
            href = a["href"].strip()
            # Skip empty or fragment-only links
            if not href or href in ('#', '/'):
                continue
            
            # Try to match URL using robust comparison
            if _urls_match(expected_url, href):
                matched_tag = a
                break
        
        # Fallback: search by anchor text if URL match failed
        # (some sites rewrite hrefs through redirects/trackers)
        if not matched_tag:
            for a in all_page_links:
                text = a.get_text(separator=" ", strip=True)
                text_norm = _normalize_anchor(text)
                exp_norm = _normalize_anchor(expected_anchor)
                if text_norm and text_norm == exp_norm:
                    matched_tag = a
                    break

        if not matched_tag:
            detail["issues"].append("MISSING_LINKS")
            if "MISSING_LINKS" not in issues:
                issues.append("MISSING_LINKS")
            issue_details.append(f"Link #{olink.slot}: target URL '{olink.target_url}' not found on page")
        else:
            detail["found"] = True
            detail["found_url"] = matched_tag["href"]
            # Extract anchor text, handling nested elements
            actual_anchor = matched_tag.get_text(separator=" ", strip=True)
            detail["found_anchor"] = actual_anchor

            # Check anchor text - normalize whitespace and compare case-insensitively
            actual_norm = _normalize_anchor(actual_anchor)
            expected_norm = _normalize_anchor(expected_anchor)
            
            if actual_norm != expected_norm:
                detail["issues"].append("WRONG_ANCHORS")
                if "WRONG_ANCHORS" not in issues:
                    issues.append("WRONG_ANCHORS")
                issue_details.append(
                    f"Link #{olink.slot}: anchor should be '{expected_anchor}' but found '{actual_anchor}'"
                )

            # Check dofollow
            rel = matched_tag.get("rel", [])
            if isinstance(rel, str):
                rel = rel.split()
            rel_lower = [r.lower() for r in rel]
            if "nofollow" in rel_lower or "sponsored" in rel_lower or "ugc" in rel_lower:
                detail["is_dofollow"] = False
                detail["issues"].append("NOFOLLOW")
                if "NOFOLLOW" not in issues:
                    issues.append("NOFOLLOW")
                issue_details.append(f"Link #{olink.slot}: has rel=\"{' '.join(rel)}\" (expected dofollow)")
            else:
                detail["is_dofollow"] = True

        link_details.append(detail)

    # --- 4. Images check ---
    if _has_images_dir(order_id):
        page_images = soup.find_all("img")
        if len(page_images) == 0:
            issues.append("IMAGES_MISSING")
            issue_details.append("Order had images but none found on published page")

    # --- 5. Content completeness ---
    if order.article_content:
        original_wc = _word_count(order.article_content)
        # Get visible text from page body
        page_text = soup.get_text(separator=" ", strip=True)
        published_wc = _word_count(page_text)
        if original_wc > 0 and published_wc < original_wc * 0.7:
            issues.append("ARTICLE_INCOMPLETE")
            issue_details.append(
                f"Content may be truncated: ~{published_wc} words published vs ~{original_wc} original ({int(published_wc/original_wc*100)}%)"
            )

    verified = len(issues) == 0
    status_str = "VERIFIED" if verified else ",".join(issues)

    result = _result(order_id, domain.domain, submitted_url, verified,
                     issues, issue_details, link_details, db, order, auto_update_status,
                     http_status=200)
    if "MISSING_LINKS" in issues and _looks_like_js_shell_page(html, soup):
        # Internal hint for verify_live_url() to force deep verification fallback.
        result["_shell_page_suspected"] = True
    return result


def _result(
    order_id: str, domain_name: str, url: str, verified: bool,
    issues: list, issue_details: list, link_details: list,
    db: Session, order: Order, auto_update: bool,
    http_status: int = None,
) -> dict:
    """Build result dict, save LinkCheck, optionally update order status."""
    status_str = "VERIFIED" if verified else ",".join(issues)
    now = datetime.utcnow()

    # Save LinkCheck record
    check = LinkCheck(
        order_id=order_id,
        checked_at=now,
        status=status_str,
        http_status=http_status,
        found_anchor=link_details[0]["found_anchor"] if link_details and link_details[0].get("found_anchor") else None,
        found_url=link_details[0]["found_url"] if link_details and link_details[0].get("found_url") else None,
        notes="; ".join(issue_details) if issue_details else "All checks passed",
    )
    db.add(check)

    if auto_update:
        order.last_checked_at = now
        order.last_check_status = status_str
        if verified:
            order.live_url = url
            order.live_at = order.live_at or now
            # Always go straight to "live" on successful verification, regardless of current status
            order.status = "live"

    db.commit()

    return {
        "verified": verified,
        "status": status_str,
        "order_id": order_id,
        "domain": domain_name,
        "live_url": url,
        "http_status": http_status,
        "issues": issue_details,
        "link_details": link_details,
        "checked_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Deep verification with agent-browser
# ---------------------------------------------------------------------------

async def deep_verify_live_url(
    order_id: str,
    submitted_url: str,
    db: Session,
    *,
    auto_update_status: bool = True,
) -> Dict[str, Any]:
    """
    Deep verification using agent-browser (real browser rendering).
    
    Takes screenshot, verifies rendered links (not just HTML source),
    checks images actually loaded, validates dofollow on rendered page.
    
    Returns dict with:
      - status: "VERIFIED" or comma-separated issue codes
      - issues: list of issue descriptions
      - screenshot_path: path to saved screenshot
      - verified: bool
      - details: link verification details
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError(f"Order {order_id} not found")
    
    domain = db.query(Domain).filter(Domain.id == order.domain_id).first()
    if not domain:
        raise ValueError(f"Domain not found for order {order_id}")
    
    # Normalize URL
    submitted_url = submitted_url.strip()
    if not submitted_url.startswith("http"):
        submitted_url = "https://" + submitted_url
    
    issues: List[str] = []
    issue_details: List[str] = []
    link_details: List[dict] = []
    screenshot_path: Optional[str] = None
    
    # --- 1. Domain match ---
    url_domain = _extract_domain(submitted_url)
    expected_domain = domain.domain.lower().replace("www.", "")
    domains_match = (
        expected_domain in url_domain
        or url_domain in expected_domain
        or expected_domain.split(".")[-2:] == url_domain.split(".")[-2:]
    )
    if not domains_match:
        return {
            "verified": False,
            "status": "NOT_LIVE",
            "issues": [f"URL domain '{url_domain}' doesn't match '{expected_domain}'"],
            "screenshot_path": None,
            "link_details": [],
            "order_id": order_id,
            "domain": domain.domain,
            "live_url": submitted_url,
        }
    
    # Create screenshots directory
    screenshot_dir = os.path.join("data", "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)
    
    # Screenshot filename: domain_YYYYMMDD_HHMMSS.png
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_domain = re.sub(r'[^a-z0-9_-]', '_', url_domain.lower())
    screenshot_filename = f"{safe_domain}_{timestamp}.png"
    screenshot_path = os.path.join(screenshot_dir, screenshot_filename)
    
    browser_ctx = None

    async def _playwright_fallback_deep_verify(order_links_local: List[OrderLink]) -> Dict[str, Any]:
        """
        Fallback deep verify path when agent-browser daemon is unavailable.
        Uses Python Playwright directly from backend venv.
        """
        from playwright.async_api import async_playwright

        pw_issues: List[str] = []
        pw_issue_details: List[str] = []
        pw_link_details: List[dict] = []
        pw_screenshot_path = screenshot_path

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(submitted_url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(5000)

                if pw_screenshot_path:
                    try:
                        await page.screenshot(path=pw_screenshot_path, full_page=True)
                    except Exception:
                        pw_screenshot_path = None

                page_text = await page.inner_text("body")

                for olink in order_links_local:
                    expected_url = olink.target_url
                    expected_anchor = olink.anchor_text.strip()
                    detail: dict = {
                        "slot": olink.slot,
                        "expected_url": expected_url,
                        "expected_anchor": expected_anchor,
                        "found": False,
                        "found_url": None,
                        "found_anchor": None,
                        "is_dofollow": None,
                        "issues": [],
                    }

                    eval_res = await page.evaluate(
                        """({ expectedUrl, expectedAnchor }) => {
                            function normalizeUrl(url) {
                                if (!url) return '';
                                return url.toLowerCase().replace(/^https?:\\/\\//, '').replace(/^www\\./, '').replace(/\\/$/, '');
                            }
                            function normalizeText(text) {
                                return (text || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                            }
                            const allLinks = Array.from(document.querySelectorAll('a[href]'));
                            const expectedUrlNorm = normalizeUrl(expectedUrl);
                            const expectedAnchorNorm = normalizeText(expectedAnchor);
                            let found = allLinks.find(a => {
                                const hrefNorm = normalizeUrl(a.href);
                                return hrefNorm && hrefNorm === expectedUrlNorm;
                            });
                            if (!found) {
                                found = allLinks.find(a => {
                                    const hrefNorm = normalizeUrl(a.href);
                                    if (!hrefNorm) return false;
                                    if (hrefNorm.startsWith(expectedUrlNorm + '/') || hrefNorm.startsWith(expectedUrlNorm + '?')) return true;
                                    if (expectedUrlNorm.startsWith(hrefNorm + '/') || expectedUrlNorm.startsWith(hrefNorm + '?')) return true;
                                    return false;
                                });
                            }
                            if (!found) {
                                found = allLinks.find(a => normalizeText(a.textContent) === expectedAnchorNorm);
                            }
                            if (!found) return { found: false };
                            const rel = found.getAttribute('rel') || '';
                            const relLower = rel.toLowerCase();
                            const isDofollow = !relLower.includes('nofollow') && !relLower.includes('sponsored') && !relLower.includes('ugc');
                            return {
                                found: true,
                                href: found.href,
                                text: (found.textContent || '').trim(),
                                rel,
                                isDofollow,
                            };
                        }""",
                        {"expectedUrl": expected_url, "expectedAnchor": expected_anchor},
                    )

                    if not eval_res.get("found"):
                        detail["issues"].append("MISSING_LINKS")
                        if "MISSING_LINKS" not in pw_issues:
                            pw_issues.append("MISSING_LINKS")
                        pw_issue_details.append(f"Link #{olink.slot}: target URL '{expected_url}' not found on rendered page")
                    else:
                        detail["found"] = True
                        detail["found_url"] = eval_res.get("href")
                        detail["found_anchor"] = eval_res.get("text")
                        detail["is_dofollow"] = bool(eval_res.get("isDofollow"))

                        actual_norm = _normalize_anchor(eval_res.get("text", ""))
                        expected_norm = _normalize_anchor(expected_anchor)
                        if actual_norm != expected_norm:
                            detail["issues"].append("WRONG_ANCHORS")
                            if "WRONG_ANCHORS" not in pw_issues:
                                pw_issues.append("WRONG_ANCHORS")
                            pw_issue_details.append(
                                f"Link #{olink.slot}: anchor should be '{expected_anchor}' but found '{eval_res.get('text', '')}'"
                            )

                        if not eval_res.get("isDofollow", False):
                            detail["issues"].append("NOFOLLOW")
                            if "NOFOLLOW" not in pw_issues:
                                pw_issues.append("NOFOLLOW")
                            pw_issue_details.append(f"Link #{olink.slot}: has rel=\"{eval_res.get('rel', '')}\" (expected dofollow)")

                    pw_link_details.append(detail)

                if _has_images_dir(order_id):
                    try:
                        img_count = await page.evaluate(
                            "Array.from(document.querySelectorAll('img')).filter(img => img.complete && img.naturalWidth > 0).length"
                        )
                        if int(img_count or 0) == 0:
                            pw_issues.append("IMAGES_MISSING")
                            pw_issue_details.append("Order had images but none found loaded on rendered page")
                    except Exception:
                        pass

                if order.article_content and page_text:
                    original_wc = _word_count(order.article_content)
                    published_wc = _word_count(page_text)
                    if original_wc > 0 and published_wc < original_wc * 0.7:
                        pw_issues.append("ARTICLE_INCOMPLETE")
                        pw_issue_details.append(
                            f"Content may be truncated: ~{published_wc} words published vs ~{original_wc} original ({int(published_wc/original_wc*100)}%)"
                        )
            finally:
                await browser.close()

        pw_verified = len(pw_issues) == 0
        pw_status = "VERIFIED" if pw_verified else ",".join(pw_issues)
        return {
            "verified": pw_verified,
            "status": pw_status,
            "issues": pw_issue_details,
            "link_details": pw_link_details,
            "screenshot_path": pw_screenshot_path,
            "order_id": order_id,
            "domain": domain.domain,
            "live_url": submitted_url,
        }
    try:
        # Try HEADED mode first (better against Cloudflare), fall back to headless
        # if headed fails for any reason (display crash, Wayland issue, etc.).
        opened = False
        try:
            browser_ctx = AgentBrowser(session=f"verify-{order_id}", timeout=45, headless=False)
            browser = await browser_ctx.__aenter__()
            await browser.open(submitted_url, wait_load=True)
            opened = True
        except (AgentBrowserError, Exception) as e:
            # Clean up failed headed browser
            if browser_ctx:
                try:
                    await browser_ctx.__aexit__(None, None, None)
                except Exception:
                    pass
                browser_ctx = None
            
            # Always retry headless on headed failure
            print(f"[deep_verify] Headed mode failed, retrying headless: {str(e)[:200]}")
            try:
                browser_ctx = AgentBrowser(session=f"verify-{order_id}-hl", timeout=45, headless=True)
                browser = await browser_ctx.__aenter__()
                await browser.open(submitted_url, wait_load=True)
                opened = True
            except (AgentBrowserError, Exception) as e2:
                if browser_ctx:
                    try:
                        await browser_ctx.__aexit__(None, None, None)
                    except Exception:
                        pass
                    browser_ctx = None
                # If agent-browser daemon is unavailable in service context,
                # fall back to direct Playwright verification.
                combined_error = f"headed: {str(e)[:250]}; headless: {str(e2)[:250]}"
                if "Failed to start daemon" in combined_error:
                    order_links_fb: List[OrderLink] = db.query(OrderLink).filter(
                        OrderLink.order_id == order.id
                    ).order_by(OrderLink.slot).all()
                    if not order_links_fb and order.target_url and order.anchor_text:
                        class _FakeLink:
                            def __init__(self, t, a):
                                self.target_url = t
                                self.anchor_text = a
                                self.slot = 1
                        order_links_fb = [_FakeLink(order.target_url, order.anchor_text)]
                    try:
                        return await _playwright_fallback_deep_verify(order_links_fb)
                    except Exception as pw_e:
                        return {
                            "verified": False,
                            "status": "BROWSER_ERROR",
                            "issues": ["BROWSER_ERROR"],
                            "screenshot_path": None,
                            "link_details": [],
                            "order_id": order_id,
                            "domain": domain.domain,
                            "live_url": submitted_url,
                            "_internal_error": f"{combined_error}; playwright_fallback: {str(pw_e)[:250]}",
                        }
                return {
                    "verified": False,
                    "status": "BROWSER_ERROR",
                    "issues": ["BROWSER_ERROR"],
                    "screenshot_path": None,
                    "link_details": [],
                    "order_id": order_id,
                    "domain": domain.domain,
                    "live_url": submitted_url,
                    "_internal_error": combined_error,
                }

        if not opened:
            return {
                "verified": False,
                "status": "BROWSER_ERROR",
                "issues": ["BROWSER_ERROR"],
                "screenshot_path": None,
                "link_details": [],
                "order_id": order_id,
                "domain": domain.domain,
                "live_url": submitted_url,
            }

        # Wait for dynamic content and Cloudflare challenge auto-resolution.
        # Headed Chromium solves CF challenges automatically but needs time.
        try:
            await browser.wait(milliseconds=5000)
        except Exception:
            pass  # Non-critical
        
        # Take screenshot
        try:
            await browser.screenshot(screenshot_path, full_page=True)
        except Exception as e:
            issue_details.append(f"Screenshot failed: {str(e)}")
            screenshot_path = None
        
        # Get current URL (in case of redirects)
        try:
            final_url = await browser.get_url()
        except Exception:
            final_url = submitted_url
        
        # Get page text for content analysis
        try:
            page_text = await browser.get_text("body")
        except Exception:
            page_text = ""
        
        # Collect expected links
        order_links: List[OrderLink] = db.query(OrderLink).filter(
            OrderLink.order_id == order.id
        ).order_by(OrderLink.slot).all()
        
        if not order_links and order.target_url and order.anchor_text:
            # Legacy single-link orders
            class _FakeLink:
                def __init__(self, t, a):
                    self.target_url = t
                    self.anchor_text = a
                    self.slot = 1
            order_links = [_FakeLink(order.target_url, order.anchor_text)]
        
        if not order_links:
            return {
                "verified": False,
                "status": "MISSING_LINKS",
                "issues": ["No target URLs configured for this order"],
                "screenshot_path": screenshot_path,
                "link_details": [],
                "order_id": order_id,
                "domain": domain.domain,
                "live_url": submitted_url,
            }
        
        # --- Verify each link using JavaScript evaluation ---
        for olink in order_links:
            expected_url = olink.target_url
            expected_anchor = olink.anchor_text.strip()
            detail: dict = {
                "slot": olink.slot,
                "expected_url": expected_url,
                "expected_anchor": expected_anchor,
                "found": False,
                "found_url": None,
                "found_anchor": None,
                "is_dofollow": None,
                "issues": [],
            }
            
            # JavaScript to find link by href or anchor text in rendered DOM
            js_code = f"""
            (function() {{
                const expectedUrl = {json.dumps(expected_url)};
                const expectedAnchor = {json.dumps(expected_anchor)};
                
                function normalizeUrl(url) {{
                    if (!url) return '';
                    return url.toLowerCase().replace(/^https?:\\/\\//, '').replace(/^www\\./, '').replace(/\\/$/, '');
                }}
                
                function normalizeText(text) {{
                    return text.replace(/\\s+/g, ' ').trim().toLowerCase();
                }}
                
                const allLinks = Array.from(document.querySelectorAll('a[href]'));
                const expectedUrlNorm = normalizeUrl(expectedUrl);
                const expectedAnchorNorm = normalizeText(expectedAnchor);
                
                // Try to find by URL — exact match first, then prefix match
                // Avoid substring containment (camhours.com ⊂ camhours.com/free-chat)
                let found = allLinks.find(a => {{
                    const hrefNorm = normalizeUrl(a.href);
                    return hrefNorm && hrefNorm === expectedUrlNorm;
                }});
                // Fallback: one URL is a prefix of the other with a path separator
                if (!found) {{
                    found = allLinks.find(a => {{
                        const hrefNorm = normalizeUrl(a.href);
                        if (!hrefNorm) return false;
                        if (hrefNorm.startsWith(expectedUrlNorm + '/') || hrefNorm.startsWith(expectedUrlNorm + '?')) return true;
                        if (expectedUrlNorm.startsWith(hrefNorm + '/') || expectedUrlNorm.startsWith(hrefNorm + '?')) return true;
                        return false;
                    }});
                }}
                
                // Fallback: find by anchor text
                if (!found) {{
                    found = allLinks.find(a => {{
                        const textNorm = normalizeText(a.textContent);
                        return textNorm === expectedAnchorNorm;
                    }});
                }}
                
                if (!found) {{
                    return {{ found: false }};
                }}
                
                // Check rel attribute for dofollow
                const rel = found.getAttribute('rel') || '';
                const relLower = rel.toLowerCase();
                const isDofollow = !relLower.includes('nofollow') && !relLower.includes('sponsored') && !relLower.includes('ugc');
                
                // Check if link is actually visible (not display:none)
                const computed = window.getComputedStyle(found);
                const isVisible = computed.display !== 'none' && computed.visibility !== 'hidden' && computed.opacity !== '0';
                
                return {{
                    found: true,
                    href: found.href,
                    text: found.textContent.trim(),
                    rel: rel,
                    isDofollow: isDofollow,
                    isVisible: isVisible,
                }};
            }})();
            """
            
            try:
                result_json = await browser.eval_js(js_code)
                result = json.loads(result_json) if result_json else {"found": False}
            except Exception as e:
                detail["issues"].append("VERIFICATION_ERROR")
                issue_details.append(f"Link #{olink.slot}: Failed to verify in browser: {str(e)}")
                link_details.append(detail)
                continue
            
            if not result.get("found"):
                detail["issues"].append("MISSING_LINKS")
                if "MISSING_LINKS" not in issues:
                    issues.append("MISSING_LINKS")
                issue_details.append(f"Link #{olink.slot}: target URL '{expected_url}' not found on rendered page")
            else:
                detail["found"] = True
                detail["found_url"] = result["href"]
                detail["found_anchor"] = result["text"]
                detail["is_dofollow"] = result["isDofollow"]
                
                # Check anchor text
                actual_norm = _normalize_anchor(result["text"])
                expected_norm = _normalize_anchor(expected_anchor)
                
                if actual_norm != expected_norm:
                    detail["issues"].append("WRONG_ANCHORS")
                    if "WRONG_ANCHORS" not in issues:
                        issues.append("WRONG_ANCHORS")
                    issue_details.append(
                        f"Link #{olink.slot}: anchor should be '{expected_anchor}' but found '{result['text']}'"
                    )
                
                # Check dofollow
                if not result["isDofollow"]:
                    detail["issues"].append("NOFOLLOW")
                    if "NOFOLLOW" not in issues:
                        issues.append("NOFOLLOW")
                    issue_details.append(f"Link #{olink.slot}: has rel=\"{result['rel']}\" (expected dofollow)")
                
                # Check visibility
                if not result.get("isVisible", True):
                    detail["issues"].append("LINK_HIDDEN")
                    if "LINK_HIDDEN" not in issues:
                        issues.append("LINK_HIDDEN")
                    issue_details.append(f"Link #{olink.slot}: link exists but is hidden (display:none or visibility:hidden)")
            
            link_details.append(detail)
        
        # --- Check images ---
        if _has_images_dir(order_id):
            try:
                # Count actually loaded images (not broken)
                img_check_js = """
                Array.from(document.querySelectorAll('img')).filter(img => 
                    img.complete && img.naturalWidth > 0
                ).length
                """
                img_count_str = await browser.eval_js(img_check_js)
                img_count = int(img_count_str) if img_count_str.isdigit() else 0
                
                if img_count == 0:
                    issues.append("IMAGES_MISSING")
                    issue_details.append("Order had images but none found loaded on rendered page")
            except Exception:
                pass  # Non-critical
            
        # --- Content completeness ---
        if order.article_content and page_text:
            original_wc = _word_count(order.article_content)
            published_wc = _word_count(page_text)
            if original_wc > 0 and published_wc < original_wc * 0.7:
                issues.append("ARTICLE_INCOMPLETE")
                issue_details.append(
                    f"Content may be truncated: ~{published_wc} words published vs ~{original_wc} original ({int(published_wc/original_wc*100)}%)"
                )
    
    except AgentBrowserError as e:
        if browser_ctx:
            try:
                await browser_ctx.__aexit__(None, None, None)
            except Exception:
                pass
        return {
            "verified": False,
            "status": "BROWSER_ERROR",
            "issues": ["BROWSER_ERROR"],
            "screenshot_path": screenshot_path,
            "link_details": [],
            "order_id": order_id,
            "domain": domain.domain,
            "live_url": submitted_url,
            "_internal_error": str(e)[:500],
        }
    
    except Exception as e:
        if browser_ctx:
            try:
                await browser_ctx.__aexit__(None, None, None)
            except Exception:
                pass
        return {
            "verified": False,
            "status": "VERIFICATION_ERROR",
            "issues": ["VERIFICATION_ERROR"],
            "screenshot_path": screenshot_path,
            "link_details": [],
            "order_id": order_id,
            "domain": domain.domain,
            "_internal_error": str(e)[:500],
            "live_url": submitted_url,
        }
    
    # Close browser context
    if browser_ctx:
        try:
            await browser_ctx.__aexit__(None, None, None)
        except Exception:
            pass
    
    # Build result
    verified = len(issues) == 0
    status_str = "VERIFIED" if verified else ",".join(issues)
    now = datetime.utcnow()
    
    # Save LinkCheck record
    check = LinkCheck(
        order_id=order_id,
        checked_at=now,
        status=status_str,
        http_status=200,  # We got this far, so page loaded
        found_anchor=link_details[0]["found_anchor"] if link_details and link_details[0].get("found_anchor") else None,
        found_url=link_details[0]["found_url"] if link_details and link_details[0].get("found_url") else None,
        notes=f"Deep verification: {'; '.join(issue_details)}" if issue_details else "Deep verification: All checks passed",
    )
    db.add(check)
    
    if auto_update_status:
        order.last_checked_at = now
        order.last_check_status = status_str
        if verified:
            order.live_url = submitted_url
            order.live_at = order.live_at or now
            # Always go straight to "live" on successful verification, regardless of current status
            order.status = "live"
    
    db.commit()
    
    return {
        "verified": verified,
        "status": status_str,
        "order_id": order_id,
        "domain": domain.domain,
        "live_url": submitted_url,
        "screenshot_path": screenshot_path,
        "issues": issue_details,
        "link_details": link_details,
        "checked_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Monthly health check
# ---------------------------------------------------------------------------

async def check_all_live_links(db: Session) -> Dict[str, Any]:
    """
    Re-verify all orders with status 'published', 'paid', or 'live' that have a live_url.
    Only checks orders not checked in the last 30 days.

    Returns summary dict.
    """
    cutoff = datetime.utcnow() - timedelta(days=30)

    orders = db.query(Order).filter(
        Order.status.in_(["published", "paid", "live"]),
        Order.live_url.isnot(None),
        (Order.last_checked_at.is_(None)) | (Order.last_checked_at < cutoff),
    ).all()

    results = {
        "total_checked": 0,
        "verified": 0,
        "issues": 0,
        "removed": 0,
        "details": [],
    }

    # Import here to avoid circular imports at module level
    from .slack_notifier import send_slack_alert

    for order in orders:
        try:
            result = await verify_live_url(order.id, order.live_url, db, auto_update_status=True)
            results["total_checked"] += 1

            if result["verified"]:
                results["verified"] += 1
            elif "NOT_LIVE" in result["status"]:
                results["removed"] += 1
                order.status = "offline"
                order.last_check_status = "offline"
                db.commit()
                # Slack alert for offline links
                domain = db.query(Domain).filter(Domain.id == order.domain_id).first()
                await send_slack_alert("LINK_OFFLINE", order, domain, extra={"url": order.live_url})
            else:
                results["issues"] += 1

            results["details"].append({
                "order_id": order.id,
                "live_url": order.live_url,
                "status": result["status"],
            })
        except Exception as e:
            results["details"].append({
                "order_id": order.id,
                "error": str(e),
            })

    return results
