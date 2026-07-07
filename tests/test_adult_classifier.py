"""Adult domain autofilter tests — classifier scoring, overrides, caching,
import wiring, the bounded import fetch pass, and the classify-adult
endpoint. All network calls mocked."""

import asyncio
import io
import os
import sys
import importlib.util
from pathlib import Path

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.models import Domain, DomainAdultOverride, Backlink
from backend.services import adult_classifier
from backend.services.adult_classifier import (
    NICHE_ADULT,
    NICHE_NON_ADULT,
    NICHE_UNKNOWN,
    classify_signals,
    classify_new_domain_for_import,
    classify_domain_with_cache,
    load_adult_overrides,
    set_adult_override,
    clear_adult_override,
    score_anchor_texts,
)

ROOT = Path(__file__).resolve().parents[1]

# Long enough (>2000 chars) that a clean page scan is trusted as non_adult
ADULT_HTML = (
    "<html><title>Live Sex Cams 18+</title>"
    "<body>18+ only enter to watch</body></html>" + "x" * 2500
)
CLEAN_HTML = (
    "<html><title>Gardening Weekly</title>"
    "<body>Flowers, soil, and compost tips</body></html>" + "x" * 2500
)


def _page_fetch(html, title="", description=""):
    """Build a _fetch_homepage stand-in returning a successful page."""
    async def fake_fetch(domain):
        return {"html": html, "title": title, "description": description, "status_code": 200}
    return fake_fetch


@pytest.fixture
def no_network(monkeypatch):
    """Fail loudly if any real HTTP is attempted; track homepage fetches."""
    calls = []

    async def fake_fetch(domain):
        calls.append(domain)
        return None

    async def fake_ai(domain, title="", description="", signals=None):
        return {"is_adult": None, "confidence": 0, "reason": "mocked"}

    monkeypatch.setattr(adult_classifier, "_fetch_homepage", fake_fetch)
    monkeypatch.setattr(adult_classifier, "classify_ai", fake_ai)
    return calls


class TestSignalScoring:
    def test_domain_keyword_adult_hit(self):
        result = classify_signals("pornhub-clips.com")
        assert result["domain_niche"] == NICHE_ADULT
        assert result["is_adult"] is True
        assert result["method"] == "domain_keyword"
        assert result["confidence"] >= 0.9

    def test_adult_tld_hit(self):
        result = classify_signals("videos.xxx")
        assert result["domain_niche"] == NICHE_ADULT

    def test_adultswim_false_positive_stays_ambiguous(self):
        result = classify_signals("adultswim.com")
        assert result["domain_niche"] == NICHE_UNKNOWN
        assert result["is_adult"] is None

    def test_neutral_domain_is_unknown_not_adult(self):
        result = classify_signals("gardeningtips.com")
        assert result["domain_niche"] == NICHE_UNKNOWN

    def test_strong_title_classifies_adult(self):
        result = classify_signals("example.com", title="Free Porn Videos - Watch Now")
        assert result["domain_niche"] == NICHE_ADULT
        assert result["method"] == "title_meta"

    def test_popcorn_title_is_not_porn(self):
        result = classify_signals("example.com", title="Best Popcorn Recipes")
        assert result["domain_niche"] == NICHE_UNKNOWN

    def test_meta_description_adult_hit(self):
        result = classify_signals("example.com", meta_description="Watch free porn and xxx movies")
        assert result["domain_niche"] == NICHE_ADULT

    def test_html_page_scan_adult(self):
        html = "<html><title>Live Sex Cams</title><body>18+ only enter</body></html>" + "x" * 2500
        result = classify_signals("example.com", html=html)
        assert result["domain_niche"] == NICHE_ADULT
        assert result["method"] == "page_scan"

    def test_clean_long_page_is_non_adult(self):
        html = "<html><title>Gardening Weekly</title><body>Flowers and soil tips</body></html>" + "x" * 2500
        result = classify_signals("example.com", html=html)
        assert result["domain_niche"] == NICHE_NON_ADULT
        assert result["is_adult"] is False


