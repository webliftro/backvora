# SPEC — BackVora Premium Neutral Refresh (color correction + modern polish)

**Status:** Ready-for-Builder
**Architect:** Claude Fable 5
**Date:** 2026-07-03
**Task slug:** backvora-ui-premium-neutral-refresh

## Intent & surface (confirmed with the user)
- **What R actually wants (his words):** "I hate the colors, let's return to the old ones." "Let's use more modern icons, buttons etc... maybe glassification or something?" Clarified: "old colors as the base with a more premium modern accent system."
- **Which surface(s):** The React/Vite/Tailwind 4 frontend under `frontend-react`. Theme: `src/index.css`. Shell: `src/components/Layout.tsx`. Shared components: `Modal.tsx`, `Toast.tsx`, `ui.tsx`. All authenticated routes (`/dashboard`, `/domains`, `/domains/new`, `/domains/:id`, `/target-sites`, `/target-sites/:id`, `/campaigns`, `/campaigns/:id`, `/competitors`, `/outreach`, `/deals`, `/inbox`, `/check-metrics`, `/settings`); `/login` and public `/` only as needed for consistency.
- **Where R accesses it:** Immediately, on every route, every session.
- **What "done" looks like to R:** The app is on the original pure-neutral dark grays again — it "feels like BackVora," not purple/rose — with a restrained, premium accent system on top, visibly more modern buttons/icons/controls, and tasteful selective glass on overlay chrome. Everything works exactly as before.

## Goal
The previous refresh (`backvora-ui-visual-refresh`, integrated at `a1765b3`) delivered a good shell, components, responsiveness, and a11y — but its rose-cast neutral ramp and raspberry accent are rejected. This task swaps the color foundation back to the original pure-neutral grays, replaces the raspberry ramp with a crisper premium accent system, and layers in modern control polish (buttons, icons, pills, filter bars, selective glass) — while preserving every structural and behavioral win from the previous task.

## Design direction (agreed with R — not optional)
1. **Old neutrals are the base.** The pre-refresh gray scale from `master@a6803d0:frontend-react/src/index.css` returns verbatim (values in AC1). Pure neutral — zero hue cast. Dark-first, single mode.
2. **Premium accent system, restrained.** Pink stays BackVora's brand family (it was the accent before the refresh too), but retuned: crisp and modern on pure-neutral darks, not the rejected raspberry (`#c43d74`) and not neon. Accents are scarce by design — defined usage tiers (AC2), never sprayed across surfaces.
3. **Selective glass only.** Subtle translucency/blur/border/highlight is allowed on overlay chrome (modals, drawer, dropdowns, toasts, sticky bars, optionally the sidebar) where it raises perceived quality. No all-over glass, no gradient blobs/orbs, no marketing-hero treatment inside the app.
4. **Modern controls.** Buttons, icon treatment, hover/focus/active states, cards, table controls, filter bars, status pills, and empty/loading/error states get a consistent, contemporary pass — shared primitives over page-local one-offs.
5. **Keep the previous task's wins.** Sidebar shell + mobile drawer, shared Modal/Toast/ui primitives, operational density, responsive behavior at 390/768/1280/1440, and the a11y state (focus rings, labeled icon-only buttons, AA contrast) must not regress.

## Acceptance criteria
Graded by code-read plus running the app locally. "Visible" means observable in a browser at the stated viewport.

