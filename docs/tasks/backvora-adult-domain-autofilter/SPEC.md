# SPEC — BackVora Adult Domain Autofilter

**Status:** Ready-for-Builder
**Architect:** Codex
**Date:** 2026-07-07
**Task slug:** backvora-adult-domain-autofilter

## Intent & Surface
- **What R actually wants:** "set up some kind of filter for adult in backvora, capable of autofiltering. The idea is so that domains get autofiltered correctly, with the option to manually overturn that." The requested signals are domain name, homepage title/meta, anchor texts, homepage fetch fallback for ambiguous domains, cached DB verdict, and manual whitelist/blacklist overrides such as `adultswim.com`.
- **Which surfaces:** BackVora backend domain intake/classification paths: `backend/services/adult_classifier.py`, Ahrefs/backlink import in `backend/routers/backlinks.py`, CSV/domain import paths in `backend/routers/import_export.py` and `backend/routers/domains.py`, on-demand `POST /api/v1/domains/classify-adult`, domain schemas/models, migration script(s), and focused frontend touchpoints only where needed for manual overrides on existing domain views.
- **Where R accesses it later:** Imported/referring domains are auto-classified as they enter BackVora; existing domains can be reclassified with the current "Check Adult" action; a manual override can be set/cleared from an existing domain detail/manual-edit surface and is reflected in domain lists/API responses.
- **What done looks like:** New referring/imported domains no longer blindly default to adult. They receive a cached adult/non-adult/unknown verdict from scoring and, only when needed, homepage scan. Manual overrides win over the classifier and survive future imports/reclassification.

## Goal
BackVora should classify referring domains automatically and consistently at ingestion time, while keeping a durable manual correction path for edge cases. The system should reuse the existing adult classifier and `is_adult` field for compatibility, but add enough verdict metadata to avoid repeated network fetches and to explain why a domain was marked adult, non-adult, or unknown.

## Acceptance Criteria
- [ ] **AC1 — Persistent verdict model.** `Domain` stores cached classification metadata in addition to existing `is_adult`: `domain_niche` (`adult`, `non_adult`, `unknown`), classifier method/source, confidence, human-readable detail/signals, and last classified timestamp. `is_adult` remains present and is updated from the verdict for compatibility. Domain response/update schemas expose the new read fields and allow only intentional manual fields to be changed.
- [ ] **AC2 — Idempotent migration.** Existing installs get the new columns and override table through a safe, idempotent migration script following the current `scripts/migrate_brand_mention_rules.py` style. The script must skip already-applied columns/tables and work against the configured SQLAlchemy engine. No destructive migration is allowed.
- [ ] **AC3 — Manual overrides.** A `DomainAdultOverride`-style table exists, keyed by normalized/root domain, with verdict (`adult` or `non_adult`), optional note/reason, and timestamps. Overrides are checked before any classifier scoring or network fetch. A forced non-adult override for `adultswim.com` classifies as non-adult even though the domain contains `adult`. Clearing an override returns the domain to classifier behavior on next forced classification.
- [ ] **AC4 — Shared classifier service.** `backend/services/adult_classifier.py` exposes one shared service/function for classifying a domain with optional context: domain name, homepage title/meta/html when available, and anchor texts. It returns structured data: `domain`, `domain_niche`, `is_adult`, `confidence`, `method`, and `detail`/signals. Domain keyword scoring, title/meta scoring, anchor text scoring, homepage scan, and existing AI fallback are coordinated in this service instead of duplicated in routers.
- [ ] **AC5 — Scoring behavior.** The classifier scores adult terms from domain name, title/meta, and anchor texts. Strong domain/TLD or strong title/meta signals classify adult immediately. Known false positives stay ambiguous or non-adult unless other signals overcome them. Anchor text can contribute to the score but must not mark a domain adult from one weak generic term alone. Ambiguous uncached domains may do one homepage fetch; cached verdicts skip repeated fetches unless force refresh is requested.
- [ ] **AC6 — Import-time classification.** New domains created by Ahrefs/backlink ingestion, CSV import, and domain bulk import call the shared classifier and persist the verdict metadata. Existing root-domain de-dupe behavior is preserved. Existing domains should not be re-fetched during import unless no cached verdict exists and no override applies.
- [ ] **AC7 — Adult-only import filter fixed.** CSV `skip_non_adult` / frontend "Adult domains only" filters on the shared persisted verdict, not only obvious domain keyword hits. Adult and unknown handling must be explicit: non-adult domains are filtered out; adult domains are imported; unknown domains are either imported as unknown or filtered according to a documented, tested choice. The choice must avoid silently dropping ambiguous domains that may be adult unless the UI/API name clearly says it does.
- [ ] **AC8 — On-demand reclassification.** `POST /api/v1/domains/classify-adult` uses the shared service, persists all verdict fields, respects overrides, and returns method/confidence/detail in its existing result shape. It should support a force refresh path if needed to bypass stale cache, but force refresh must not bypass manual overrides.
- [ ] **AC9 — Manual override access.** The existing domain detail/manual edit flow provides a clear way to set or clear the adult verdict override without a large new admin screen. Reusing the existing Adult checkbox is acceptable only if the UI/API makes it durable as a manual override and the response shows whether a value is automatic or overridden.
- [ ] **AC10 — Security and network hygiene.** Homepage fetches use conservative timeouts, redirect limits/following consistent with existing classifier behavior, a normal user agent, and no credential leakage. Failures classify as `unknown` with a reason; they do not crash imports. No paid AI call is made during bulk import unless already configured and explicitly guarded by the existing classifier behavior.
- [ ] **AC11 — Focused tests.** Add automated tests with network calls mocked for: domain keyword adult hit, false positive `adultswim.com` override, title/meta adult hit, anchor text scoring, homepage fetch used only for ambiguous uncached domains, cached verdict skip, override precedence, CSV/import classification behavior, and `/domains/classify-adult` persistence. Tests should avoid real HTTP and real external APIs.
- [ ] **AC12 — Gates.** `flow gates --record backvora-adult-domain-autofilter` is green before handoff. If the baseline has unrelated known failures, record the exact command/output and explain why the task did not regress it.

