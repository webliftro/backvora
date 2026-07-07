"""
Adult site classifier — shared verdict service.

Scoring tiers:
1. Domain keyword/TLD scan (instant, free)
2. Signal scoring: homepage title/meta, anchor texts (instant, free)
3. Page content scan (one HTTP fetch, only for ambiguous uncached domains)
4. AI classification (Claude, only for ambiguous cases, needs API key)

Manual overrides (DomainAdultOverride, keyed by root domain) win over every
tier and are checked before any scoring or network fetch.

Verdicts are cached on Domain (domain_niche/adult_* columns); cached domains
are not re-fetched unless force refresh is requested.
"""

import asyncio
import re
import logging
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from ..models import Domain, DomainAdultOverride
from ..utils.domains import extract_root_domain, normalize_domain

log = logging.getLogger(__name__)

# Verdict values stored in Domain.domain_niche
NICHE_ADULT = "adult"
NICHE_NON_ADULT = "non_adult"
NICHE_UNKNOWN = "unknown"

# Verdict method meaning "local signal scoring only — homepage never fetched".
# Unlike every other cached method, it stays eligible for the import-time
# fetch pass, so capped/deferred domains get their one fetch on a later import.
METHOD_SIGNALS = "signals"

# Signal score at/above which a domain is classified adult
ADULT_SCORE_THRESHOLD = 40

# Import-time homepage fallback: bounded so bulk imports can never stampede
# remote sites or blow past proxy timeouts. Domains beyond the per-import cap
# keep their signals-only verdict and are retried on the next import.
IMPORT_FETCH_CONCURRENCY = 5
IMPORT_FETCH_TIMEOUT = 20
IMPORT_FETCH_MAX = 25

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
    "adultswim",
}

# Generic/ambiguous terms that must not mark a domain adult on their own
# when found in anchor text (weight 10 vs 20 for explicit terms)
WEAK_ANCHOR_TERMS = {
    "adult", "sex", "sexy", "cam", "cams", "tube", "dating",
    "gay", "trans", "nude", "naked", "ass", "tit", "dick", "cock",
}

ANCHOR_TERM_WEIGHT_STRONG = 20
ANCHOR_TERM_WEIGHT_WEAK = 10
ANCHOR_SCORE_CAP = 60
TITLE_KEYWORD_WEIGHT = 20
TITLE_KEYWORD_CAP = 3
META_DESC_WEIGHT = 15