class TestAnchorScoring:
    def test_one_weak_generic_term_does_not_mark_adult(self):
        result = classify_signals("example.com", anchor_texts=["adult education courses"])
        assert result["domain_niche"] == NICHE_UNKNOWN

    def test_two_strong_terms_mark_adult(self):
        result = classify_signals("example.com", anchor_texts=["free porn videos", "xxx movies here"])
        assert result["domain_niche"] == NICHE_ADULT
        assert "anchor:" in result["detail"]

    def test_word_boundary_avoids_false_positives(self):
        score, signals = score_anchor_texts(["classic analytics for Sussex campus"])
        assert score == 0
        assert signals == []

    def test_anchor_contributes_to_title_score(self):
        # one title keyword (20) + one strong anchor term (20) crosses threshold
        result = classify_signals("example.com", title="live sex chat rooms", anchor_texts=["escort services"])
        assert result["domain_niche"] == NICHE_ADULT


class TestOverrides:
    def test_adultswim_non_adult_override_wins(self, db):
        set_adult_override(db, "adultswim.com", NICHE_NON_ADULT, note="cartoon network brand")
        db.commit()
        overrides = load_adult_overrides(db)
        result = classify_new_domain_for_import("adultswim.com", overrides=overrides)
        assert result["domain_niche"] == NICHE_NON_ADULT
        assert result["is_adult"] is False
        assert result["method"] == "override"

    def test_override_wins_over_adult_keyword(self, db):
        set_adult_override(db, "pornhub.com", NICHE_NON_ADULT)
        db.commit()
        overrides = load_adult_overrides(db)
        result = classify_new_domain_for_import("pornhub.com", overrides=overrides)
        assert result["domain_niche"] == NICHE_NON_ADULT

    def test_override_matches_subdomain_via_root(self, db):
        set_adult_override(db, "adultswim.com", NICHE_NON_ADULT)
        db.commit()
        overrides = load_adult_overrides(db)
        result = classify_new_domain_for_import("blog.adultswim.com", overrides=overrides)
        assert result["domain_niche"] == NICHE_NON_ADULT

    def test_set_override_applies_to_stored_domains(self, db):
        d = Domain(id="d-ov1", domain="adultswim.com")
        db.add(d)
        db.commit()
        _, affected = set_adult_override(db, "adultswim.com", NICHE_NON_ADULT)
        db.commit()
        assert affected == 1
        assert d.domain_niche == NICHE_NON_ADULT
        assert d.is_adult is False
        assert d.adult_method == "override"
        assert d.is_adult_overridden is True

    def test_clear_override_resets_cached_verdict(self, db):
        d = Domain(id="d-ov2", domain="adultswim.com")
        db.add(d)
        db.commit()
        set_adult_override(db, "adultswim.com", NICHE_NON_ADULT)
        db.commit()
        affected = clear_adult_override(db, "adultswim.com")
        db.commit()
        assert affected == 1
        assert d.domain_niche is None
        assert d.adult_method is None
        assert d.is_adult_overridden is False
        assert load_adult_overrides(db) == {}

    @pytest.mark.asyncio
    async def test_force_refresh_does_not_bypass_override(self, db, no_network):
        d = Domain(id="d-ov3", domain="adultswim.com")
        db.add(d)
        db.commit()
        set_adult_override(db, "adultswim.com", NICHE_NON_ADULT)
        db.commit()
        result = await classify_domain_with_cache(db, d, force_refresh=True)
        assert result["method"] == "override"
        assert result["domain_niche"] == NICHE_NON_ADULT
        assert no_network == []  # override checked before any fetch