## Out Of Scope
- Production deploy, production DB migration execution, or live data backfill.
- Replacing BackVora's whole category/tag system.
- Building a large override management dashboard.
- Changing campaign/order/link-building business logic unrelated to domain classification.
- Fixing the known pre-existing Domains text bulk-import contract bug unless it directly blocks this task and the fix is narrowly scoped.
- Broad frontend redesign, table redesign, or unrelated lint cleanup.

## Constraints
- **Single source of truth:** classifier scoring and verdict persistence must live behind shared service functions, not copied into import routers.
- **Compatibility:** preserve existing `Domain.is_adult`, API consumers, and frontend list/detail behavior while adding richer verdict metadata.
- **DB safety:** use additive schema changes only. Never drop/truncate data. Migration must be idempotent.
- **Performance:** import paths must not perform unbounded concurrent homepage fetches. Bulk work needs bounded concurrency or a clearly synchronous small-batch behavior that cannot stampede remote sites.
- **Security:** do not fetch arbitrary internal URLs from user-provided full URLs. Normalize to domains and fetch only `https://<domain>` / fallback behavior chosen by the classifier. No secrets in code.
- **DRY:** normalize/root-domain handling should be shared or reused where practical; do not create competing normalization logic in multiple routers.

## Test Plan
- **Unit / automated:** run focused pytest coverage for `adult_classifier`, migration helper behavior where practical, import-router/service behavior with mocked classifier/fetches, override precedence, and domain schema/API response behavior.
- **Frontend:** typecheck/build must pass for any UI changes. Browser verification is limited to existing Domain Detail / Domains list affordances if the Builder changes the UI.
- **Gates:** `flow gates --record backvora-adult-domain-autofilter` before Builder handoff. The repo gates are tests (`bash scripts/relay_pytest_changed.sh`), typecheck (`cd frontend-react && npx tsc -b --noEmit`), build (`cd frontend-react && npm run build`), and lint (`bash scripts/relay_lint_baseline.sh`).
- **Boundary note for the Builder:** values consumed from Ahrefs rows are `name_source`, `anchor`, `url_from`, `url_to`, `domain_rating_source`, and `traffic_domain`; existing import de-dupe consumes root-domain extraction from `backend/routers/backlinks.py`; frontend domain shape comes from `frontend-react/src/types.ts` and `backend/schemas/domain.py`. Verify producers before relying on new fields.

## Likely-Touched Files
- `backend/models.py`
- `backend/schemas/domain.py`
- `backend/services/adult_classifier.py`
- `backend/routers/backlinks.py`
- `backend/routers/import_export.py`
- `backend/routers/domains.py`
- `backend/services/__init__.py` if needed for exports
- `scripts/migrate_adult_domain_classification.py` or similarly named idempotent migration
- `tests/test_adult_classifier.py` and/or focused router/import tests
- `frontend-react/src/types.ts`
- `frontend-react/src/api.ts`
- `frontend-react/src/pages/DomainDetailPage.tsx`
- `frontend-react/src/pages/DomainsPage.tsx` only if needed to display override/source state

## Notes / Open Context
- Existing classifier already has domain keyword, page content, and AI fallback logic in `backend/services/adult_classifier.py`; extend it instead of starting over.
- Current ingestion defaults new backlink/referring domains to `is_adult=True`; this is the core behavior to replace.
- Current CSV `skip_non_adult` uses only `classify_domain_keyword`, which can wrongly skip ambiguous adult domains before homepage/title/meta/anchor evidence is considered.
- This repo uses `Base.metadata.create_all(checkfirst=True)` plus one-off migration scripts, not Alembic.
- `flow memory` warns that Domains text bulk-import is already broken on `master` because frontend sends `{domains, is_competitor}` while endpoint expects a bare array. Do not let that unrelated bug expand the scope unless it blocks the accepted path.