- [ ] **AC1 — Old neutral base restored in tokens.** `src/index.css` `@theme` defines the gray ramp with exactly the pre-refresh values: `gray-50 #fafafa`, `gray-100 #f5f5f5`, `gray-200 #e5e5e5`, `gray-300 #d4d4d4`, `gray-400 #a3a3a3`, `gray-500 #737373`, `gray-600 #525252`, `gray-700 #333333`, `gray-800 #1a1a1a`, `gray-900 #0a0a0a`, `gray-950 #050505`. The semantic tokens introduced by the previous task (`--color-bg`, `--color-surface`, `--color-surface-2`, `--color-line`, `--color-ink`, `--color-ink-dim`, `--color-ink-mute`, brand/status/ring tokens) are kept as the vocabulary and remapped onto this neutral ramp. Every neutral used anywhere (scrollbar, selection, borders, surfaces) has zero saturation — no rose/purple cast remains in any gray.
- [ ] **AC2 — Premium accent system, bounded.** The `pink-*` ramp values in `index.css` are replaced with a modern pink/magenta tuned for pure-neutral darks: hue in the 320–345° family, crisp but not fluorescent; white text on `pink-600` ≥ 4.5:1; `pink-400` text on `gray-800` and `gray-900` ≥ 4.5:1. A comment block in `index.css` documents the accent usage tiers, and the app obeys them: **fills** only on primary buttons and the active-nav indicator; **text/links** for brand-accent text; **ring** for focus; **tints** (accent backgrounds/borders at ≤ 15% opacity) only for active/selected states; checkbox/radio `accent-color` and `::selection`. At rest, cards, tables, page chrome, and secondary controls show no accent. Status ramps (green/red/yellow/amber/blue/teal/purple/orange/emerald) stay restrained and dark-tuned — existing values may be kept or minimally retuned to sit well on the neutral base; they must not become neon.
- [ ] **AC3 — Selective glass, with rules.** Glass treatment (translucent surface + `backdrop-blur` + 1px border + optional inset top-edge highlight ≤ white/10) appears only on overlay chrome: the modal backdrop and panel (`Modal.tsx`), the mobile drawer and its backdrop, dropdown/popover menus, toasts (`Toast.tsx`), sticky top bars, and optionally the sidebar (`Layout.tsx`). Recipe bounds: surface opacity ≥ 70% (text must meet AA against the worst-case content behind it), blur between 8–16px. Prohibited anywhere: glass on page backgrounds, tables/rows, inputs, or data cards; gradient orbs/blobs/bokeh; decorative hero sections inside the authenticated app.
- [ ] **AC4 — Shared Button primitive.** `ui.tsx` gains a `Button` component with variants (primary/secondary/ghost/danger) and sizes (sm/md) defining consistent radius, padding, typography, icon slot, and hover/active/disabled/`focus-visible` treatments (visible hover shift, pressed feedback, dimmed+non-interactive disabled). Standard buttons across the pages adopt it; in `CampaignDetailPage.tsx` (2,135 lines), mechanical class alignment to the same visual spec is acceptable where extraction would require restructuring JSX/state. Grading check: the same button variant on any two pages looks identical.
- [ ] **AC5 — Status pill primitive.** `ui.tsx` gains a `StatusPill`/`Badge` component (tone-based: success/warning/danger/info/neutral/brand) and the status pills on Domains, Campaigns (+ detail), Deals, Target Sites, Outreach, and Inbox render through it (or, where a page computes tone from backend strings, through one shared tone-map utility — not per-page hex/class one-offs). Backend status strings are styled by value, never renamed or remapped.
- [ ] **AC6 — Modern icon treatment.** All icons come from `lucide-react` (already true — keep it that way). Icon sizing is consistent: one size inside buttons/table rows/pills, one size in nav/section headers, applied uniformly. Emoji used as UI icons are replaced with lucide equivalents: the 📧/⚠️ row indicators in `DomainsPage.tsx` (~line 184), and the `✅`/`❌` prefixes in result banners (`DomainsPage.tsx`, `CompetitorsPage.tsx`) become tone-styled banners with a lucide icon instead of an emoji prefix. Emoji inside toast message strings passed straight from errors are out of scope.
- [ ] **AC7 — Table controls, filter bars, and states.** Filter/search bars and table toolbars share one consistent treatment (input + select + button alignment, spacing, surface). Empty lists use the shared `EmptyState`. Loading uses one consistent treatment (spinner or skeleton — pick one) across pages. Error/result banners share tone styling from the status tokens. Grading check: the Domains, Campaigns, Deals, and Target Sites list pages look like one product.
- [ ] **AC8 — Behavior preserved everywhere.** No route paths, redirects, auth guards, API calls, form submissions, handlers, or state transitions change. `App.tsx` is untouched. `TargetSitesPage.tsx` keeps its `TargetSitesListPage`/`TargetSiteDetailPage` named exports. On `/campaigns/:id`: article edit → save, edit → cancel, regenerate, order rows, verification status, and modal flows behave exactly as on current `master`.
- [ ] **AC9 — Responsive preserved.** At exactly 390px, 768px, 1280px, and 1440px: navigation, tables/lists, buttons, filters, modals, and long labels do not overlap or clip important text; no horizontal page scroll except inside intentionally scrollable containers. The mobile drawer still opens/closes and closes on navigate.
- [ ] **AC10 — A11y and density preserved.** Every interactive control keeps a visible `focus-visible` indicator (retune the ring color to the new accent; do not remove it). All icon-only buttons keep their `aria-label`/`title` (the previous task labeled them all — zero regressions, including any newly added icon-only controls). Body/table text meets WCAG AA (≥ 4.5:1 normal, ≥ 3:1 large) against its surface, including glass surfaces. Hover-revealed controls remain reachable via keyboard focus. Row heights and rows-per-screen at 1440×900 on Dashboard, Domains, Campaigns, Deals, and Inbox are ≥ the current `master` build.
- [ ] **AC11 — No decorative clutter.** Zero anywhere in the diff: gradient orbs/blobs/bokeh, decorative hero sections in the authenticated app, cards nested inside cards, or in-app copy announcing the redesign.
- [ ] **AC12 — Gates.** Baseline `flow gates` run and recorded on the fresh branch *before* any UI change, then `flow gates --record backvora-ui-premium-neutral-refresh` fully green (rc=0) before handoff, using the current `relay.config`: tests `bash scripts/relay_pytest_changed.sh` (auto-skips green when no Python/backend changes), typecheck `cd frontend-react && npx tsc -b --noEmit`, build `cd frontend-react && npm run build`, lint `bash scripts/relay_lint_baseline.sh` (green while ESLint problems stay ≤ 287 errors / 11 warnings). The last recorded run on `master` is rc=0, so full green is achievable and required — a frontend-only branch has no excuse for red.