# Explicit title/meta terms that classify adult immediately (word-boundary
# matched, so "Popcorn" never trips "porn"). Generic terms like "sex"/"cam"
# only contribute to the score.
STRONG_TITLE_TERMS = {
    "porn", "porno", "xxx", "hentai", "escort", "milf", "fetish", "bdsm",
    "live sex", "free porn", "watch porn", "nsfw", "rule34", "camgirl",
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


def score_anchor_texts(anchor_texts: list[str]) -> tuple[int, list[str]]:
    """Score adult terms across anchor texts (whole-word matches only).

    Explicit terms weigh 20, generic/ambiguous terms weigh 10, so one weak
    generic term alone can never reach the adult threshold.
    """
    score = 0
    signals = []
    lowered = [(a or "").lower() for a in anchor_texts if a]
    for kw in ADULT_KEYWORDS:
        pattern = r"\b" + re.escape(kw) + r"(?:s|es)?\b"
        if any(re.search(pattern, a) for a in lowered):
            weight = ANCHOR_TERM_WEIGHT_WEAK if kw in WEAK_ANCHOR_TERMS else ANCHOR_TERM_WEIGHT_STRONG
            score += weight
            signals.append(f"anchor:{kw}")
    return min(score, ANCHOR_SCORE_CAP), signals


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
    if score >= ADULT_SCORE_THRESHOLD:
        return {"is_adult": True, "confidence": min(score / 100, 1.0), "signals": signals, "score": score}
    elif score == 0:
        return {"is_adult": False, "confidence": 0.7, "signals": ["no_adult_signals"], "score": 0}
    else:
        return {"is_adult": None, "confidence": score / 100, "signals": signals, "score": score}


def _strong_title_term(text: str) -> Optional[str]:
    """Return the first strong explicit term found in title/meta text, if any."""
    lowered = (text or "").lower()
    for term in STRONG_TITLE_TERMS:
        if re.search(r"\b" + re.escape(term) + r"\b", lowered):
            return term
    return None


def _score_title_meta(title: str, meta_description: str) -> tuple[int, list[str]]:
    """Score adult keywords in a bare title/meta description (no HTML)."""
    score = 0
    signals = []
    if title:
        title_lower = title.lower()
        hits = [kw for kw in ADULT_TITLE_KEYWORDS if kw in title_lower]
        for kw in hits[:TITLE_KEYWORD_CAP]:
            signals.append(f"title:{kw}")
            score += TITLE_KEYWORD_WEIGHT
    if meta_description:
        desc_lower = meta_description.lower()
        adult_count = sum(1 for kw in ADULT_TITLE_KEYWORDS if kw in desc_lower)
        if adult_count >= 2:
            signals.append(f"meta_desc:{adult_count}_keywords")
            score += META_DESC_WEIGHT
    return score, signals


def _verdict(domain: str, niche: str, confidence: float, method: str, detail: str) -> dict:
    """Build the structured verdict dict every classification path returns."""
    is_adult = {NICHE_ADULT: True, NICHE_NON_ADULT: False}.get(niche)
    return {
        "domain": domain,
        "domain_niche": niche,
        "is_adult": is_adult,
        "confidence": confidence,
        "method": method,
        "detail": detail,
    }


def classify_signals(
    domain: str,
    *,
    title: str = "",
    meta_description: str = "",
    html: str = "",
    anchor_texts: Optional[list[str]] = None,
) -> dict:
    """Score all locally-available signals — no network, no AI.

    Strong domain/TLD signals classify adult immediately; title/meta and
    anchor text scores combine and classify adult at ADULT_SCORE_THRESHOLD.
    non_adult only comes from a clean fetched page; everything else stays
    unknown for the fetch/AI tiers.
    """
    keyword_result = classify_domain_keyword(domain)
    if keyword_result is True:
        return _verdict(domain, NICHE_ADULT, 0.95, "domain_keyword", "adult keyword in domain")

    score = 0
    signals = []
    page_clean = False

    if html:
        page = classify_page_content(html)
        if page["is_adult"] is True:
            return _verdict(domain, NICHE_ADULT, page["confidence"], "page_scan", ", ".join(page["signals"]))
        # Don't trust "not adult" if page is very short (might be a redirect/stub)
        if page["is_adult"] is False and page["confidence"] >= 0.7 and len(html) > 2000:
            page_clean = True
        score += page.get("score", 0)
        if page["is_adult"] is None:
            signals.extend(page["signals"])
    else:
        strong = _strong_title_term(title) or _strong_title_term(meta_description)
        if strong:
            return _verdict(domain, NICHE_ADULT, 0.85, "title_meta", f"strong adult term '{strong}' in title/meta")
        tm_score, tm_signals = _score_title_meta(title, meta_description)
        score += tm_score
        signals.extend(tm_signals)

    if anchor_texts:
        anchor_score, anchor_signals = score_anchor_texts(anchor_texts)
        score += anchor_score
        signals.extend(anchor_signals)

    if score >= ADULT_SCORE_THRESHOLD:
        return _verdict(domain, NICHE_ADULT, min(score / 100, 0.95), "signal_score", ", ".join(signals))

    if page_clean and score == 0:
        return _verdict(domain, NICHE_NON_ADULT, 0.7, "page_scan", "no adult signals on page")

    detail = ", ".join(signals) if signals else "no conclusive signals"
    if keyword_result is None and any(fp in domain.lower().split(".")[0] for fp in FALSE_POSITIVES):
        detail = f"known false-positive domain term; {detail}"
    return _verdict(domain, NICHE_UNKNOWN, score / 100 if score else 0, METHOD_SIGNALS, detail)


async def _fetch_homepage(domain: str) -> Optional[dict]:
    """Fetch https://<domain> homepage. Returns html/title/description/status,
    or None on network failure. Never raises."""
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
            return {"html": html, "title": title, "description": description, "status_code": resp.status_code}
    except Exception as e:
        log.warning(f"Page scan failed for {domain}: {e}")
        return None


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


async def classify_domain(
    domain: str,
    *,
    title: str = "",
    meta_description: str = "",
    anchor_texts: Optional[list[str]] = None,
    allow_fetch: bool = True,
    allow_ai: bool = True,
) -> dict:
    """Full classification pipeline for one domain with optional context.

    Returns dict with: domain, domain_niche, is_adult, confidence, method, detail
    """
    # Tier 1+2: local signals (domain keyword, provided title/meta, anchors)
    result = classify_signals(domain, title=title, meta_description=meta_description, anchor_texts=anchor_texts)
    if result["domain_niche"] != NICHE_UNKNOWN:
        return result

    fetched_title = title
    fetched_description = meta_description
    fetch_failed = False
    signals = []

    # Tier 3: one homepage fetch for ambiguous domains
    if allow_fetch:
        page = await _fetch_homepage(domain)
        if page is None:
            fetch_failed = True
        else:
            fetched_title = page["title"] or title
            fetched_description = page["description"] or meta_description
            if page["status_code"] == 200:
                result = classify_signals(domain, html=page["html"], anchor_texts=anchor_texts)
                if result["domain_niche"] != NICHE_UNKNOWN:
                    return result
                signals = [s for s in result["detail"].split(", ") if s and s != "no conclusive signals"]
            else:
                # Non-200 (likely CF block) — check title for adult signals anyway
                for kw in ADULT_TITLE_KEYWORDS:
                    if kw in fetched_title.lower():
                        return _verdict(
                            domain, NICHE_ADULT, 0.8, "page_scan_title",
                            f"title contains '{kw}' (page was CF-blocked)",
                        )

    # Tier 4: AI classification (only for genuinely ambiguous cases)
    if allow_ai:
        ai_result = await classify_ai(domain, fetched_title, fetched_description, signals)
        if ai_result.get("is_adult") is not None:
            niche = NICHE_ADULT if ai_result["is_adult"] else NICHE_NON_ADULT
            return _verdict(domain, niche, ai_result.get("confidence", 0.5), "ai", ai_result.get("reason", ""))

    detail = "all tiers inconclusive"
    if fetch_failed:
        detail = "homepage fetch failed; " + detail
    return _verdict(domain, NICHE_UNKNOWN, 0, "inconclusive", detail)


# ── DB-aware helpers: overrides, cached verdicts, persistence ──


def load_adult_overrides(db: Session) -> dict[str, DomainAdultOverride]:
    """Preload all active overrides keyed by root domain (for import loops)."""
    rows = db.query(DomainAdultOverride).filter(DomainAdultOverride.deleted_at.is_(None)).all()
    return {row.root_domain: row for row in rows}


def find_adult_override(overrides: dict[str, DomainAdultOverride], domain: str) -> Optional[DomainAdultOverride]:
    return overrides.get(extract_root_domain(normalize_domain(domain)))


def get_adult_override(db: Session, domain: str) -> Optional[DomainAdultOverride]:
    root = extract_root_domain(normalize_domain(domain))
    return db.query(DomainAdultOverride).filter(
        DomainAdultOverride.root_domain == root,
        DomainAdultOverride.deleted_at.is_(None),
    ).first()


def verdict_from_override(override: DomainAdultOverride, domain: str) -> dict:
    detail = override.note or f"manual override ({override.verdict})"
    return _verdict(domain, override.verdict, 1.0, "override", detail)


def apply_verdict_to_domain(domain_obj: Domain, verdict: dict) -> None:
    """Persist a verdict onto the Domain row (caller commits).

    is_adult mirrors the verdict for compatibility; unknown keeps the
    existing boolean untouched (new rows keep the historical True default)
    so an ambiguous verdict never silently hides a domain from adult views.
    """
    domain_obj.domain_niche = verdict["domain_niche"]
    domain_obj.adult_method = verdict.get("method")
    domain_obj.adult_confidence = verdict.get("confidence")
    domain_obj.adult_detail = verdict.get("detail")
    domain_obj.adult_classified_at = datetime.utcnow()
    if verdict.get("is_adult") is not None:
        domain_obj.is_adult = verdict["is_adult"]


def cached_verdict(domain_obj: Domain) -> dict:
    return {
        "domain": domain_obj.domain,
        "domain_niche": domain_obj.domain_niche,
        "is_adult": domain_obj.is_adult,
        "confidence": domain_obj.adult_confidence or 0,
        "method": domain_obj.adult_method or "cached",
        "detail": domain_obj.adult_detail or "",
        "cached": True,
    }


def classify_new_domain_for_import(
    domain_name: str,
    *,
    anchor_texts: Optional[list[str]] = None,
    overrides: dict[str, DomainAdultOverride],
) -> dict:
    """Phase-1 import verdict: override, else local signals only (no network).

    Ambiguous domains come back `unknown` with method `signals` — the import
    loop should hand those to run_import_fetch_pass for their one bounded
    homepage fetch after the rows are processed.
    """
    override = find_adult_override(overrides, domain_name)
    if override:
        return verdict_from_override(override, domain_name)
    return classify_signals(domain_name, anchor_texts=anchor_texts)


def apply_import_verdict(
    domain_obj: Domain,
    overrides: dict[str, DomainAdultOverride],
    *,
    anchor_texts: Optional[list[str]] = None,
) -> bool:
    """Phase-1 import verdict applied to a new or stored domain (no network).

    Overrides always win, even over a cached verdict. Conclusive or
    already-fetched cached verdicts are left untouched (AC6: never re-fetch
    on import). Uncached domains and signals-only unknowns get a fresh
    signal verdict. Returns True when the domain still needs the bounded
    homepage fetch pass (ambiguous, uncached-or-signals-only, no override).
    """
    override = find_adult_override(overrides, domain_obj.domain)
    if override:
        apply_verdict_to_domain(domain_obj, verdict_from_override(override, domain_obj.domain))
        return False
    if domain_obj.domain_niche and not (
        domain_obj.domain_niche == NICHE_UNKNOWN and domain_obj.adult_method == METHOD_SIGNALS
    ):
        return False
    verdict = classify_signals(domain_obj.domain, anchor_texts=anchor_texts)
    apply_verdict_to_domain(domain_obj, verdict)
    return verdict["domain_niche"] == NICHE_UNKNOWN


async def run_import_fetch_pass(
    candidates: list[tuple[Domain, Optional[list[str]]]],
) -> dict:
    """Phase-2 import verdict: one bounded homepage fetch per ambiguous domain.

    Takes (domain, anchor_texts) pairs left ambiguous by apply_import_verdict /
    classify_new_domain_for_import. At most IMPORT_FETCH_MAX domains are
    fetched per import (IMPORT_FETCH_CONCURRENCY concurrent, per-domain
    timeout); never calls AI. Fetched verdicts — including fetch failures and
    timeouts, persisted as `unknown` with a reason — are cached so a domain is
    only ever fetched once. Deferred domains keep their signals-only verdict
    and stay eligible on the next import. Caller commits.

    Returns {"fetched", "resolved", "deferred"} counts for the import response.
    """
    unique: list[tuple[Domain, Optional[list[str]]]] = []
    seen: set[str] = set()
    for domain_obj, anchors in candidates:
        if domain_obj.domain in seen:
            continue
        seen.add(domain_obj.domain)
        unique.append((domain_obj, anchors))

    to_fetch = unique[:IMPORT_FETCH_MAX]
    deferred = len(unique) - len(to_fetch)
    if deferred:
        log.info(f"Import fetch pass: {deferred} ambiguous domain(s) deferred to a later import (cap {IMPORT_FETCH_MAX})")
    if not to_fetch:
        return {"fetched": 0, "resolved": 0, "deferred": deferred}

    semaphore = asyncio.Semaphore(IMPORT_FETCH_CONCURRENCY)

    async def classify_one(domain_obj: Domain, anchors: Optional[list[str]]) -> dict:
        async with semaphore:
            try:
                verdict = await asyncio.wait_for(
                    classify_domain(domain_obj.domain, anchor_texts=anchors, allow_ai=False),
                    timeout=IMPORT_FETCH_TIMEOUT,
                )
            except asyncio.TimeoutError:
                verdict = _verdict(
                    domain_obj.domain, NICHE_UNKNOWN, 0, "inconclusive",
                    "homepage scan timed out during import",
                )
        apply_verdict_to_domain(domain_obj, verdict)
        return verdict

    verdicts = await asyncio.gather(*[classify_one(d, a) for d, a in to_fetch])
    resolved = sum(1 for v in verdicts if v["domain_niche"] != NICHE_UNKNOWN)
    return {"fetched": len(to_fetch), "resolved": resolved, "deferred": deferred}


async def classify_domain_with_cache(
    db: Session,
    domain_obj: Domain,
    *,
    anchor_texts: Optional[list[str]] = None,
    force_refresh: bool = False,
    allow_fetch: bool = True,
) -> dict:
    """Classify a stored domain: override > cached verdict > full pipeline.

    Overrides win even on force refresh. Cached verdicts skip the network
    unless force_refresh. The verdict is persisted; caller commits.
    """
    override = get_adult_override(db, domain_obj.domain)
    if override:
        verdict = verdict_from_override(override, domain_obj.domain)
        apply_verdict_to_domain(domain_obj, verdict)
        return verdict

    signals_only_unknown = (
        domain_obj.domain_niche == NICHE_UNKNOWN
        and domain_obj.adult_method == METHOD_SIGNALS
    )
    if domain_obj.domain_niche and not force_refresh and not signals_only_unknown:
        return cached_verdict(domain_obj)

    verdict = await classify_domain(domain_obj.domain, anchor_texts=anchor_texts, allow_fetch=allow_fetch)
    apply_verdict_to_domain(domain_obj, verdict)
    return verdict


def set_adult_override(db: Session, domain: str, verdict: str, note: Optional[str] = None) -> tuple[DomainAdultOverride, int]:
    """Upsert a manual override for the domain's root and apply it to all
    stored domains sharing that root. Returns (override, affected_count).
    Caller commits."""
    if verdict not in (NICHE_ADULT, NICHE_NON_ADULT):
        raise ValueError(f"Override verdict must be '{NICHE_ADULT}' or '{NICHE_NON_ADULT}', got {verdict!r}")

    root = extract_root_domain(normalize_domain(domain))
    override = db.query(DomainAdultOverride).filter(DomainAdultOverride.root_domain == root).first()
    if override:
        override.verdict = verdict
        override.note = note
        override.deleted_at = None
    else:
        override = DomainAdultOverride(root_domain=root, verdict=verdict, note=note)
        db.add(override)

    affected = 0
    for d in _domains_with_root(db, root):
        apply_verdict_to_domain(d, verdict_from_override(override, d.domain))
        affected += 1
    return override, affected


def clear_adult_override(db: Session, domain: str) -> int:
    """Remove the override for the domain's root and reset the cached verdict
    on matching domains so the next classification re-runs the classifier.
    Returns affected domain count. Caller commits."""
    root = extract_root_domain(normalize_domain(domain))
    override = db.query(DomainAdultOverride).filter(
        DomainAdultOverride.root_domain == root,
        DomainAdultOverride.deleted_at.is_(None),
    ).first()
    if not override:
        return 0

    override.deleted_at = datetime.utcnow()
    affected = 0
    for d in _domains_with_root(db, root):
        d.domain_niche = None
        d.adult_method = None
        d.adult_confidence = None
        d.adult_detail = "override cleared; pending reclassification"
        d.adult_classified_at = None
        affected += 1
    return affected


def _domains_with_root(db: Session, root: str) -> list[Domain]:
    candidates = db.query(Domain).filter(
        Domain.deleted_at.is_(None),
        Domain.domain.like(f"%{root}"),
    ).all()
    return [d for d in candidates if extract_root_domain(d.domain) == root]
