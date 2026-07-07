# SPEC — BackVora Domains Filter Improvements

**Status:** Ready-for-Builder
**Architect:** Codex
**Date:** 2026-07-07
**Task slug:** backvora-domains-filter-improvements
**Issue:** `webliftro/backvora#3`

## Intent & Surface
- **What R wants:** improve the `/domains` view filters so `Links To` / target filtering supports multiple selected targets instead of only all-or-one, and add an Adult Yes/No filter.
- **Primary surface:** `frontend-react/src/pages/DomainsPage.tsx`.
- **Likely supporting surfaces:** `frontend-react/src/types.ts` only if the current `Domain` shape lacks needed adult fields; no backend/API change is expected.
- **User-facing result:** from the Domains page, R can select several backlink targets and see rows whose `backlink_target` is any selected target. R can also filter adult-classified domains by Adult Yes or Adult No.

## Acceptance Criteria
- [ ] **AC1 — Multi-target filtering.** The Domains view target filter supports selecting zero, one, or many targets. Zero selected means all targets. One or more selected means rows pass if `domain.backlink_target` is included in the selected target set.
- [ ] **AC2 — URL target seeding preserved.** Existing `?target=<value>` behavior still works by preselecting that target in the multi-target filter. A persisted filter may coexist with URL seeding, but explicit URL target should be honored when present.
- [ ] **AC3 — Persistence preserved.** Domains filters remain persisted in `localStorage`. Multi-target selections persist as an array and existing old `targetFilter` string values are handled without crashing.
- [ ] **AC4 — Clear filters resets both new filters.** The existing Clear action resets the target selection and Adult filter along with the other filters.
- [ ] **AC5 — Adult Yes/No filter.** Add an Adult filter with at least All / Yes / No options. Semantics must match the new adult verdict model:
  - `Yes` matches `domain_niche === "adult"`.
  - `No` matches `domain_niche === "non_adult"`.
  - unknown/unclassified rows do not match Yes or No.
  - manual overrides are naturally covered because they persist `domain_niche`.
- [ ] **AC6 — Filters compose.** Search, status, category, multi-target, backlink yes/no, adult yes/no, competitor-only, traffic, DR, contacts, and link-type filters all continue to combine with AND semantics.
- [ ] **AC7 — UI stays compact.** The target filter control remains usable in the existing filter toolbar without making the Domains page materially taller or wider. A compact checkbox dropdown or similarly dense multi-select control is acceptable; do not redesign the table/page.
- [ ] **AC8 — Gates.** `flow gates --record backvora-domains-filter-improvements` is green before handoff. At minimum, TypeScript typecheck and frontend build must pass.

## Out Of Scope
- Backend/API changes.
- Data migration or production deploy.
- Redesigning the Domains table or broader filter system.
- Adding an Adult Unknown filter unless it falls out naturally and does not complicate the UI.
- Fixing unrelated import or bulk action behavior.

## Constraints
- Preserve existing filter localStorage key (`backvora_domains_filters`) unless there is a strong reason to change it.
- Keep backward compatibility with previously persisted `targetFilter: string`.
- Do not add a heavy component library for a small filter control.
- Keep changes tightly scoped to Domains filtering.

## Test Plan
- Code-read filter predicate for target OR semantics and Adult Yes/No semantics.
- Run `flow gates --record backvora-domains-filter-improvements`.
- If UI code is substantial, run or inspect the built bundle enough to confirm no TypeScript/build regression.

## Notes For Builder
- Current target filter state is a string named `targetFilter` in `frontend-react/src/pages/DomainsPage.tsx`.
- Current filter predicate uses `if (targetFilter && d.backlink_target !== targetFilter) return false;`.
- Current Adult column display already reads `domain_niche`, `is_adult`, and `is_adult_overridden`; use `domain_niche` for filtering to avoid treating old blind-default rows as adult.
- `targets` is already derived from loaded domain rows.