## Out of scope (do NOT build)
- Backend/API changes of any kind; database or migration work. (Includes the known bulk-import 422 contract bug — leave it.)
- New features, new routes, changed auth behavior, changed business logic.
- Light mode / theme switching.
- Structural redesign of the sidebar shell, drawer, or page layouts — this is a color-and-polish pass on the existing structure, not a second shell rebuild.
- Redesigning public Home `/` or `/login` beyond bringing them onto the corrected tokens/accent — consistency only.
- Copy rewrites beyond labels needed for visual clarity.
- Codebase-wide lint-debt cleanup or unrelated refactors.
- Deploying, pushing to GitHub, or integrating to `master` (human gate).

## Constraints
- **The `@theme` token remap is the lever.** ~290 `pink-*` and thousands of `gray-*` utility usages resolve through `index.css` tokens. Restore/retune *values* there; do not sweep class names across pages except where an AC explicitly requires component adoption. After changing token values, verify no page becomes unreadable (the previous rose values were contrast-tuned; the neutral ramp shifts several relationships — e.g. `gray-700` borders on `gray-800` surfaces are subtler at `#333333`/`#1a1a1a` than at the rose values).
- **`CampaignDetailPage.tsx` is 2,135 lines.** Targeted, mechanical class edits only; do not restructure state, handlers, or JSX logic. If a change can't be made confidently, note it in `STATE.md` rather than gambling.
- **Preserve the previous task's a11y work byte-for-spirit:** the `aria-label`/`title` set on icon-only buttons, `focus-visible` ring, hover/keyboard parity, reduced-motion support, `tabular-nums` tables.
- DRY: shared primitives in `ui.tsx`; no per-page re-implementations of button/pill/banner styling where a primitive exists.
- `lucide-react` for icons; no hand-drawn SVGs or emoji-as-icons where a suitable icon exists.
- No hardcoded secrets, external URLs, or environment-specific values. All TS stays typed; follow existing code style.
- `backdrop-filter` is broadly supported in current evergreen browsers; a `@supports` fallback is not required, but glass surfaces must remain readable if blur fails (i.e. the translucent surface alone must not drop text below AA — the ≥ 70% opacity floor covers this).

