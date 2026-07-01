"""
Adult site classifier — 3-tier approach:
1. Domain keyword scan (instant, free)
2. Page content scan (HTTP fetch, ~2s per domain)
3. AI classification (Claude Sonnet, only for ambiguous cases)
"""

import re
import logging
import httpx
from typing import Optional

log = logging.getLogger(__name__)

# Tier 1: Domain name keywords (strongly adult)
ADULT_KEYWORDS = {
    # Explicit
    "porn", "xxx", "sex", "nude", "naked", "nsfw", "adult", "erotic",
    "hentai", "milf", "dilf", "gilf", "fetish", "bdsm", "bondage",
    "escort", "hooker", "prostitut", "brothel",
    # Cam specific
    "cam", "webcam", "livecam", "camgirl", "camshow", "livejasmin",
    "chaturbate", "stripchat", "bongacam",
    # Body parts / acts
    "boob", "tit", "ass", "anal", "blowjob", "handjob", "creampie",
    "cumshot", "facial", "gangbang", "threesome", "orgy",
    "pussy", "cock", "dick", "penis", "vagina", "clit",
    # Genres
    "lesbian", "gay", "twink", "shemale", "tranny", "trans",
    "interracial", "cuckold", "swinger", "hotwife",
    # Tube / content
    "tube", "fap", "jerk", "wank", "spank", "smut", "sleazy",
    "xvideo", "xhamster", "redtube", "youporn", "pornhub",
    "xnxx", "beeg", "brazzers", "realitykings", "bangbros",
    # Dating (adult-adjacent)
    "hookup", "fling", "bangbuddy", "fucknow",
    # Subculture / specific
    "rule34", "r34", "onlyfans", "fansly", "manyvids",
    "jav", "javhd", "javdoe",
    "doujin", "nhentai", "ehentai", "gelbooru", "danbooru",
}

# Words that look adult but aren't (avoid false positives)
FALSE_POSITIVES = {
    "camden", "camera", "cambridge", "campaign", "campbell", "campus",
    "sextant", "sextet", "sussex", "essex", "middlesex", "unisex",
    "therapist", "dickens", "dickson", "hancock", "woodcock", "peacock",
    "scunthorpe", "arsenal", "cockburn", "penistone",
    "analytic", "analyst", "analysis", "canal",
    "classic", "class", "assessment",
    "nudge", "nucleus",
    "titanic", "titan", "title",
    "cocktail",
}

# Tier 2: Page content signals
ADULT_META_SIGNALS = [
    r'<meta\s+name=["\']rating["\']\s+content=["\'](?:adult|mature|RTA)',
    r'RTA-5042-1996-1400-1577-RTA',
    r'<meta\s+name=["\']classification["\']\s+content=["\']adult',
]

ADULT_AD_NETWORKS = [
    "exoclick", "trafficjunky", "juicyads", "trafficstars", "ero-advertising",
    "plugrush", "clickadu", "adxxx", "exosrv", "realsrv", "tsyndicate",
    "trafficfactory", "awempire", "crakrevenue",
]

AGE_GATE_PATTERNS = [
    r"(?:are you|i am|i'm)\s+(?:over\s+)?18",
    r"you must be (?:at least )?18",
    r"18\s*\+\s*(?:only|enter|agree|content|warning)",
    r"adults?\s+only",
    r"age\s+verification",
    r"enter\s+(?:if|only)\s+.*18",
    r"by entering.*(?:18|legal age|adult)",
    r"this (?:site|website) (?:contains|is intended for) (?:adult|mature|explicit)",
    # Japanese
    r"18歳未満",
    r"18歳以上",
    r"成人向け",
    r"アダルトサイト",
    # Chinese
    r"18歲以下",
    r"未滿18",
    r"成人內容",
    r"成人网站",
    # Korean
    r"18세 미만",
    r"성인 인증",
]