class TestCachingAndFetch:
    @pytest.mark.asyncio
    async def test_fetch_only_for_ambiguous_uncached(self, db, no_network):
        keyword_adult = Domain(id="d-c1", domain="pornhub-clips.com")
        ambiguous = Domain(id="d-c2", domain="gardeningtips.com")
        db.add_all([keyword_adult, ambiguous])
        db.commit()

        await classify_domain_with_cache(db, keyword_adult)
        assert no_network == []  # strong keyword verdict → no fetch

        await classify_domain_with_cache(db, ambiguous)
        assert no_network == ["gardeningtips.com"]  # ambiguous + uncached → one fetch

    @pytest.mark.asyncio
    async def test_cached_verdict_skips_fetch(self, db, no_network):
        d = Domain(id="d-c3", domain="gardeningtips.com", domain_niche=NICHE_NON_ADULT,
                   is_adult=False, adult_method="page_scan", adult_confidence=0.7)
        db.add(d)
        db.commit()
        result = await classify_domain_with_cache(db, d)
        assert no_network == []
        assert result["cached"] is True
        assert result["domain_niche"] == NICHE_NON_ADULT

    @pytest.mark.asyncio
    async def test_signals_only_unknown_is_not_treated_as_cached(self, db, no_network):
        d = Domain(id="d-c6", domain="gardeningtips.com", domain_niche=NICHE_UNKNOWN,
                   adult_method=adult_classifier.METHOD_SIGNALS, adult_confidence=0)
        db.add(d)
        db.commit()
        result = await classify_domain_with_cache(db, d)
        assert no_network == ["gardeningtips.com"]
        assert result["domain_niche"] == NICHE_UNKNOWN
        assert d.adult_method == "inconclusive"

    @pytest.mark.asyncio
    async def test_force_refresh_reclassifies(self, db, no_network):
        d = Domain(id="d-c4", domain="gardeningtips.com", domain_niche=NICHE_ADULT,
                   is_adult=True, adult_method="signal_score")
        db.add(d)
        db.commit()
        result = await classify_domain_with_cache(db, d, force_refresh=True)
        assert no_network == ["gardeningtips.com"]
        assert result["domain_niche"] == NICHE_UNKNOWN  # mocked fetch fails → unknown, not crash
        assert "fetch failed" in result["detail"]

    @pytest.mark.asyncio
    async def test_fetch_failure_persists_unknown_with_reason(self, db, no_network):
        d = Domain(id="d-c5", domain="gardeningtips.com")
        db.add(d)
        db.commit()
        await classify_domain_with_cache(db, d)
        assert d.domain_niche == NICHE_UNKNOWN
        assert d.adult_method == "inconclusive"
        assert d.adult_classified_at is not None


