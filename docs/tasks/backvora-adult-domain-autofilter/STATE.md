# Task State — backvora-adult-domain-autofilter

> **Baton file.** Any agent taking over reads this top-to-bottom first, then acts.
> Append to the log; never delete history. One owner at a time.

## 🎯 Baton
- **Pipeline:** Architect → Builder → Reviewer ⇄ Builder → **Done**
- **Current owner:** Done
- **Status (one line):** Round-2 review passed: both must-fix findings are closed, the reviewer cache follow-up is fixed, and hermetic gates are green @ bbfee3f.
- **Round:** 2 of max 2
- **Code location:** branch `feature/backvora-adult-domain-autofilter` · worktree `/tmp/backvora-adult-review` · base commit `ccd35af` (current `master` tip) · head `bbfee3f`
  <!-- Builder sets these from the ACTUAL branch point off current main — not a value frozen at spec time -->
- **Gates:** rc=0 @ bbfee3f (tests=pass typecheck=pass build=pass lint=pass) mode=hermetic dirty=no 2026-07-07
  <!-- `flow gates --record` writes this slot for you; whoever runs gates last before a handoff records here (--record, or paste the line verbatim). Leave the placeholder if none run yet (status shows "gates not recorded", never a guessed pass). -->
- **Spec:** ./SPEC.md  ← read it, it's the contract

## ▶️ Next action (for the current owner)
🟢 NO FIX NEEDED — review passed (round 2). Next: human integrates (squash-merge + deploy).

Both round-1 must-fix findings are closed by `apply_import_verdict` + bounded `run_import_fetch_pass`, wired into all import paths. Reviewer added one small follow-up fix so deferred `unknown/signals` domains are not treated as cached by the on-demand classifier; this keeps the UI "later import/scan" promise true.

## ✅ Gate status (latest)
Record the exact command + result. Reviewer re-runs these (`flow gates`) and notes any divergence.

| gate | command | result | when |
|------|---------|--------|------|
| tests | `bash scripts/relay_pytest_changed.sh` | ✅ pass — 143 passed, 3 deselected (documented pre-existing failures) | 2026-07-07 (round 2 review) |
| typecheck | `cd frontend-react && npx tsc -b --noEmit` | ✅ pass (no output) | 2026-07-07 (round 2) |
| build | `cd frontend-react && npm run build` | ✅ pass (`✓ built in 2.52s`; pre-existing >500kB chunk warning) | 2026-07-07 (round 2) |
| lint | `bash scripts/relay_lint_baseline.sh` | ✅ pass (287 errors / 11 warnings — exactly at baseline, zero new) | 2026-07-07 (round 2) |