ADULT_TITLE_KEYWORDS = [
    "porn", "xxx", "sex", "nude", "cam", "adult", "erotic",
    "escort", "live sex", "free porn", "watch porn", "hentai",
    "webcam", "nsfw", "naked", "explicit", "av ",
    # Japanese
    "エロ", "アダルト", "無修正", "av女優", "同人", "成人",
    "オナニー", "フェラ", "おっぱい", "エッチ", "痴女",
    "熟女", "巨乳", "素人", "ヌード",
    # Chinese
    "色情", "成人", "裸体", "情色", "自拍", "做爱",
    "口交", "肛交", "av在線", "免費av", "高清av",
    # Korean
    "야동", "성인", "자위", "av여배우",
    # Spanish/Portuguese
    "porno", "sexo", "desnuda",
    # German
    "nackt", "erotik",
    # French
    "sexe", "porno",
    # Arabic
    "سكس", "اباحي", "نيك", "قحبة", "عاري",
    # Turkish
    "porno", "sikiş", "seks",
    # Subculture
    "rule34", "rule 34", "hentai", "doujin", "r18",
]


# TLDs that are strong adult signals
ADULT_TLDS = {".cam", ".xxx", ".adult", ".sex", ".porn", ".sexy"}


def classify_domain_keyword(domain: str) -> Optional[bool]:
    """Tier 1: Check domain name against keyword lists.
    
    Returns:
        True = definitely adult
        False = definitely NOT adult (false positive word detected)
        None = inconclusive, needs page scan
    """
    domain_lower = domain.lower().replace("www.", "")
    name_part = domain_lower.split(".")[0]  # e.g. "pornhub" from "pornhub.com"
    tld = "." + domain_lower.split(".")[-1] if "." in domain_lower else ""
    
    # Check adult TLDs
    if tld in ADULT_TLDS:
        return True
    
    # Check false positives first
    for fp in FALSE_POSITIVES:
        if fp in name_part:
            return None  # Inconclusive — let page scan decide
    
    # Check adult keywords
    for keyword in ADULT_KEYWORDS:
        if keyword in name_part:
            return True
    
    return None  # Inconclusive


def classify_page_content(html: str, url: str = "") -> dict:
    """Tier 2: Scan page HTML for adult signals.
    
    Returns dict with:
        is_adult: True/False/None (None = still inconclusive)
        confidence: 0.0-1.0
        signals: list of detected signals
    """
    html_lower = html.lower()
    signals = []
    score = 0
    
    # Meta rating tags (very strong signal)
    for pattern in ADULT_META_SIGNALS:
        if re.search(pattern, html, re.IGNORECASE):
            signals.append("meta_adult_rating")
            score += 40
    
    # Adult ad networks (strong signal)
    for network in ADULT_AD_NETWORKS:
        if network in html_lower:
            signals.append(f"ad_network:{network}")
            score += 15
            break  # One is enough
    
    # Age gate / 18+ warnings (strong signal)
    for pattern in AGE_GATE_PATTERNS:
        if re.search(pattern, html_lower):
            signals.append("age_gate")
            score += 25
            break
    
    # Title keywords
    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    if title_match:
        title = title_match.group(1).lower()
        for kw in ADULT_TITLE_KEYWORDS:
            if kw in title:
                signals.append(f"title:{kw}")
                score += 20
                break
    
    # Meta description keywords
    desc_match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
    if desc_match:
        desc = desc_match.group(1).lower()
        adult_count = sum(1 for kw in ADULT_TITLE_KEYWORDS if kw in desc)
        if adult_count >= 2:
            signals.append(f"meta_desc:{adult_count}_keywords")
            score += 15
    
    # Determine result
    if score >= 40:
        return {"is_adult": True, "confidence": min(score / 100, 1.0), "signals": signals}
    elif score == 0:
        return {"is_adult": False, "confidence": 0.7, "signals": ["no_adult_signals"]}
    else:
        return {"is_adult": None, "confidence": score / 100, "signals": signals}


