# SPEC — BackVora UI Visual Refresh

**Status:** Ready-for-Builder
**Architect:** Claude Fable 5 (rewrite after spec-check; supersedes the earlier Coder draft)
**Date:** 2026-07-02
**Task slug:** backvora-ui-visual-refresh

## Intent & Surface
- **What R wants:** BackVora's UI looks dated (flat dark gray, plain top nav, gray active states). Make it feel "fabulous" in a *serious product* sense — premium, modern, polished, dense, scannable, workflow-focused. A premium SaaS dashboard, not a marketing site and not decorative luxury.
- **Surface:** The React/Vite/Tailwind 4 frontend under `frontend-react`. Shell: `src/components/Layout.tsx`. Theme: `src/index.css`. Every routed page (full list in AC2). Shared components: `Modal.tsx`, `Toast.tsx`, plus buttons, inputs, selects, tables, cards, badges/status pills, filters/tabs, empty/loading/error states used across pages.
- **Where users access it:** Immediately on every route. Authenticated app is the priority; Login and public Home `/` must match the same product identity but get proportionally less effort.
- **Done looks like:** Dark-first premium admin UI with a desktop left-sidebar shell, refined (non-neon) pink as the BackVora brand accent, restrained teal/green/amber/red status colors, consistent components, and unchanged behavior everywhere.

## Design Direction (agreed with R — not optional)
1. **Dark-first.** The refreshed theme keeps a dark background as the default and only mode.
2. **Refined pink brand accent.** Pink stays the primary accent but must read premium, not neon — used for primary actions, active nav state, focus/brand moments. Not sprayed across every surface.
3. **Status palette.** Restrained teal/green/amber/red for success/progress/warning/danger states, defined once as theme tokens and reused.
4. **App shell.** Desktop (≥1024px): fixed left sidebar navigation with grouped nav items, active-route indication, and logout/settings access. Mobile/tablet (<1024px): a drawer or compact top bar + drawer that does not crowd content; the sidebar must not squash the page.
5. **Operational density.** Tables, lists, inbox rows, and campaign detail stay dense and scannable — comfortable-compact row heights, tabular data alignment, no oversized cards or whitespace showcases.

## Acceptance Criteria
All ACs are graded by code-read plus running the app locally. "Visible" means observable in a browser at the stated viewport.

- [ ] **AC1 — Sidebar shell.** `Layout.tsx` (or its replacement) renders a left sidebar at ≥1024px containing links to every authenticated route group (Dashboard, Domains, Target Sites, Campaigns, Competitors, Outreach, Deals, Inbox, Check Metrics, Settings) plus logout. The active route is visually distinct (accent treatment, not just a gray background). Below 1024px the sidebar collapses to a drawer or compact nav that is openable/closable and overlays or shifts content without clipping it.
- [ ] **AC2 — Full page coverage.** Every routed surface renders on the new theme with no leftover flat-gray-only treatment: `/` (Home), `/login`, `/dashboard`, `/domains`, `/domains/new`, `/domains/:id`, `/target-sites`, `/target-sites/:id`, `/campaigns`, `/campaigns/:id`, `/competitors`, `/outreach`, `/deals`, `/inbox`, `/check-metrics`, `/settings`. Note: `/target-sites` and `/target-sites/:id` are both exported from `src/pages/TargetSitesPage.tsx`.
- [ ] **AC3 — Theme tokens.** `src/index.css` defines named theme tokens (Tailwind 4 `@theme` variables or equivalent) for at minimum: page background, raised surface, border, primary/secondary text, muted text, brand accent (pink) with hover/active variants, success, warning, danger, info/teal, and focus ring. Pages/components consume these tokens (directly or via Tailwind utilities backed by them) rather than one-off hex values.
- [ ] **AC4 — Component consistency.** Buttons (primary/secondary/ghost/danger), inputs, selects, tables, cards, modals, toasts, badges/status pills, tab/filter controls, and empty/loading/error states share consistent radius, spacing, typography scale, border, shadow, and hover/active/disabled/focus treatments. Grading check: the same control type on any two pages looks the same.
- [ ] **AC5 — Campaign Detail preserved.** On `/campaigns/:id`, article preview, article editing (edit → save and edit → cancel), regenerate actions, order rows, verification status display/actions, and all modal flows behave exactly as before the refresh — same handlers, same API calls, same state transitions — while adopting the new visual system.
- [ ] **AC6 — Behavior preserved everywhere.** No route paths, redirects, auth guards, API calls, form submissions, or business logic change. `App.tsx` routing and auth behavior are untouched except (if needed) the shell component wrapping.
- [ ] **AC7 — Responsive.** At exactly 390px, 768px, 1280px, and 1440px viewport widths: navigation, tables/lists, buttons, filters, modals, and long labels do not overlap or clip important text, and there is no horizontal page scroll except inside intentionally scrollable data tables/containers.
- [ ] **AC8 — Accessibility.** Every interactive control shows a visible focus indicator when keyboard-focused; icon-only buttons have `aria-label` or `title`; body and table text meets WCAG AA contrast (≥4.5:1 for normal text, ≥3:1 for large text) against its surface; anything revealed on hover is also reachable/visible via keyboard focus.
- [ ] **AC9 — No decorative clutter.** Zero of the following anywhere in the diff: gradient orbs/blobs/bokeh, decorative hero sections inside the authenticated app, cards nested inside cards, or any in-app copy that explains/announces the redesign. Icons come from `lucide-react` where icons are used.
- [ ] **AC10 — Density preserved.** Dashboard metrics, domain/campaign/deal/target-site lists, and inbox rows show at least as many data rows/items per 1440px×900px screen as before the refresh (compare against the pre-refresh build; small deviations from row-height polish are fine, halving visible rows is not).
- [ ] **AC11 — Gates.** Baseline `flow gates` run and recorded *before* any UI change (so regressions are attributable), and `flow gates --record backvora-ui-visual-refresh` passes before handoff: `python -m pytest`, `cd frontend-react && npx tsc -b --noEmit`, `cd frontend-react && npm run build`, `cd frontend-react && npm run lint`.