class TestImportClassification:
    @pytest.mark.asyncio
    async def test_csv_import_classifies_and_filters(self, db, no_network):
        from backend.routers.import_export import import_domains_csv

        set_adult_override(db, "flowershop.com", NICHE_NON_ADULT, note="florist")
        db.commit()

        csv_text = "domain\nsexcams-hub.com\ngardeningtips.com\nflowershop.com\n"
        upload = UploadFile(io.BytesIO(csv_text.encode()), filename="domains.csv")
        result = await import_domains_csv(
            file=upload, min_traffic=None, max_traffic=None, min_dr=None,
            max_dr=None, skip_non_adult=True, db=db,
        )

        assert result["added"] == 2  # adult + unknown imported
        assert result["filtered_out"] == 1  # overridden non-adult dropped
        # only the ambiguous domain got its one homepage fetch
        assert no_network == ["gardeningtips.com"]
        assert result["adult_scan"] == {"fetched": 1, "resolved": 0, "deferred": 0}

        adult = db.query(Domain).filter(Domain.domain == "sexcams-hub.com").first()
        assert adult.domain_niche == NICHE_ADULT
        assert adult.is_adult is True
        assert adult.adult_classified_at is not None

        unknown = db.query(Domain).filter(Domain.domain == "gardeningtips.com").first()
        assert unknown.domain_niche == NICHE_UNKNOWN  # fetch failed → cached unknown
        assert unknown.adult_method == "inconclusive"
        assert unknown.is_adult is True  # unknown keeps historical default

        assert db.query(Domain).filter(Domain.domain == "flowershop.com").first() is None

    @pytest.mark.asyncio
    async def test_bulk_import_persists_verdicts(self, db, no_network):
        from backend.routers.domains import bulk_import_domains

        result = await bulk_import_domains(
            domains=["https://www.pornhub-clips.com/page", "gardeningtips.com"],
            is_competitor=False, db=db,
        )
        assert result["added"] == 2
        d = db.query(Domain).filter(Domain.domain == "pornhub-clips.com").first()
        assert d.domain_niche == NICHE_ADULT
        # only the ambiguous domain got its one homepage fetch
        assert no_network == ["gardeningtips.com"]

    def test_apply_import_verdict_uses_anchor_and_respects_cache(self, db, no_network):
        overrides = load_adult_overrides(db)

        fresh = Domain(id="d-i1", domain="myblog.com")
        needs_fetch = adult_classifier.apply_import_verdict(
            fresh, overrides, anchor_texts=["free porn videos xxx cams"])
        assert needs_fetch is False  # anchors were conclusive
        assert fresh.domain_niche == NICHE_ADULT
        assert "anchor:" in fresh.adult_detail

        cached = Domain(id="d-i2", domain="cachedsite.com", domain_niche=NICHE_NON_ADULT,
                        is_adult=False, adult_method="page_scan")
        assert adult_classifier.apply_import_verdict(
            cached, overrides, anchor_texts=["free porn videos xxx cams"]) is False
        assert cached.domain_niche == NICHE_NON_ADULT  # cached fetched verdict untouched

        ambiguous = Domain(id="d-i3", domain="plainblog.com")
        assert adult_classifier.apply_import_verdict(ambiguous, overrides) is True
        assert ambiguous.domain_niche == NICHE_UNKNOWN
        assert ambiguous.adult_method == adult_classifier.METHOD_SIGNALS

    @pytest.mark.asyncio
    async def test_ahrefs_csv_classifies_existing_uncached_domain(self, db, no_network):
        from backend.routers.import_export import import_ahrefs_backlinks_csv

        stale = Domain(id="d-x1", domain="oldsite.com")  # blind pre-fix row, no verdict
        db.add(stale)
        db.commit()

        csv_text = (
            "Referring page URL,Domain rating,Domain traffic,Anchor\n"
            "https://oldsite.com/post,50,1000,free porn xxx videos\n"
        )
        upload = UploadFile(io.BytesIO(csv_text.encode()), filename="backlinks.csv")
        result = await import_ahrefs_backlinks_csv(file=upload, competitor_domain="comp.com", db=db)

        assert result["domains_added"] == 0  # matched the existing row
        assert stale.domain_niche == NICHE_ADULT  # anchor evidence applied on import
        assert "anchor:" in stale.adult_detail
        assert no_network == []  # signals decided it — no fetch needed

    @pytest.mark.asyncio
    async def test_ahrefs_csv_applies_active_override_to_existing_domain(self, db, no_network):
        from backend.routers.import_export import import_ahrefs_backlinks_csv

        d = Domain(id="d-x2", domain="pornhub.com", domain_niche=NICHE_ADULT,
                   is_adult=True, adult_method="domain_keyword")
        db.add(d)
        # override row created out-of-band (drifted from the cached verdict)
        db.add(DomainAdultOverride(root_domain="pornhub.com", verdict=NICHE_NON_ADULT, note="client site"))
        db.commit()

        csv_text = (
            "Referring page URL,Domain rating,Domain traffic,Anchor\n"
            "https://pornhub.com/blog,90,5000,cool article\n"
        )
        upload = UploadFile(io.BytesIO(csv_text.encode()), filename="backlinks.csv")
        await import_ahrefs_backlinks_csv(file=upload, competitor_domain="comp.com", db=db)

        assert d.domain_niche == NICHE_NON_ADULT  # import re-asserted the override
        assert d.adult_method == "override"
        assert d.is_adult is False
        assert no_network == []

    @pytest.mark.asyncio
    async def test_domains_csv_classifies_existing_uncached_domain(self, db, no_network):
        from backend.routers.import_export import import_domains_csv

        stale = Domain(id="d-x3", domain="oldsite2.com")
        db.add(stale)
        db.commit()

        upload = UploadFile(io.BytesIO(b"domain\noldsite2.com\n"), filename="domains.csv")
        result = await import_domains_csv(
            file=upload, min_traffic=None, max_traffic=None, min_dr=None,
            max_dr=None, skip_non_adult=None, db=db,
        )

        assert result["added"] == 0
        assert result["skipped"] == 1
        assert no_network == ["oldsite2.com"]  # ambiguous → one homepage fetch
        assert stale.domain_niche == NICHE_UNKNOWN  # mocked fetch fails → cached unknown
        assert stale.adult_method == "inconclusive"
        assert stale.adult_classified_at is not None

    @pytest.mark.asyncio
    async def test_domains_csv_fetch_confirms_adult_at_import(self, db, monkeypatch):
        from backend.routers.import_export import import_domains_csv

        monkeypatch.setattr(adult_classifier, "_fetch_homepage",
                            _page_fetch(ADULT_HTML, title="Live Sex Cams 18+"))

        upload = UploadFile(io.BytesIO(b"domain\nrandomblog.com\n"), filename="domains.csv")
        result = await import_domains_csv(
            file=upload, min_traffic=None, max_traffic=None, min_dr=None,
            max_dr=None, skip_non_adult=True, db=db,
        )

        assert result["added"] == 1
        assert result["adult_scan"] == {"fetched": 1, "resolved": 1, "deferred": 0}
        d = db.query(Domain).filter(Domain.domain == "randomblog.com").first()
        assert d.domain_niche == NICHE_ADULT
        assert d.adult_method == "page_scan"
        assert d.is_adult is True

    @pytest.mark.asyncio
    async def test_domains_csv_skip_non_adult_drops_fetch_confirmed_non_adult(self, db, monkeypatch):
        from backend.routers.import_export import import_domains_csv

        monkeypatch.setattr(adult_classifier, "_fetch_homepage",
                            _page_fetch(CLEAN_HTML, title="Gardening Weekly"))

        upload = UploadFile(io.BytesIO(b"domain\ngardeningtips.com\n"), filename="domains.csv")
        result = await import_domains_csv(
            file=upload, min_traffic=None, max_traffic=None, min_dr=None,
            max_dr=None, skip_non_adult=True, db=db,
        )

        assert result["added"] == 0
        assert result["filtered_out"] == 1
        assert db.query(Domain).filter(Domain.domain == "gardeningtips.com").first() is None

    @pytest.mark.asyncio
    async def test_domains_csv_without_filter_keeps_fetch_confirmed_non_adult(self, db, monkeypatch):
        from backend.routers.import_export import import_domains_csv

        monkeypatch.setattr(adult_classifier, "_fetch_homepage",
                            _page_fetch(CLEAN_HTML, title="Gardening Weekly"))

        upload = UploadFile(io.BytesIO(b"domain\ngardeningtips.com\n"), filename="domains.csv")
        result = await import_domains_csv(
            file=upload, min_traffic=None, max_traffic=None, min_dr=None,
            max_dr=None, skip_non_adult=None, db=db,
        )

        assert result["added"] == 1
        d = db.query(Domain).filter(Domain.domain == "gardeningtips.com").first()
        assert d.domain_niche == NICHE_NON_ADULT
        assert d.is_adult is False


