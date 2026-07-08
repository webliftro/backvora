"""Shared domain filtering helpers for campaign planning and autopilot."""

from __future__ import annotations

from sqlalchemy import and_, or_

from ..models import Domain


ADULT_CONCEPT_ALIASES = {"adult", "porn", "xxx", "nsfw"}
DIRECTORY_CONCEPT_ALIASES = {
    "aggregator",
    "catalog",
    "catalogue",
    "directories",
    "directory",
    "toplist",
}

ADULT_TERMS = ("adult", "porn", "xxx", "nsfw", "sex")
DIRECTORY_METADATA_TERMS = (
    "aggregator",
    "catalog",
    "catalogue",
    "directories",
    "directory",
    "toplist",
    "top list",
)
DIRECTORY_DOMAIN_TERMS = (
    "aggregator",
    "catalog",
    "catalogue",
    "directories",
    "directory",
    "toplist",
)
ADULT_DIRECTORY_DOMAIN_PREFIXES = (
    "adult",
    "cam",
    "cams",
    "fetish",
    "porn",
    "sex",
    "tube",
)


def parse_filter_concepts(raw_tags: str | None) -> list[str]:
    """Normalize comma-separated campaign filters while preserving order."""
    concepts: list[str] = []
    seen: set[str] = set()
    for tag in (raw_tags or "").split(","):
        concept = tag.strip().lower()
        if not concept or concept in seen:
            continue
        seen.add(concept)
        concepts.append(concept)
    return concepts


def _field_term_conditions(term: str):
    pattern = f"%{term}%"
    return (
        Domain.domain.ilike(pattern),
        Domain.category.ilike(pattern),
        Domain.tags.ilike(pattern),
        Domain.niche_tags.ilike(pattern),
    )


def domain_concept_condition(concept: str):
    """Build a SQLAlchemy condition for one campaign filter concept."""
    normalized = concept.strip().lower()
    if normalized in ADULT_CONCEPT_ALIASES:
        adult_text_conditions = []
        for term in ADULT_TERMS:
            adult_text_conditions.extend(_field_term_conditions(term))
        return or_(
            Domain.domain_niche == "adult",
            and_(
                or_(Domain.domain_niche.is_(None), Domain.domain_niche == "unknown"),
                or_(*adult_text_conditions),
            ),
        )

    if normalized in DIRECTORY_CONCEPT_ALIASES:
        directory_conditions = []
        for term in DIRECTORY_METADATA_TERMS:
            pattern = f"%{term}%"
            directory_conditions.extend((
                Domain.category.ilike(pattern),
                Domain.tags.ilike(pattern),
                Domain.niche_tags.ilike(pattern),
            ))
        for term in DIRECTORY_DOMAIN_TERMS:
            directory_conditions.append(Domain.domain.ilike(f"%{term}%"))
        for prefix in ADULT_DIRECTORY_DOMAIN_PREFIXES:
            directory_conditions.append(and_(
                Domain.domain.ilike(f"%{prefix}%"),
                Domain.domain.ilike("%list%"),
            ))
            directory_conditions.append(and_(
                Domain.domain.ilike(f"%{prefix}%"),
                Domain.domain.ilike("%sites%"),
            ))
        return or_(*directory_conditions)

    return or_(
        Domain.niche_tags.ilike(f"%{normalized}%"),
        Domain.tags.ilike(f"%{normalized}%"),
        Domain.category.ilike(f"%{normalized}%"),
    )


def apply_domain_concept_filters(query, raw_tags: str | None):
    """Apply campaign domain concepts.

    Legacy comma filters matched any tag. The adult-directory phrase is a
    stricter product concept: adult AND toplist/aggregator/directory.
    """
    concepts = parse_filter_concepts(raw_tags)
    has_adult = any(concept in ADULT_CONCEPT_ALIASES for concept in concepts)
    has_directory = any(concept in DIRECTORY_CONCEPT_ALIASES for concept in concepts)
    required: set[str] = set()

    if has_adult and has_directory:
        query = query.filter(domain_concept_condition("adult"))
        query = query.filter(domain_concept_condition("directory"))
        required.update({"adult", "directory"})

    optional_conditions = [
        domain_concept_condition(concept)
        for concept in concepts
        if concept not in required
    ]
    if optional_conditions:
        query = query.filter(or_(*optional_conditions))
    return query