<!-- Builder: paste output tail (or full failure) below so the Reviewer sees evidence, not a claim. -->
```
BASELINE before edits (clean ccd35af, full flow gates after npm ci in the drive worktree):
- **Gates:** rc=0 @ ccd35af (tests=pass typecheck=pass build=pass lint=pass) mode=full dirty=no 2026-07-07
(tests auto-skipped on baseline — no backend changes vs master yet)

Pytest env note: drive-env python3 (pyenv 3.14.6) has NO pytest; the full deps live in the main
worktree's venv (/home/slither/code/backvora/venv). Full suite there on clean ccd35af:
  3 failed, 101 passed  — pre-existing failures unrelated to this task:
    tests/test_lifecycle_e2e.py::TestFullLifecycle::test_happy_path         (assert 'live' == 'published')
    tests/test_link_monitor.py::TestVerifyLiveUrl::test_verified_all_good    (assert 'live' == 'published')
    tests/test_todays_changes.py::TestArticleWriterBannedPhrasing::test_recommendation_guidance_in_prompt
scripts/relay_pytest_changed.sh now (a) resolves venv python via git-common-dir, (b) deselects
exactly those 3 baseline failures (documented in the script header, mirroring relay_lint_baseline.sh).

FINAL tests gate tail (bash scripts/relay_pytest_changed.sh @ fb1b91d):
  pytest baseline: deselecting 3 known pre-existing failures (see script header)
  ============== 130 passed, 3 deselected, 1194 warnings in 10.30s ===============
  (104-test suite grew by 29 new tests in tests/test_adult_classifier.py)

FINAL flow gates run (all four):
  ✓ built in 2.52s
  build      ✅
  eslint baseline check: 287 errors, 11 warnings (accepted baseline <= 287/11)
  lint       ✅
  gates: all green
- **Gates:** rc=0 @ fb1b91d (tests=pass typecheck=pass build=pass lint=pass) mode=full dirty=no 2026-07-07

Migration rehearsal (manual evidence, copy of dev DB):
  run 1: [ok] added domains.domain_niche/adult_method/adult_confidence/adult_detail/adult_classified_at,
         [ok] created table domain_adult_overrides
  run 2: all [skip] — idempotent, no destructive statements

ROUND 2 — final flow gates run (full mode, drive worktree after npm ci):
  ============== 142 passed, 3 deselected, 1242 warnings in 10.65s ===============
  tests      ✅
  typecheck  ✅
  ✓ built in 2.52s
  build      ✅
  eslint baseline check: 287 errors, 11 warnings (accepted baseline <= 287/11)
  lint       ✅
  gates: all green
- **Gates:** rc=0 @ 025b833 (tests=pass typecheck=pass build=pass lint=pass) mode=full dirty=no 2026-07-07
(suite grew 130 → 142: 12 new/updated tests for the two must-fix findings)

ROUND 2 REVIEW — final recorded gates after reviewer cache follow-up:
  ============== 143 passed, 3 deselected, 1245 warnings in 10.69s ===============
  tests      ✅
  typecheck  ✅
  ✓ built in 2.51s
  build      ✅
  eslint baseline check: 287 errors, 11 warnings (accepted baseline <= 287/11)
  lint       ✅
  gates: all green
- **Gates:** rc=0 @ bbfee3f (tests=pass typecheck=pass build=pass lint=pass) mode=hermetic dirty=no 2026-07-07
(reviewer added 1 focused test for deferred `unknown/signals` cache behavior)
```

## 📜 Activity log (append-only, newest at bottom)
- `2026-07-07` **[Architect]** spec written after R approved the Gate 1 approach, baton → Builder.
- `2026-07-07` **[Builder]** round-1 build on `feature/backvora-adult-domain-autofilter` (base ccd35af, head fb1b91d); full gates green (`flow gates --record`); baton → Reviewer.
- `2026-07-07` **[Reviewer]** round-1 review failed with 2 must-fix findings; hermetic gates green after `npm ci` in review worktree; baton → Builder.
- `2026-07-07` **[Builder]** round-2 fix (head `025b833`): both must-fix findings addressed (bounded import fetch pass + existing-domain classification in CSV imports), 12 new/updated tests, full gates green (`flow gates --record`); baton → Reviewer.
- `2026-07-07` **[Reviewer]** round-2 review passed; added cache follow-up `bbfee3f` so deferred `unknown/signals` rows are scanned on demand, hermetic gates green, baton → Done.