## Test plan
- **Baseline:** run `flow gates` on the fresh branch before touching UI; record the result in `STATE.md`.
- **Automated:** `flow gates --record backvora-ui-premium-neutral-refresh` fully green (rc=0) before handoff (AC12).
- **Browser/runtime (Builder):** run the app locally (FastAPI backend + seeded data); inspect Login, Home, and every authenticated route at 390/768/1280/1440. Exercise: sidebar/drawer open-close + close-on-navigate, navigation to each route, logout, campaign detail article edit → save and edit → cancel, one regenerate click-path, order-row expand, verification-status display, at least one modal open/confirm/cancel (observe the glass treatment), one form submit, one table filter, one toast. Spot-check contrast on the new accent (white-on-pink-600 fill, pink-400 text on gray-800/900) and on one glass surface over bright content. Record what was exercised — and any check not performed as `NOT-VERIFIED` — in `STATE.md`. *(A relay agent can't hand-verify every pixel; anything not exercised ships UNVERIFIED and the Reviewer's ledger must flag it.)*
- **Reviewer:** re-run gates (`flow gates --hermetic` if sandboxed), verify ACs by code-read plus local browser inspection where possible; independently check AC1 hex values, AC2 contrast ratios, and the AC3 prohibitions; mark purely visual items not exercised as `NOT-VERIFIED`.
- **`flow verify` target:** none configured in `relay.config` (no `VERIFY_*` set) — runtime verification is the browser plan above.

## Likely-touched files
- `frontend-react/src/index.css` — the bulk of the color correction (gray + pink ramps, semantic tokens, scrollbar/selection, accent-usage comment block)
- `frontend-react/src/components/ui.tsx` — new `Button`, `StatusPill`/`Badge` primitives alongside `PageHeader`/`Card`/`EmptyState`
- `frontend-react/src/components/Layout.tsx` — accent retune on active nav/rail; optional sidebar/drawer/top-bar glass
- `frontend-react/src/components/Modal.tsx`, `Toast.tsx` — glass treatment per AC3
- `frontend-react/src/pages/*.tsx` (15 files) — primitive adoption, icon-size normalization, emoji-as-icon replacement, filter-bar/banner unification; mostly mechanical class edits

## Boundary note (values the Builder consumes from untouched code)
- `App.tsx` owns routing/auth wiring; the shell consumes its `<Outlet/>`/children contract — do not change route definitions or the auth guard.
- Status/state strings rendered as pills (campaign status, verification status, deal stages, inbox states, domain statuses) come from the backend API — style by value, never rename or remap them.
- `TargetSitesListPage` and `TargetSiteDetailPage` are named exports of `TargetSitesPage.tsx` — keep those export names intact.
- The lint gate (`scripts/relay_lint_baseline.sh`) counts total ESLint problems against a fixed baseline (287 errors / 11 warnings) — any new lint error fails the gate even though 287 pre-existing ones pass. The tests gate (`scripts/relay_pytest_changed.sh`) diffs against `master` for `*.py`/`backend/`/`tests/` changes — touch no Python and it stays green by skip.
- The semantic tokens in `index.css` are consumed by `Layout.tsx`/`Modal.tsx`/`Toast.tsx`/`ui.tsx` via Tailwind utilities that resolve through `@theme` — keep every existing semantic token name defined or those utilities silently break.

## Notes / open context
- Pre-refresh reference for AC1 values: `git show a6803d0:frontend-react/src/index.css`.
- The rejected palette is current `master` `index.css`: rose-cast neutrals (hue ~285°) and raspberry `pink-600 #c43d74`. R's rejection is the *palette*, not the previous task's structure — shell, drawer, primitives, density, responsiveness, and a11y are keepers.
- Pink was BackVora's accent before the previous refresh too (pages used Tailwind default `pink-*` utilities against the old neutral grays), which is why AC2 keeps the `pink-*` family and retunes values rather than introducing a new hue family — it also means zero accent class-sweeps.
- Known pre-existing bug, do not fix (behavior preservation): Domains text bulk-import 422 (`api.bulkImportDomains` sends `{domains, is_competitor}`; endpoint expects a bare array). See `relay.memory.md`.
- Inbox in a dev env without mail creds surfaces IMAP 500s via the error toast — pre-existing, expected.