## Out of Scope
- Backend/API changes of any kind; database or migration work.
- New features, new routes, changed auth behavior, changed business logic.
- Light mode / theme switching.
- Copy rewrites beyond labels needed for visual clarity.
- Deploying, pushing to GitHub, or integrating to `master` (human gate).
- Redesigning public Home `/` beyond bringing it onto the same tokens/identity — it must look consistent, but the authenticated app is the priority.

## Constraints
- **`index.css` gray-token override is a live wire.** The current `@theme` block remaps Tailwind's `gray-*` scale globally; every existing `bg-gray-*`/`text-gray-*` utility in ~6,800 lines of pages resolves through it. Changing those token values restyles the whole app at once — powerful, but verify no page becomes unreadable. Prefer adding new semantic tokens over silently re-meaning `gray-*` if the two would conflict.
- **`CampaignDetailPage.tsx` is 2,135 lines.** Restyle it with targeted, mechanical class edits (or by wrapping sections in shared components); do not restructure its state, handlers, or JSX logic. If a change there can't be made confidently, note it in `STATE.md` rather than gambling.
- Prefer shared components/utilities over repeated page-local styling (DRY); extraction is allowed only where it reduces duplication or makes the refresh coherent — no unrelated refactors.
- `lucide-react` for icons; no hand-drawn SVGs where a suitable icon exists.
- No hardcoded secrets, external URLs, or environment-specific values.
- All new/modified functions keep type hints/TS types; follow existing code style.

## Test Plan
- **Baseline:** run `flow gates` on the fresh branch before touching UI; record the result in `STATE.md`.
- **Automated:** `flow gates --record backvora-ui-visual-refresh` green before handoff (exact commands in AC11).
- **Browser/runtime (Builder):** run the app locally; inspect Login, public Home, and every authenticated route at 390px, 768px, 1280px, and 1440px. Exercise: sidebar/drawer open-close, navigation to each route, logout, campaign detail article edit → save, edit → cancel, regenerate action, verification status, order rows, at least one modal open/confirm/cancel, one form submit, one table filter/tab. Record what was exercised — and any check not performed as `NOT-VERIFIED` — in `STATE.md`.
- **Reviewer:** re-run gates, verify ACs by code-read plus local browser inspection where possible; mark purely visual/mobile items not exercised as `NOT-VERIFIED` in the ledger.

## Likely-Touched Files
- `frontend-react/src/index.css` (theme tokens)
- `frontend-react/src/components/Layout.tsx` (sidebar shell)
- `frontend-react/src/components/Modal.tsx`, `Toast.tsx`
- `frontend-react/src/pages/*.tsx` (all 15 files)
- New shared UI components under `frontend-react/src/components/` (e.g. button/badge/table primitives) as needed

## Boundary Note (values consumed from untouched code)
- `App.tsx` owns routing/auth wiring; the shell consumes its `<Outlet/>`/children contract — do not change route definitions or the auth guard.
- Status/state strings rendered as badges (campaign status, verification status, deal stages, inbox states) come from the backend API; style them by value, do not rename or remap them.
- `TargetSitesListPage` and `TargetSiteDetailPage` are named exports of `TargetSitesPage.tsx` — keep those export names intact.