async def classify_ai(domain: str, title: str = "", description: str = "", signals: list = None) -> dict:
    """Tier 3: AI classification for ambiguous cases.
    
    Returns dict with: is_adult, confidence, reason
    """
    import json
    import os
    from ..config import settings
    
    api_key = getattr(settings, 'anthropic_api_key', None) or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"is_adult": None, "confidence": 0, "reason": "No API key"}
    
    prompt = f"""Is this an adult/NSFW website? Answer with JSON only.

Domain: {domain}
Title: {title or 'unknown'}
Description: {description or 'unknown'}
{f'Partial signals found: {", ".join(signals)}' if signals else ''}

Classify as adult if: porn, cam sites, escort services, adult dating, nude/explicit content, sex toys (primary business), strip clubs, adult entertainment, adult video/manga/anime sites, tube sites.

NOT adult: mainstream dating (Tinder, Bumble), lingerie brands, sex education, medical/health, relationship advice, swimwear, mainstream video sites.

If the title is "Just a moment..." or similar Cloudflare challenge, the site is likely behind an age gate — this is itself a mild adult signal. Consider the domain name carefully in that case.

Consider non-English meanings: "kosel" (Arabic slang), "jable" (Chinese AV), "xfree", etc. may be adult in other languages.
Domain names containing transliterated adult words from Arabic, Chinese, Japanese, Korean, Turkish, or other languages should be classified as adult.

If you genuinely cannot determine from available info, set is_adult to null (not false).

Reply ONLY with: {{"is_adult": true/false/null, "confidence": 0.0-1.0, "reason": "brief explanation"}}"""

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.anthropic_model,
                    "max_tokens": 200,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            text = resp.json()["content"][0]["text"]
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                return json.loads(match.group())
    except Exception as e:
        log.warning(f"AI classification failed for {domain}: {e}")
    
    return {"is_adult": None, "confidence": 0, "reason": "classification failed"}


async def classify_domain(domain: str) -> dict:
    """Full 3-tier classification pipeline.
    
    Returns dict with:
        domain, is_adult, confidence, method, signals/reason
    """
    result = {"domain": domain, "is_adult": None, "confidence": 0, "method": "unknown", "detail": ""}
    
    # Tier 1: Keyword scan
    keyword_result = classify_domain_keyword(domain)
    if keyword_result is True:
        result.update({"is_adult": True, "confidence": 0.95, "method": "keyword", "detail": "adult keyword in domain"})
        return result
    
    # Tier 2: Page content scan
    title = ""
    description = ""
    signals = []
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                f"https://{domain}",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            html = resp.text
            
            # Always extract title/desc even from non-200 responses (CF pages sometimes leak the real title)
            title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip()[:200] if title_match else ""
            desc_match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
            description = desc_match.group(1).strip()[:300] if desc_match else ""
            
            if resp.status_code == 200:
                page_result = classify_page_content(html, str(resp.url))
                signals = page_result["signals"]
                
                if page_result["is_adult"] is True:
                    result.update({"is_adult": True, "confidence": page_result["confidence"], "method": "page_scan", "detail": ", ".join(signals)})
                    return result
                elif page_result["is_adult"] is False and page_result["confidence"] >= 0.7:
                    # Don't trust "not adult" if page is very short (might be a redirect/stub)
                    if len(html) > 2000:
                        result.update({"is_adult": False, "confidence": page_result["confidence"], "method": "page_scan", "detail": "no adult signals on page"})
                        return result
                # else: inconclusive, fall through to AI
            else:
                # Non-200 (likely CF block) — check title for adult signals anyway
                for kw in ADULT_TITLE_KEYWORDS:
                    if kw in title.lower():
                        signals.append(f"title:{kw}")
                        result.update({"is_adult": True, "confidence": 0.8, "method": "page_scan_title", "detail": f"title contains '{kw}' (page was CF-blocked)"})
                        return result
    except Exception as e:
        log.warning(f"Page scan failed for {domain}: {e}")
    
    # Tier 3: AI classification (only for genuinely ambiguous cases)
    ai_result = await classify_ai(domain, title, description, signals)
    if ai_result.get("is_adult") is not None:
        result.update({
            "is_adult": ai_result["is_adult"],
            "confidence": ai_result.get("confidence", 0.5),
            "method": "ai",
            "detail": ai_result.get("reason", ""),
        })
    else:
        result.update({"is_adult": None, "confidence": 0, "method": "inconclusive", "detail": "all tiers failed"})
    
    return result