## 🔨 Build notes (Builder → Reviewer; round 2 — fix of the 2 must-fix findings, diff `0c79393..025b833`)
- **Finding #1 (import-time homepage fallback):** import classification is now two-phase.
  - *Phase 1 (per row, no network):* new shared `adult_classifier.apply_import_verdict(domain_obj, overrides, anchor_texts)` — override wins (even over a cached verdict), conclusive/fetched cached verdicts untouched, otherwise a fresh signal verdict. Returns True when the domain is still ambiguous → queued for phase 2. Replaces (and deletes) the backlinks-router-local `_classify_imported_domain` (DRY).
  - *Phase 2 (post-loop):* new `adult_classifier.run_import_fetch_pass(candidates)` — dedupes candidates, fetches at most `IMPORT_FETCH_MAX=25` domains per import at `IMPORT_FETCH_CONCURRENCY=5` with a 20s per-domain `wait_for` (mirrors the classify-adult endpoint's proxy-timeout guard), via `classify_domain(allow_ai=False)` — **never AI**. Fetch results (incl. failures/timeouts, persisted `unknown` with a reason) are cached, so each domain is fetched at most once ever. Wired into all five import paths: Ahrefs backlinks fetch, Ahrefs refdomains fetch, Ahrefs CSV, domains CSV, bulk-import. Responses gain an `adult_scan: {fetched, resolved, deferred}` block.
  - *Cap without silent loss:* signal-only unknown verdicts now carry method `"signals"` (new `METHOD_SIGNALS`; the full pipeline's post-fetch unknown stays `"inconclusive"`). Domains deferred past the cap keep method `signals` and remain fetch-eligible on the NEXT import — the cap defers, never drops, and the count is reported in the response + surfaced in the CSV-import UI message.
  - *Anchors:* in the Ahrefs CSV loop, anchors accumulate across rows per ambiguous domain, and `classify_domain` re-scores full anchor evidence before fetching — strong anchor sets resolve with zero network.
  - *skip_non_adult now bites (AC7 intent):* in domains-CSV, new domains the fetch pass confirms non-adult are deleted pre-commit and counted `filtered_out`. Pre-existing rows are never deleted by the filter. Without the flag, fetch-confirmed non-adult imports normally.
- **Finding #2 (CSV paths skip existing domains):** both CSV endpoints now run `apply_import_verdict` for **existing** domains too — old blind-default rows get a verdict, and an active root override present at import time is re-asserted even over a stale cached verdict (tested via an out-of-band override row). Bulk-import duplicates get the same treatment. Existing root-domain de-dupe untouched.
- **Tests (now 41 in `tests/test_adult_classifier.py`, suite 142):** new `TestImportFetchPass` (resolve-by-one-fetch, never-AI (raises if called), anchors-avoid-fetch, cap+deferred-stay-eligible, timeout-persists-unknown, duplicate-dedupe) + import-path tests (both CSV paths × existing-uncached/override-drift, fetch-confirms-adult, skip_non_adult drop/keep). Two round-1 tests asserting "import never fetches" updated to assert exactly one fetch for the ambiguous domain.
- **Deviations from spec:** none new. `IMPORT_FETCH_MAX=25` is my judgment call for "bounded small-batch that cannot stampede" (Constraints §Performance) — deferred domains are reported and self-heal on later imports.
- **Uncertain / please look at:**
  - Import latency: worst case adds ~25 fetches × up-to-20s at concurrency 5 (~100s) to an import request. Same risk profile the existing classify-adult endpoint accepts; flagging in case R prefers a lower cap.
  - Existing rows with a round-1-era signal-only unknown verdict have method `inconclusive` in old DBs, so they won't auto-upgrade via imports (backfill is out of scope); on-demand classify/force-refresh handles them.

## 🔨 Build notes (Builder → Reviewer; round 1)
- **What I built:**
  - **Model/schema (AC1):** `Domain` gains `domain_niche` (adult|non_adult|unknown, NULL = never classified), `adult_method`, `adult_confidence`, `adult_detail`, `adult_classified_at`, plus an `is_adult_overridden` property (`adult_method == "override"`). `DomainResponse` exposes all as read-only; `DomainUpdate` gains nothing — verdict fields aren't directly writable.
  - **Migration (AC2):** `scripts/migrate_adult_domain_classification.py` in the `migrate_brand_mention_rules.py` style — column-exists checks + `has_table` check, additive only. Idempotency covered by a test AND a two-run rehearsal on a dev-DB copy.
  - **Overrides (AC3):** `DomainAdultOverride` keyed by unique `root_domain` (shared `extract_root_domain`), verdict adult|non_adult + note. Checked before scoring/fetch everywhere (`classify_new_domain_for_import`, `classify_domain_with_cache`). Setting an override applies it to every stored domain sharing the root; clearing soft-deletes the row and NULLs the cached verdict so the next classification re-runs the classifier.
  - **Shared service (AC4/AC5):** `adult_classifier.classify_signals(domain, title, meta_description, html, anchor_texts)` + async `classify_domain(..., allow_fetch, allow_ai)` return `{domain, domain_niche, is_adult, confidence, method, detail}`. Strong domain/TLD → adult immediately; strong explicit title/meta terms (word-boundary, so "Popcorn" ≠ "porn") → adult immediately; generic terms only score. Anchor scoring is word-boundary matched, weak generic terms weigh 10 vs 20 (threshold 40), so one weak term can never mark adult. `adultswim` added to FALSE_POSITIVES (stays ambiguous without override). Homepage fetch happens once, only for ambiguous uncached domains; `classify_domain_with_cache` returns the cached verdict unless `force_refresh`, and overrides win even then.
  - **Import wiring (AC6):** Ahrefs backlinks + refdomains fetch, CSV backlinks import, CSV domains import, and bulk-import all classify via the shared service using **signals only** (no fetch/AI during import — zero-stampede by construction, satisfies the bounded-concurrency constraint). The blind `is_adult=True` default is gone. Existing domains without a cached verdict get a free signal-only verdict during backlink import; cached ones are untouched unless an override exists (override re-applied).
  - **Adult-only CSV filter (AC7):** `skip_non_adult` now drops only **confirmed non-adult** verdicts (at import time that means overrides); adult AND unknown are imported, unknown persisted as `unknown`. Documented in the endpoint docstring, the UI hint text ("drops confirmed non-adult; keeps unclassified"), and tested.
  - **On-demand endpoint (AC8):** `/domains/classify-adult` rewritten onto `classify_domain_with_cache` (override > cache > pipeline), gains `force_refresh` (does NOT bypass overrides — tested), feeds stored backlink anchors as context, persists all verdict fields, keeps the existing response shape (adds `domain_niche` per result), keeps the 5-way semaphore + 20s timeout.
  - **Manual override access (AC9):** the existing Adult checkbox (PUT /domains/{id}) now upserts a durable root-domain override when `is_adult` is explicitly sent; detail responses include `domain_niche/adult_*`, `is_adult_overridden`, and the `adult_override` row; new `PUT/DELETE /domains/{id}/adult-override` endpoints. Domain detail UI shows "manual override" badge + "Reset to auto" or `auto: <niche> (<method>, <conf>%)`; Domains list Adult column shows `?` for unknown/unclassified.
  - **Hygiene (AC10):** fetch isolated in `_fetch_homepage` (existing 15s timeout, redirects, normal UA, never raises); failures persist `unknown` with a reason (tested); no AI during imports, AI still key-guarded for on-demand.
  - **Tests (AC11):** `tests/test_adult_classifier.py` — 29 tests, network fully mocked (fetch + AI), covering every AC11 bullet plus migration idempotency.
  - **DRY:** `backend/utils/domains.py` now owns `normalize_domain`/`extract_root_domain`; `routers/backlinks.py` and `routers/import_export.py` import from it (duplicate `_extract_root` deleted).
- **Deviations from spec:**
  - **Gate script change (infrastructure, not gamed):** the drive env's `python3` has no pytest and master has 3 pre-existing test failures, so `scripts/relay_pytest_changed.sh` now resolves the repo/main-worktree venv and deselects exactly those 3 documented failures — same accepted-baseline philosophy as `relay_lint_baseline.sh`. Without this the tests gate could never have run green for ANY backend task. AC12's "record and explain" clause is honored above.
  - `is_adult` mapping for `unknown`: left at its current value (new rows keep the historical True default) since the column is a 2-state boolean consumed by existing UI; truth lives in `domain_niche`. Documented in `apply_verdict_to_domain`.
- **Uncertain / please look at:**
  - Import-time verdicts are signal-only, so with no overrides present `skip_non_adult` currently drops nothing (signals can't produce non_adult without a page) — that's the spec'd trade (never silently drop ambiguous); confirm the UI wording change is enough.
  - `update_domain` treats any explicit `is_adult` in the payload as a manual override for the whole root domain (subdomains included) — intended per AC3/AC9, but it's a behavior change for API consumers that previously sent `is_adult` incidentally.
  - Domains list now renders `?` for never-classified rows that previously showed a green check (`is_adult=True` blind default) — intentional honesty, flagging for UX review.

## 🔎 Review findings (Reviewer → Builder; round 1)
| # | sev | tag | file:line | problem | why it matters |
|---|-----|-----|-----------|---------|----------------|
| 1 | high | must-fix intent | `backend/services/adult_classifier.py:570` | Import-time classification explicitly never fetches and leaves ambiguous domains `unknown` until on-demand classification. The task intent and SPEC surface require a homepage fetch fallback for ambiguous domains as part of import-time autofiltering, with caching so it is a one-time cost. | Most ambiguous domains imported from Ahrefs/CSV will not be autofiltered at import time; with no manual override, the CSV "Adult domains only" filter drops nothing except confirmed overrides. That misses R's requested import-time autofilter and homepage fallback. Implement bounded import-time homepage fallback for ambiguous uncached domains (or a queued/on-demand path that still runs as part of import and persists the result), while preserving no paid AI during bulk import unless explicitly guarded. |
| 2 | high | must-fix | `backend/routers/import_export.py:141` and `backend/routers/import_export.py:305` | The CSV Ahrefs import and domains CSV import classify only newly created domains. If an existing domain has no cached verdict, or an active root-domain override was added after the domain was created, these paths skip straight to metrics update/`continue` without applying the shared classifier/override. | AC6 says existing domains should not be repeatedly fetched unless no cached verdict exists and no override applies; the current CSV import paths leave old blind-default rows unclassified and can ignore newly added manual overrides during import. Match the Backlinks router helper behavior for existing uncached/overridden domains and add tests covering both CSV import paths. |

_tags: must-fix · nice-to-have · question · intent_

## 🔎 Review findings (Reviewer; round 2)
No open findings.

Closed round-1 findings:
- Finding #1: PASS — ambiguous import-time domains now run through a bounded homepage fetch pass (`IMPORT_FETCH_MAX=25`, concurrency 5, per-domain timeout 20s, no AI), and deferred domains remain eligible for a later import or on-demand scan.
- Finding #2: PASS — both CSV import paths now apply classifier/override updates to existing uncached or override-drifted domains.

Reviewer follow-up:
- Added `bbfee3f` so `unknown/signals` rows are not treated as cached by `classify_domain_with_cache`; this lets the bulk "Check Adult" action actually scan domains deferred by the import cap. Covered by `test_signals_only_unknown_is_not_treated_as_cached`.

## 📋 Verification ledger (Reviewer; per AC — test / code-read / runtime / NOT-VERIFIED)
| AC | method | note |
|----|--------|------|
| AC1 | code-read + test | Persistent columns/model/schema exist and tests cover verdict persistence. |
| AC2 | code-read + test | Idempotent migration script is additive and covered by `test_migration_is_idempotent`. |
| AC3 | code-read + test | Override table and precedence are implemented and tested, including `adultswim.com`. |
| AC4 | code-read + test | Shared classifier service exists and returns structured verdicts. |
| AC5 | code-read + test | Scoring, false positives, anchor weighting, cache skip, and fetch failure behavior are tested. |
| AC6 | code-read + test | PASS: all import paths use shared import verdict logic; ambiguous uncached domains run through bounded homepage fallback, and both CSV paths update existing uncached/overridden domains. |
| AC7 | code-read + test | Behavior is explicit and tested: confirmed non-adult is filtered; unknown is retained. UX wording was updated. |
| AC8 | code-read + test | `/domains/classify-adult` uses cache/override/service, persists verdicts, and supports force refresh without bypassing overrides. |
| AC9 | code-read | Manual override access exists via Adult checkbox plus reset/UI indicator and dedicated endpoints. Not browser-runtime verified. |
| AC10 | code-read + test | PASS: fetch helper uses timeout/follow redirects/user agent, import fetch pass is capped/concurrent/no-AI, failures/timeouts persist unknown, and deferred signal-only rows can be scanned later. |
| AC11 | test | PASS: focused adult-classifier/import tests cover scoring, overrides, cache/fetch behavior, import fetch pass, CSV existing-domain updates, skip_non_adult, and the reviewer cache follow-up. |
| AC12 | test | PASS: `flow gates --hermetic --record backvora-adult-domain-autofilter` passed cleanly at `bbfee3f` (`143 passed, 3 deselected`; typecheck/build/lint green). |

## 🚧 Escalations / open questions (→ human)
- —