class TestImportFetchPass:
    @pytest.mark.asyncio
    async def test_ambiguous_domain_resolved_by_one_fetch(self, db, monkeypatch):
        calls = []

        async def fake_fetch(domain):
            calls.append(domain)
            return {"html": ADULT_HTML, "title": "Live Sex Cams 18+", "description": "", "status_code": 200}

        monkeypatch.setattr(adult_classifier, "_fetch_homepage", fake_fetch)

        d = Domain(id="d-f1", domain="ambiguous-blog.com")
        stats = await adult_classifier.run_import_fetch_pass([(d, None)])

        assert calls == ["ambiguous-blog.com"]
        assert d.domain_niche == NICHE_ADULT
        assert d.adult_method == "page_scan"
        assert stats == {"fetched": 1, "resolved": 1, "deferred": 0}

    @pytest.mark.asyncio
    async def test_fetch_pass_never_calls_ai(self, db, monkeypatch):
        async def boom_ai(*args, **kwargs):
            raise AssertionError("AI must never run during import")

        monkeypatch.setattr(adult_classifier, "_fetch_homepage",
                            _page_fetch("<html><body>tiny inconclusive page</body></html>"))
        monkeypatch.setattr(adult_classifier, "classify_ai", boom_ai)

        d = Domain(id="d-f2", domain="tinypage.com")
        stats = await adult_classifier.run_import_fetch_pass([(d, None)])

        assert d.domain_niche == NICHE_UNKNOWN  # short page → still unknown, no AI
        assert stats["resolved"] == 0

    @pytest.mark.asyncio
    async def test_anchor_evidence_resolves_without_fetch(self, db, no_network):
        d = Domain(id="d-f3", domain="someblog.com")
        stats = await adult_classifier.run_import_fetch_pass(
            [(d, ["free porn videos", "xxx movies here"])])

        assert no_network == []  # full anchor evidence decided it first
        assert d.domain_niche == NICHE_ADULT
        assert stats["resolved"] == 1

    @pytest.mark.asyncio
    async def test_fetch_cap_defers_rest_and_keeps_them_eligible(self, db, monkeypatch, no_network):
        monkeypatch.setattr(adult_classifier, "IMPORT_FETCH_MAX", 1)
        overrides = {}

        d1 = Domain(id="d-f4", domain="first-blog.com")
        d2 = Domain(id="d-f5", domain="second-blog.com")
        assert adult_classifier.apply_import_verdict(d1, overrides) is True
        assert adult_classifier.apply_import_verdict(d2, overrides) is True

        stats = await adult_classifier.run_import_fetch_pass([(d1, None), (d2, None)])

        assert stats == {"fetched": 1, "resolved": 0, "deferred": 1}
        assert no_network == ["first-blog.com"]
        # fetched one is cached-unknown now (fetch failed) — no longer eligible
        assert d1.adult_method == "inconclusive"
        assert adult_classifier.apply_import_verdict(d1, overrides) is False
        # deferred one keeps its signals-only verdict — next import may fetch it
        assert d2.adult_method == adult_classifier.METHOD_SIGNALS
        assert adult_classifier.apply_import_verdict(d2, overrides) is True

    @pytest.mark.asyncio
    async def test_fetch_timeout_persists_unknown_with_reason(self, db, monkeypatch):
        async def slow_fetch(domain):
            await asyncio.sleep(0.5)
            return None

        monkeypatch.setattr(adult_classifier, "_fetch_homepage", slow_fetch)
        monkeypatch.setattr(adult_classifier, "IMPORT_FETCH_TIMEOUT", 0.05)

        d = Domain(id="d-f6", domain="slowsite.com")
        stats = await adult_classifier.run_import_fetch_pass([(d, None)])

        assert d.domain_niche == NICHE_UNKNOWN
        assert "timed out" in d.adult_detail
        assert stats["resolved"] == 0

    @pytest.mark.asyncio
    async def test_duplicate_candidates_fetched_once(self, db, no_network):
        d = Domain(id="d-f7", domain="dupe.com")
        stats = await adult_classifier.run_import_fetch_pass([(d, None), (d, None)])

        assert stats["fetched"] == 1
        assert no_network == ["dupe.com"]


