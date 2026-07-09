"""Domain source-type label tests."""

import pytest

from backend.models import Domain
from backend.routers.domains import ClassifyTypeRequest, classify_domain_types
from backend.services.domain_type_classifier import apply_domain_type_labels, classify_domain_type


def test_domain_type_classifier_detects_common_adult_source_types():
    topsite = Domain(
        domain="adulttoplist.example",
        domain_niche="adult",
        category="Adult Toplist",
    )
    tube = Domain(domain="redtube-example.com")
    blog = Domain(domain="example.com", category="Adult Blog")

    assert classify_domain_type(topsite)["type_tags"] == ["topsite", "directory", "adult-directory"]
    assert classify_domain_type(tube)["type_tags"] == ["tube"]
    assert classify_domain_type(blog)["type_tags"] == ["blog"]


def test_apply_domain_type_labels_preserves_custom_tags():
    domain = Domain(
        domain="bestadultsites.example",
        domain_niche="adult",
        tags="premium,old-topsite",
    )

    result = apply_domain_type_labels(domain)

    assert result["changed"] is True
    assert domain.tags == "premium,old-topsite,topsite,directory,adult-directory"
    assert domain.category == "topsite"


@pytest.mark.asyncio
async def test_classify_domain_types_endpoint_persists_labels(db):
    domain = Domain(
        id="dom-1",
        domain="adultdirectory.example",
        domain_niche="adult",
        tags="premium",
    )
    unmatched = Domain(id="dom-2", domain="plainexample.com")
    db.add_all([domain, unmatched])
    db.commit()

    result = await classify_domain_types(ClassifyTypeRequest(domain_ids=[domain.id, unmatched.id]), db=db)

    db.refresh(domain)
    assert result["scanned"] == 2
    assert result["updated"] == 1
    assert result["unmatched"] == 1
    assert domain.tags == "premium,directory,adult-directory"
