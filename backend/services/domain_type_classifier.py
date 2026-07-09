"""Deterministic domain type labels for link-source domains."""

from __future__ import annotations

import re

from ..models import Domain


DOMAIN_TYPE_TAGS = (
    "topsite",
    "directory",
    "tube",
    "blog",
    "forum",
    "news",
    "review",
    "cams",
    "escort",
)
MAX_DOMAIN_TAGS_LENGTH = 500

TYPE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("topsite", (
        r"\btop\s*(?:site|list)s?\b",
        r"\bbest\s+(?:adult\s+)?(?:cam|porn|sex|xxx).*(?:sites?|list)\b",
        r"\b(?:adult|porn|sex|xxx|cam|cams).*top\s*(?:site|list)s?\b",
    )),
    ("directory", (
        r"\bdirector(?:y|ies)\b",
        r"\bcatalog(?:ue)?\b",
        r"\baggregator\b",
        r"\blisting(?:s)?\b",
    )),
    ("tube", (
        r"\btubes?\b",
        r"\bvideos?\b",
        r"\bclips?\b",
        r"\bmovies?\b",
        r"\bpornhub\b",
        r"\bxvideos?\b",
        r"\bxnxx\b",
        r"\bxhamster\b",
        r"\bredtube\b",
        r"\byouporn\b",
    )),
    ("blog", (
        r"\bblogs?\b",
        r"\bmagazine\b",
        r"\barticles?\b",
        r"\bstories\b",
        r"\bnews\b",
    )),
    ("forum", (
        r"\bforums?\b",
        r"\bcommunity\b",
        r"\bboard\b",
    )),
    ("news", (
        r"\bnews\b",
        r"\bpress\b",
        r"\bmedia\b",
    )),
    ("review", (
        r"\breviews?\b",
        r"\bratings?\b",
        r"\bcompare\b",
        r"\bcomparison\b",
    )),
    ("cams", (
        r"\bcams?\b",
        r"\bwebcams?\b",
        r"\blive\s*cam\b",
        r"\bcamgirls?\b",
        r"\bchaturbate\b",
        r"\bstripchat\b",
    )),
    ("escort", (
        r"\bescorts?\b",
        r"\bbrothel\b",
        r"\badult\s+dating\b",
    )),
)

COMPACT_TYPE_TERMS: dict[str, tuple[str, ...]] = {
    "topsite": ("topsite", "toplist", "bestadultsites", "bestpornosites", "bestcamsites"),
    "directory": ("directory", "directories", "catalog", "catalogue", "aggregator"),
    "tube": ("tube", "video", "clip", "movie", "pornhub", "xvideos", "xnxx", "xhamster", "redtube", "youporn"),
    "blog": ("blog", "magazine", "article", "stories"),
    "forum": ("forum", "community", "board"),
    "news": ("news", "press", "media"),
    "review": ("review", "rating", "compare", "comparison"),
    "cams": ("cam", "webcam", "livecam", "camgirl", "chaturbate", "stripchat"),
    "escort": ("escort", "brothel", "adultdating"),
}


def split_tags(raw: str | None) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for tag in (raw or "").split(","):
        normalized = tag.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tags.append(normalized)
    return tags


def join_tags(tags: list[str]) -> str | None:
    kept: list[str] = []
    for tag in split_tags(",".join(tags)):
        candidate = ",".join(kept + [tag])
        if len(candidate) > MAX_DOMAIN_TAGS_LENGTH:
            break
        kept.append(tag)
    return ",".join(kept) if kept else None


def classify_domain_type(domain: Domain) -> dict:
    """Return deterministic source-type labels from domain metadata."""
    text = " ".join(
        value
        for value in (
            domain.domain,
            domain.category,
            domain.tags,
            domain.niche_tags,
            domain.notes,
        )
        if value
    ).lower()
    compact_domain = re.sub(r"[^a-z0-9]+", "", domain.domain.lower())

    matched: list[str] = []
    signals: dict[str, list[str]] = {}
    for label, patterns in TYPE_PATTERNS:
        hits = [pattern for pattern in patterns if re.search(pattern, text)]
        compact_hits = [term for term in COMPACT_TYPE_TERMS[label] if term in compact_domain]
        if hits:
            matched.append(label)
            signals[label] = hits
        elif compact_hits:
            matched.append(label)
            signals[label] = compact_hits

    if "topsite" in matched and "directory" not in matched:
        matched.append("directory")
    if domain.domain_niche == "adult" and any(t in matched for t in ("topsite", "directory")):
        matched.append("adult-directory")

    return {
        "domain": domain.domain,
        "type_tags": split_tags(",".join(matched)),
        "signals": signals,
    }


def apply_domain_type_labels(domain: Domain) -> dict:
    """Persist inferred source-type tags without removing existing custom tags."""
    verdict = classify_domain_type(domain)
    inferred = verdict["type_tags"]
    if not inferred:
        return {**verdict, "changed": False}

    existing = [
        tag for tag in split_tags(domain.tags)
        if tag not in DOMAIN_TYPE_TAGS and tag != "adult-directory"
    ]
    next_tags = join_tags(existing + inferred)
    changed = domain.tags != next_tags
    domain.tags = next_tags

    if not domain.category and inferred:
        domain.category = inferred[0]
        changed = True

    return {**verdict, "changed": changed}