class TestClassifyAdultEndpoint:
    @pytest.mark.asyncio
    async def test_persists_verdicts_and_respects_precedence(self, db, no_network):
        from backend.routers.domains import classify_adult_domains, ClassifyAdultRequest

        kw = Domain(id="d-e1", domain="pornhub-clips.com")
        cached = Domain(id="d-e2", domain="cachedsite.com", domain_niche=NICHE_NON_ADULT,
                        is_adult=False, adult_method="page_scan", adult_confidence=0.7)
        overridden = Domain(id="d-e3", domain="adultswim.com")
        db.add_all([kw, cached, overridden])
        db.commit()
        set_adult_override(db, "adultswim.com", NICHE_NON_ADULT)
        db.commit()

        body = ClassifyAdultRequest(domain_ids=["d-e1", "d-e2", "d-e3"])
        result = await classify_adult_domains(body, db)

        assert result["scanned"] == 3
        assert result["adult"] == 1
        assert result["non_adult"] == 2
        assert no_network == []  # keyword/cached/override → zero fetches

        by_domain = {r["domain"]: r for r in result["results"]}
        assert by_domain["pornhub-clips.com"]["method"] == "domain_keyword"
        assert by_domain["cachedsite.com"]["method"] == "page_scan"
        assert by_domain["adultswim.com"]["method"] == "override"

        # verdict metadata persisted
        assert kw.domain_niche == NICHE_ADULT
        assert kw.adult_confidence >= 0.9
        assert kw.adult_classified_at is not None
        assert overridden.is_adult is False

    @pytest.mark.asyncio
    async def test_adult_checkbox_update_creates_durable_override(self, db, no_network):
        from backend.routers.domains import update_domain
        from backend.schemas.domain import DomainUpdate

        d = Domain(id="d-e4", domain="adultswim.com", is_adult=True)
        db.add(d)
        db.commit()

        await update_domain("d-e4", DomainUpdate(is_adult=False), db)
        assert d.is_adult is False
        assert d.adult_method == "override"
        overrides = load_adult_overrides(db)
        assert "adultswim.com" in overrides

        # a forced reclassification cannot undo the manual decision
        result = await classify_domain_with_cache(db, d, force_refresh=True)
        assert result["domain_niche"] == NICHE_NON_ADULT
        assert no_network == []


class TestMigration:
    def test_migration_is_idempotent(self, tmp_path, monkeypatch):
        spec = importlib.util.spec_from_file_location(
            "migrate_adult", ROOT / "scripts" / "migrate_adult_domain_classification.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        engine = create_engine(f"sqlite:///{tmp_path / 'mig.db'}")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE domains (id VARCHAR(36) PRIMARY KEY, domain VARCHAR(255))"))
        monkeypatch.setattr(mod, "engine", engine)

        mod.main()  # applies
        mod.main()  # skips everything, no error

        cols = {c["name"] for c in inspect(engine).get_columns("domains")}
        assert {"domain_niche", "adult_method", "adult_confidence", "adult_detail", "adult_classified_at"} <= cols
        assert inspect(engine).has_table("domain_adult_overrides")
