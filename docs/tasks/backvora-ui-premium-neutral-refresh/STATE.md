# Task State — backvora-ui-premium-neutral-refresh

> **Baton file.** Any agent taking over reads this top-to-bottom first, then acts.
> Append to the log; never delete history. One owner at a time.

## 🎯 Baton
- **Pipeline:** Architect → Builder → Reviewer ⇄ Builder → Human → **Done**
- **Current owner:** Done
- **Status (one line):** Round-5 review passed: the selected/active tint-strength must-fix is closed, Domains/sidebar read neutral, rendered React source is free of `purple-*` classes, and hermetic gates are green.
- **Round:** 5 (round-4 review returned one color correction must-fix)
- **Code location:** branch `feature/backvora-ui-premium-neutral-refresh` · worktree `/tmp/backvora-premium-neutral` · base commit `a3251e7` (current `master` tip) · reviewed code head `5c34e3f`
- **Gates:** rc=0 @ c0d3bcb (tests=pass typecheck=pass build=pass lint=pass) mode=hermetic dirty=no 2026-07-03
  <!-- `flow gates --record` writes this slot for you; whoever runs gates last before a handoff records here (--record, or paste the line verbatim). Leave the placeholder if none run yet (status shows "gates not recorded", never a guessed pass). -->
- **Spec:** ./SPEC.md  ← read it, it's the contract

## ▶️ Next action (for the current owner)
🟢 NO FIX NEEDED — review passed (round 5). Next: human integrates (squash-merge + deploy).

Round-5 scoped review verified the round-4 must-fix is closed: selected/active tint fills are ≤15% or neutral, the Domains table/sidebar are neutral-first rather than violet/maroon, React TSX and built output have no rendered `purple-*` class strings, and hermetic gates remain green.

## ✅ Gate status (latest)
Record the exact command + result. Reviewer re-runs these (`flow gates`) and notes any divergence.

| gate | command | result | when |
|------|---------|--------|------|
| tests | `bash scripts/relay_pytest_changed.sh` | ✅ pass (no Python/backend changes → auto-skip green) | 2026-07-03 |
| typecheck | `cd frontend-react && npx tsc -b --noEmit` | ✅ pass (no output) | 2026-07-03 |
| build | `cd frontend-react && npm run build` | ✅ pass (`✓ built in 2.5s`; pre-existing >500kB chunk warning) | 2026-07-03 |
| lint | `bash scripts/relay_lint_baseline.sh` | ✅ pass (287 errors / 11 warnings — exactly at baseline, zero new) | 2026-07-03 |

<!-- Builder: paste output tail (or full failure) below so the Reviewer sees evidence, not a claim. -->
```
BASELINE on fresh branch BEFORE any UI change (AC12), after `npm ci` in the drive worktree:
- **Gates:** rc=0 @ a3251e7 (tests=pass typecheck=pass build=pass lint=pass) mode=full dirty=no 2026-07-03
(first baseline attempt was red for env reasons only: node_modules absent in the fresh worktree
— `@eslint/js` not found; green after `npm ci`, zero source changes)

FINAL run tail (flow gates, post-build):
  ✓ built in 2.53s
  build      ✅
  ── lint: (.) bash scripts/relay_lint_baseline.sh
  eslint baseline check: 287 errors, 11 warnings (accepted baseline <= 287/11)
  lint       ✅
  gates: all green
Note: mid-build the count briefly hit 289 (react-refresh/only-export-components on non-component
exports in ui.tsx); fixed properly by moving buttonClasses/statusTone/tone maps to components/styles.ts.

ROUND 2 FINAL (flow gates --record backvora-ui-premium-neutral-refresh, full mode, at 60be1db):
  ✓ built in 2.54s
  build      ✅
  ── lint: (.) bash scripts/relay_lint_baseline.sh
  eslint baseline check: 287 errors, 11 warnings (accepted baseline <= 287/11)
  lint       ✅
  gates: all green
(the no-slug `flow gates --record` run passed but failed to record — two in-flight tasks; re-ran with
the explicit slug, same as the Reviewer had to)

ROUND 3 (flow gates --record backvora-ui-premium-neutral-refresh, full mode, at e9b3ce2, fresh
worktree after `npm ci` — same env-only red as the round-1 baseline before install):
  ✓ built in 2.54s
  build      ✅
  ── lint: (.) bash scripts/relay_lint_baseline.sh
  eslint baseline check: 287 errors, 11 warnings (accepted baseline <= 287/11)
  lint       ✅
  gates: all green

ROUND 4 (manual Builder correction after live preview rejection, `flow gates --hermetic`, dirty before commit):
  tests      ✅ (frontend-only branch; Python/backend/tests unchanged)
  typecheck  ✅
  build      ✅ (`✓ built in 2.47s`; pre-existing >500kB chunk warning)
  lint       ✅ (287 errors / 11 warnings, exactly within accepted baseline)
  gates: all green
```

## 📜 Activity log (append-only, newest at bottom)
- `2026-07-03` **[→ Architect]** R direction: old BackVora colors as the base, with a more premium modern accent system; keep useful shell/component improvements from the previous refresh; spec selective glass/polished controls, not noisy full-app glass.
- `2026-07-03` **[Architect / Claude Fable 5]** Recon done (current `index.css` rose-cast tokens + semantic vocabulary; old ramp confirmed at `a6803d0`; ~290 `pink-*` usages all resolve through `@theme`; icons already 100% lucide, remaining emoji-as-icons located; gate scripts read — frontend-only branch can be fully green). SPEC written: 12 ACs covering exact neutral hex restoration, bounded accent tiers with contrast floors, selective-glass rules, Button/StatusPill primitives, icon normalization, behavior/responsive/a11y/density preservation, and green `flow gates --record`. Baton → Builder.
- `2026-07-03` **[Builder / Claude Fable 5]** Built on `feature/backvora-ui-premium-neutral-refresh` off `a3251e7` (head `3f24268`): neutral ramp restored verbatim, pink retuned to ~334° with measured contrast floors, `glass` utility on overlay chrome only, Button/StatusPill/ResultBanner/LoadingState primitives + shared `styles.ts` tone/class maps, emoji→lucide, page headers unified. Baseline gates recorded pre-change; final gates fully green (287/287 lint baseline, zero new). Runtime-exercised in headless Chromium (all routes, drawer, modals, filter, delete flow, form submit, toast, focus ring, 390/768/1280/1440). Baton → Reviewer.
- `2026-07-03` **[Reviewer / Codex GPT-5]** Re-ran hermetic gates green (`tests/typecheck/build/lint`, recorded after explicit task slug). Review found 2 must-fix AC gaps: AC2 still has solid pink fills outside primary/nav uses, and AC4 did not adopt/align shared Button treatment on Domain Detail standard buttons. Baton → Builder, round 2.
- `2026-07-03` **[Builder / Claude Fable 5]** Round-2 fixes at `60be1db` (5 source files + relay.memory). Finding #1: budget progress bars → neutral `gray-400`; ready-domain selected chips → `pink-600/15` tint + `pink-300` text (hover pink fill removed); anchor chips keep their type hue with a neutral white ring for selection; TargetSites quick-insert `hover:bg-pink-600` → gray. Finding #2: every standard button in `DomainDetailPage` now renders through `Button` (new shared `xs` size for micro row actions; purple Inbox/Grab Rules mechanically aligned; control icons w-4). Runtime-exercised in headless Chromium (login, Domain Detail flows incl. price-form submit through converted Button, Campaigns bar color probe, cross-page variant-identity probe, 390/1440 no-hscroll). Full gates green + recorded. Baton → Reviewer.
- `2026-07-03` **[Reviewer / Codex GPT-5]** Round-2 re-review: hermetic gates green, Domain Detail Button adoption verified, prior selected-chip/progress-bar fixes verified, but AC2 still has one secondary Ready Domains `Refresh` utility button using solid `bg-pink-600`. Max review rounds exhausted; baton → human.
- `2026-07-03` **[→ Builder]** Human authorized one more drive loop. Scope is narrow: fix the round-2 AC2 must-fix by changing CampaignDetailPage Ready Domains Refresh from solid pink to neutral secondary/shared secondary treatment, then run and record gates before Reviewer.
- `2026-07-03` **[Builder / Claude Fable 5]** Round-3 narrow fix at `e9b3ce2` (1 line): Ready Domains `Refresh` → neutral secondary classes identical to the adjacent accepted `Apply` button. Runtime-probed in headless Chromium (computed bg `rgb(51,51,51)`; tab's at-rest pink-fill census = primary `Add` only; zero console errors). Full gates green + recorded. Baton → Reviewer for a scoped round-3 review of this single commit.
- `2026-07-03` **[Reviewer / Codex GPT-5]** Scoped round-3 review passed: verified `CampaignDetailPage.tsx:885` Ready Domains `Refresh` is neutral secondary, reran hermetic gates green after installing locked frontend dependencies, and closed the remaining AC2 finding. Baton → Done for human integration.
- `2026-07-03` **[→ Builder]** Human rejected live preview: sidebar and Domains table/buttons still read violet. Reopen for focused color correction only. Requirements: restore original BackVora color feel, not just gray ramp. Use old Tailwind default pink ramp or original pre-refresh accent behavior; remove burgundy/violet sidebar active tint; active sidebar/nav should be neutral gray like old active nav, with at most a tiny pink rail/icon if not visually dominant. Replace literal purple/violet controls (bg-purple-*, text-purple-*) with original neutral or existing non-violet status colors. Domains table must read neutral gray/black first; no violet/maroon wash. Keep modern shell/layout/components. Do not integrate, push, or deploy. Visual evidence: /tmp/backvora-domains-violet-feedback.png.
- `2026-07-03` **[Builder / Coder manual fallback]** Round-4 color correction built after stale RelayFlow/Claude attempts made no source progress: restored Tailwind default pink token values, changed sidebar active nav from pink tint/rail to neutral `bg-gray-700 text-white`, removed the logo's pink-tinted square, and replaced all React source `purple-*` classes with neutral secondary or teal/status alternatives. `rg "purple-" frontend-react/src -g "*.tsx"` returns no matches. Hermetic gates green. Baton → Reviewer.
- `2026-07-03` **[Reviewer / Codex GPT-5]** Round-4 review: hermetic gates green, Tailwind-default pink ramp and neutral sidebar active state verified, and `purple-*` rendered React class scan clean. Found 1 must-fix AC2 gap: selected/active pink tints still exceed the 15% ceiling in multiple surfaces. Baton → Builder, round 5.
- `2026-07-03` **[Builder / Coder]** Round-5 tint-strength fix: reduced flagged selected/active pink washes to ≤15% or neutralized them, including campaign mode buttons, selected Inbox rows, selected/preferred Domain Detail cards, selected Domains rows, and the Domains table resize hover. No API, layout, or behavior changes. Hermetic gates green on the dirty worktree.
- `2026-07-03` **[Reviewer / Codex GPT-5]** Round-5 scoped review passed: verified the round-4 AC2 tint-strength finding is closed, React source has no rendered `purple-*` classes, Domains/sidebar color treatment is neutral-first, built output scan is clean, and hermetic gates are green/recorded. Baton → Done.

## 🔨 Build notes (Builder → Reviewer; latest round)

### Round 5 (reviewer finding: selected/active tints above AC2 ceiling)
- **What changed:**
  - `CampaignsPage.tsx` and `CampaignDetailPage.tsx`: campaign mode selected states `bg-pink-600/20` → `bg-pink-600/15`.
  - `InboxPage.tsx`: selected email row `bg-pink-600/20 ring-pink-500/50` → `bg-pink-600/15 ring-pink-500/30`.
  - `DomainDetailPage.tsx`: primary/preferred cards `bg-pink-900/20 border-pink-700` → `bg-pink-600/10 border-pink-600/30`; the stronger preferred badge wash `bg-pink-900/50` → `bg-pink-600/15`.
  - `DomainsPage.tsx`: selected row `bg-pink-900/20` → `bg-pink-600/10`; column-resize hover `hover:bg-pink-500/50` → neutral `hover:bg-gray-500/40` so the Domains table stays neutral-first.
- **Verification performed so far:**
  - `rg "pink-[0-9]+/(2[0-9]|[3-9][0-9])|purple-" frontend-react/src -g "*.tsx"` shows no active/selected tint over the 15% ceiling and no rendered React `purple-*` source classes; remaining `/30` matches are rings/borders/focus states, not fills.
  - `flow gates --hermetic` passed: tests/typecheck/build/lint all green (`✓ built in 2.50s`; lint baseline 287 errors / 11 warnings, no new).
- **Scope deliberately held:** no routing, API, table behavior, data loading, or layout structure changes.

### Round 4 (live-preview color rejection: "sidebar/domains table/buttons still read violet") — manual fallback
- **What changed:**
  - `frontend-react/src/index.css`: pink ramp restored to Tailwind's default values (`pink-400 #f472b6`, `pink-500 #ec4899`, `pink-600 #db2777`, etc.), matching the original app's implicit Tailwind palette instead of the custom darker/more violet ramp.
  - `frontend-react/src/components/Layout.tsx`: active sidebar/nav state now uses the old neutral active feel (`bg-gray-700 text-white`) instead of `bg-pink-600/15` plus pink rail; logo icon no longer sits inside a pink-tinted square.
  - Removed rendered React `purple-*` UI classes from Domains, Domain Detail, Campaign Detail, Inbox, and Target Sites. Special purple action buttons are neutral secondary (`bg-gray-700 hover:bg-gray-600`); anchor topical/status color moved to teal where a distinct category color is needed; suggestion panels use neutral gray.
- **Verification performed:**
  - Captured the rejected authenticated Domains screenshot at `/tmp/backvora-domains-violet-feedback.png` before changes.
  - `rg "purple-" frontend-react/src -g "*.tsx"` returns no matches after changes.
  - `flow gates --hermetic` passed: tests/typecheck/build/lint all green.
- **Scope deliberately held:** no routing, API, table behavior, or layout structure changes; only theme tokens and color classes.

### Round 3 (human-authorized narrow fix for round-2 finding #1) — head `e9b3ce2`
- **The fix (one line):** `CampaignDetailPage.tsx:885` Ready Domains toolbar `Refresh`:
  `bg-pink-600 hover:bg-pink-700` → `bg-gray-700 hover:bg-gray-600`. Deliberately byte-identical to
  the adjacent `Apply` button (line 919, same toolbar, same `px-3 py-1.5 … rounded text-sm`
  geometry) — the mechanical secondary idiom the round-2 review already accepted for this file
  (which has AC4's mechanical exception; converting to the `Button` component was not required and
  would have been a larger structural touch than the finding asked for).
- **Nothing else changed.** No other source files; scope held to the single finding.
- **Runtime-verified (local FastAPI from the main tree's env/DB + vite from this worktree, gstack
  headless Chromium):** login → `/campaigns` → campaign detail → Ready Domains tab; computed style of
  `Refresh` = `rgb(51,51,51)` (gray-700 = restored neutral `#333333`); at-rest solid `pink-600` fill
  census on that tab = **1** (the primary `Add` button — the allowed tier, matching the round-2
  accepted census); zero console errors. Screenshot at `/tmp/ready-domains-refresh-fixed.png`.
  A throwaway QA login user was created in the dev DB for the probe and deleted afterwards.
- **Process note:** the round-2 baton (owner → human) was resolved by the human's dispatch: an
  uncommitted STATE edit in the previous round's worktree flipped owner → Builder with the log line
  "Human authorized one more drive loop", which I committed as `0a482c3` before building so the
  authorization survives in history.

### Round 2 (fixes for the two must-fix findings) — head `60be1db`
- **Finding #1 (AC2 accent tiers) — fixed at every flagged site plus two same-pattern strays:**
  - Budget progress-bar fills (`CampaignsPage.tsx:232`, `CampaignDetailPage.tsx:578`): `bg-pink-600` → `bg-gray-400` (neutral data-viz at rest; runtime-probed `rgb(163,163,163)` on /campaigns).
  - Ready-domain link-type chips (`CampaignDetailPage.tsx:971`): selected state `bg-pink-600 ring-2 ring-pink-400` → `bg-pink-600/15 text-pink-300 ring-1 ring-inset ring-pink-600/30` (the same tint/border vocabulary as the accepted `PILL_TONES.brand`); unselected hover `hover:bg-pink-600` → `hover:bg-gray-600`.
  - Anchor chips (`CampaignDetailPage.tsx:1818`, `1914`): selected no longer overrides the informative anchor-type status hue with pink — chips keep their type color and selection is a neutral `ring-2 ring-white/80` (also untangles the old always-on `ring-white/30` class clash).
  - Same-pattern stray not in the findings list: `TargetSitesPage.tsx:451` quick-insert chips `hover:bg-pink-600` → `hover:bg-gray-600`.
  - **Kept, deliberately:** the toggle-switch track `peer-checked:bg-pink-600` (`CampaignDetailPage.tsx:1261`) — a checked boolean control, i.e. the checkbox/radio `accent-color` tier of AC2, not a selected-state tint; and solid pink on actual primary buttons (incl. CampaignDetail's, under its mechanical exception). Runtime probe of campaign detail at rest: the only `pink-600` fills on the page are two primary buttons.
- **Finding #2 (AC4 Domain Detail shared Button) — full sweep:**
  - Every standard button in `DomainDetailPage.tsx` now renders through `Button` (primary/secondary × sm/md/xs): domain-name Save/Cancel, Update from Ahrefs, contact Edit/Save, Grab Contacts/Deep Grab, Save All / per-email Save/Dismiss, form Preview/Submit, preview-modal Confirm/Cancel, rules Edit + Save Rules, price Types/Add + Save/Cancel, payment Add + Save/Cancel, notes Edit/Save/Cancel, email-template chips, send-email Cancel/Send, link-types Add. Submit buttons pass `type="submit"` explicitly (Button defaults to `type="button"`).
  - Special-hue purple buttons (Inbox, Grab Rules) mechanically aligned to the Button geometry classes — the exact idiom round 1 used for emerald/purple on Domains/TargetSites/Inbox.
  - Icon sizes: all control icons w-4 (was w-3/w-3.5), incl. row-action Pencil/Trash2/Star/Send; link-type delete `×` glyph → lucide `X`. Two remaining w-3 are non-control micro-indicators inside status badges (solvingStatus spinner, "Preferred" star), matching round 1's indicator rule.
- **Deviations / judgment calls (round 2):**
  - **`styles.ts` gained a Button size `xs`** (`px-2 py-1 text-xs rounded`). AC4 names sm/md; xs is additive, shared (not page-local), and preserves the existing micro-density of inline row actions (per-email Save/Dismiss, form Preview/Submit) instead of inflating them to sm. Flag if you'd rather they become sm.
  - Anchor-chip selection uses a neutral white ring rather than an accent tint because the chip fill itself is an informative status hue (anchor type) that a tint overlay would destroy; the reviewer's remedy text ("neutral/status fills") allows this.
- **Runtime exercised (round 2; local FastAPI + vite dev, gstack headless Chromium):** login → /domains; Domain Detail: all sections render zero console errors, contact Edit→Cancel toggle, Types modal open/close, price form open → custom type + price → submit through the converted `Button type="submit"` → row rendered + toast → cleaned up via API; computed-style probes: primary/secondary sm on Domain Detail identical to DomainsPage sm (`4px 12px | 6px | 14px`, pink-600/#333 fills), purple buttons same geometry; Campaigns budget fill `rgb(163,163,163)`; campaign detail at-rest pink-fill census = primary buttons only; no horizontal scroll at 390 and 1440.
- **NOT-VERIFIED at runtime (code-read + tsc only):** ready-domain selected-chip and anchor-chip selected states (seed DB has 0 ready domains / no anchor pool — the class strings are mechanical); TargetSites quick-insert hover. Pre-existing, not mine: `POST /link-prices/types/add` 500s (`no such table: link_type_presets` in the dev DB — recorded in relay.memory; the price create itself succeeds).

### Round 1 (kept for context)
- **What I built:**
  - **AC1:** `index.css` gray ramp restored verbatim to the `a6803d0` values (50→950). Semantic token names all kept, same mappings (bg→900, surface→800, surface-2/line→700, ink→100, ink-dim→400, ink-mute→500). Scrollbar/selection resolve through tokens → zero saturation everywhere.
  - **AC2:** new pink ramp `300 #f5aacb / 400 #ef77ae / 500 #e4508f / 600 #d02e72 / 700 #ad2560 / 800 #8a1e4e / 900 #5d1535 / 950 #36091d` — hue 332–335°. Measured (WCAG relative luminance): white on 600 = **4.87:1**; 400 on gray-800 = **6.56:1**, on gray-900 = **7.47:1**; ring (500) on gray-900 = 5.51:1. Accent-tier comment block at top of `@theme`. Status ramps kept as-is (spec allows). Removed at-rest accent decoration: pink page-header icons (Campaigns/Target Sites/Inbox/Check Metrics h1s) replaced by plain `PageHeader`.
  - **AC3:** one `@utility glass` in `index.css` (85% gray-800 surface, 12px blur, inset white/6 top highlight + elevation shadow). Applied ONLY to: Modal panel, Toast, mobile drawer panel, mobile sticky top bar, Domains column dropdown, DomainAdd owner-suggestion dropdown. Backdrops (modal + drawer) got `backdrop-blur-sm`. Desktop sidebar left solid (nothing renders beneath a fixed sidebar — glass would be a no-op; spec marks it optional).
  - **AC4:** `Button` (primary/secondary/ghost/danger × sm/md) in `ui.tsx`; `buttonClasses()` in new `components/styles.ts` for `<Link>`s styled as buttons. Adopted across all pages for standard buttons.
  - **AC5:** `StatusPill` (tone-tinted, rounded-full) + one shared `statusTone()` map in `styles.ts` covering domain/campaign/order status strings. Adopted: Domains table, Domain detail header, Campaigns cards, Campaign detail (header, recent orders, orders tab). Deals/Outreach are "coming soon" pages with no pills; Inbox has no status pills — nothing to convert there.
  - **AC6:** emoji→lucide: 📧/📝/⚠️ row indicators → `Mail`/`FileText`/`ShieldAlert` (title+aria-label kept); ✅/❌/⏳/✓ prefixes stripped and banners now render `ResultBanner` (tone-styled + lucide icon); ⚠️ CAPTCHA (DomainDetail) → `ShieldAlert`; 💳 → `CreditCard`; 2 literal ✅/❌ toast strings in CampaignDetail stripped (Toast has its own icons). In-control icons normalized to `w-4 h-4`; nav + brand icons to `w-5 h-5`.
  - **AC7:** `filterFieldClass` (styles.ts) for filter bars (Domains, Inbox search); `LoadingState` (one spinner treatment) replaces mixed text/Loader loading on Domains/Campaigns/Competitors/TargetSites/Inbox; `EmptyState` adopted on Domains table, Campaigns, TargetSites, Inbox (Competitors already had it); `ResultBanner` unifies result/error banners (Domains, Competitors, Dashboard, Settings, DomainAdd dupe warning).
  - **AC12:** baseline recorded before any UI change; final `flow gates --record` green (line in Baton).
- **Deviations from spec / judgment calls:**
  - **New file `components/styles.ts`** (not in likely-touched list): required — exporting `buttonClasses`/`statusTone` from `ui.tsx` trips `react-refresh/only-export-components` (2 new lint errors → gate red). Component file stays components-only; class/tone vocabulary lives beside it.
  - **Streaming-progress state shape:** `bulkActionResult` (DomainsPage) gained a `busy?: boolean` so ⏳-prefixed strings could become a spinner banner; CompetitorsPage `fetchResult` changed `string` → `{tone, message}`. UI-state only, same render sites, no API/handler changes.
  - **Special-hue buttons kept, mechanically aligned:** emerald "Grab Contacts", purple "Check Adult" (Domains), purple "Suggest Next Anchor" (TargetSites), purple "Scan Replies" (Inbox) are not one of the four spec'd variants; they keep their hue (operator color-coding) with Button-matching geometry/disabled classes. Adding variants beyond the spec'd four felt like scope creep — flag if you disagree.
  - **Tone collapse on order statuses:** 11 order-status colors map onto 6 tones (published/live→success; payment_sent/paid/monitored/content_ready→info; sent/pending_review→warning). Some formerly-distinct hues (purple published, orange paid) now share tones. Strings untouched.
  - **gray-500 captions are 3.67:1 on gray-800** (old-app parity): AC1 pins `#737373` verbatim, so `text-gray-500` captions/timestamps sit below the 4.5:1 AA floor — exactly as the original palette did. Body/table text (gray-100/300/400) all clear AA (gray-400 = 6.9:1). Unresolvable without breaking AC1; noting per AC10.
  - **Micro-indicators kept at w-3:** sort chevrons in table headers and a few inline ▼/▶ text arrows; they're indicators, not control icons. The "one size" rule was applied to button/row/pill icons (w-4).
- **Runtime exercised (local FastAPI + seeded data, headless Chromium at 390/768/1280/1440):** login → redirect; every route incl. campaign detail + all 4 tabs (zero console errors except Inbox's pre-existing IMAP 500/401, expected per spec); sidebar active state; drawer open + close-on-navigate (glass verified); Import modal open/cancel (glass verified); table search filter narrows rows; row delete → glass confirm modal → toast → row removed; Target Sites create form submit → toast + card renders; keyboard Tab → `:focus-visible` outline computes `rgb(228,80,143)` (pink-500); no horizontal page scroll at 390/768/1280/1440; logout → /login.
- **Uncertain / please look at (NOT-VERIFIED at runtime):**
  - Campaign detail **article edit→save / edit→cancel, regenerate, order-row expand, verification status** — no orders/articles seedable without content-generation APIs. Code-read: my only edits in that file are 3 pill renders + 2 toast strings; handlers/JSX untouched. Please code-verify.
  - Toast/banner **glass over bright content** — app content is dark; worst-case AA was computed (85% surface over white ⇒ gray-100 text 10.1:1) not observed.
  - Rows-per-screen ≥ master at 1440×900 — row paddings and pill height (py-0.5, 16px content) unchanged by code-read; not pixel-compared against a master build.
  - Check Metrics with a real Ahrefs key; email send paths (no SMTP creds).

## 🔎 Review findings (Reviewer → Builder; round 1)
| # | sev | tag | file:line | problem | why it matters |
|---|-----|-----|-----------|---------|----------------|
| 1 | high | must-fix | `frontend-react/src/pages/CampaignsPage.tsx:232` | AC2 says pink fills are limited to primary buttons and the active-nav indicator, while selected/active states should use tints at <=15% opacity. Solid `bg-pink-600` still appears on non-primary at-rest/data UI, including campaign budget progress bars (`CampaignsPage.tsx:232`, `CampaignDetailPage.tsx:578`) and selected/hover chips (`CampaignDetailPage.tsx:971`, `1818`, `1914`). | This violates the core "premium accent, restrained" contract: the app can still read as pink-accent-sprayed outside primary actions, exactly what AC2 was meant to prevent. Replace these with neutral/status fills or low-opacity accent tints where they are true selected states. |
| 2 | high | must-fix | `frontend-react/src/pages/DomainDetailPage.tsx:367` | AC4 requires standard buttons across pages to adopt the shared Button primitive, with the explicit mechanical-exception only for `CampaignDetailPage.tsx`. `DomainDetailPage.tsx` still has many page-local standard action buttons (`Save`/`Cancel`/`Update from Ahrefs`/`Add`/`Send`, e.g. lines `367`, `381`, `450`, `515`, `1066`, `1089`, `1110`, `1152`, `1207`, `1223`) and mixed icon sizes (`w-3`, `w-3.5`). | The shared primitive is the spec's mechanism for consistent radius, padding, disabled/active/focus treatment, and icon sizing. Leaving a major authenticated route on one-off button classes fails the "same variant on any two pages looks identical" grading check. |

_tags: must-fix · nice-to-have · question · intent_

## 🔎 Review findings (Reviewer → human; round 2)
| # | sev | tag | file:line | problem | why it matters |
|---|-----|-----|-----------|---------|----------------|
| 1 | high | must-fix | `frontend-react/src/pages/CampaignDetailPage.tsx:885` | AC2 allows solid pink fills only on primary buttons and the active-nav indicator. The Ready Domains toolbar `Refresh` control is a secondary utility action but still uses `bg-pink-600 hover:bg-pink-700`. | This leaves a non-primary solid accent fill in the app after the round-2 accent cleanup. The spec's core goal is restrained accent use; this control should be neutral secondary styling or the shared secondary `Button` treatment. |

## 🔎 Review findings (Reviewer → human; round 3)
No must-fix findings. The round-2 AC2 finding is closed by the round-3 one-line source fix.

## 🔎 Review findings (Reviewer → Builder; round 4)
| # | sev | tag | file:line | problem | why it matters |
|---|-----|-----|-----------|---------|----------------|
| 1 | high | must-fix | `frontend-react/src/pages/CampaignsPage.tsx:300` | AC2 caps active/selected accent tints at ≤15% opacity, but several selected/active surfaces still use stronger pink treatment: campaign mode buttons use `bg-pink-600/20` (`CampaignsPage.tsx:300`, `CampaignDetailPage.tsx:1613`), selected inbox rows use `bg-pink-600/20 ring-pink-500/50` (`InboxPage.tsx:294`), and selected/preferred domain-detail cards use `bg-pink-900/20 border-pink-700` (`DomainDetailPage.tsx:470`, `1111`). | The round-4 task exists because the live app still read violet/maroon. These over-strength pink selected states keep visible color wash outside the allowed accent tiers and fail AC2's explicit tint ceiling. Reduce them to ≤15% tint/border treatment or neutral/status styling. |

## 🔎 Review findings (Reviewer → human; round 5)
No must-fix findings. The round-4 AC2 tint-strength finding is closed by the round-5 source changes.

## 📋 Verification ledger (Reviewer; per AC — test / code-read / runtime / NOT-VERIFIED)
| AC | method | note |
|----|--------|------|
| AC1 | code-read | `index.css` gray ramp matches the required pre-refresh hex values exactly; semantic tokens remain defined and scrollbar/selection use tokenized neutrals. |
| AC2 | code-read | Contrast/ramp comment and hue range pass by code-read. Round-1 progress bars, selected chips, and quick-insert hover were fixed, but a secondary Ready Domains `Refresh` button still uses solid `bg-pink-600`. See round-2 finding #1. |
| AC3 | code-read | `rg glass/backdrop-blur` shows glass only in the single utility plus Modal, Toast, mobile top bar/drawer/backdrops, and two dropdowns; no gradient orb/blob/bokeh hits in the diff. |
| AC4 | code-read | Round-2 fix verified: Domain Detail standard text/action buttons now render through `Button`; remaining raw buttons are dropdown options, icon-only row/close actions, or documented special-hue buttons aligned to the shared geometry. |
| AC5 | code-read | `StatusPill` and shared `statusTone()` cover domain/campaign/order status displays touched by the build; Deals/Outreach are coming-soon pages with no status pills, Inbox has none. |
| AC6 | code-read | Required Domains row indicators, result-banner prefixes, CAPTCHA icon, payment icon, and toast check/cross prefixes were replaced/stripped; lucide remains the icon source. |
| AC7 | code-read | Shared filter/loading/empty/result treatments are present on the changed list pages; no automated visual test was available. |
| AC8 | code-read | `App.tsx` untouched; API calls/route exports reviewed for changed files. Campaign-detail behavior-heavy handlers were not reworked beyond status/toast render edits. |
| AC9 | NOT-VERIFIED | Reviewer did not run browser viewport checks at 390/768/1280/1440; Builder reported headless coverage, but I did not independently reproduce it. |
| AC10 | code-read | Global `:focus-visible` ring remains tokenized to `--color-ring`; icon-only labels/titles in touched controls were preserved where reviewed. Rows-per-screen and glass-over-bright-content were not independently runtime-verified. |
| AC11 | code-read | Diff contains no decorative hero/orb/blob/bokeh additions and no redesign-announcement copy. |
| AC12 | test | Ran `flow gates --hermetic`; tests/typecheck/build/lint all passed. Final recorded hermetic run is in the Baton gate slot above. |

## 🚧 Escalations / open questions (→ human)
- NOT-VERIFIED by Reviewer: responsive browser checks at 390/768/1280/1440, rows-per-screen parity, and glass/banner contrast over bright content. Builder reported runtime coverage, but I did not independently run a browser session.

## 📋 Verification ledger (Reviewer; round 3 scoped)
| AC | method | note |
|----|--------|------|
| AC1 | code-read | Not re-opened in the human-authorized scoped review; prior round-2 review remained unchanged. |
| AC2 | code-read | Verified `CampaignDetailPage.tsx:885` changed Ready Domains `Refresh` from solid `bg-pink-600 hover:bg-pink-700` to neutral `bg-gray-700 hover:bg-gray-600`; focused `rg` scan confirms the flagged secondary utility control no longer uses a solid accent fill. |
| AC3 | code-read | Not re-opened in the human-authorized scoped review; the round-3 source diff only touches one button class string. |
| AC4 | code-read | Not re-opened in the human-authorized scoped review; the changed control remains in `CampaignDetailPage.tsx`, where the spec allows mechanical class alignment. |
| AC5 | code-read | Not re-opened in the human-authorized scoped review; no status-pill code changed. |
| AC6 | code-read | Not re-opened in the human-authorized scoped review; no icon code changed. |
| AC7 | code-read | Not re-opened in the human-authorized scoped review; no table/filter/state code changed beyond the flagged secondary button class. |
| AC8 | code-read | `Refresh` still calls `loadReadyDomains()`; only the class string changed, so behavior is preserved for the scoped fix. |
| AC9 | NOT-VERIFIED | Reviewer did not run independent browser viewport checks at 390/768/1280/1440 in round 3. |
| AC10 | code-read | The scoped class change does not remove focus handling, labels, or text; broader rows-per-screen and glass-over-bright-content checks remain not independently runtime-verified by Reviewer. |
| AC11 | code-read | The round-3 source diff adds no decorative clutter or redesign copy. |
| AC12 | test | Ran `flow gates --hermetic`: tests/typecheck/build/lint passed after `npm ci` installed the locked frontend dependencies. Final recorded hermetic run is in the Baton gate slot above. |

## 📋 Verification ledger (Reviewer; round 4 scoped)
| AC | method | note |
|----|--------|------|
| AC1 | code-read | `index.css` gray ramp still matches the required original neutral values exactly. |
| AC2 | code-read | Pink ramp is restored to Tailwind default values and contrast checks pass (`white/pink-600` 4.60:1, `pink-400/gray-800` 6.57:1, `pink-400/gray-900` 7.48:1), but selected/active tints above 15% remain. See round-4 finding #1. |
| AC3 | code-read | `rg gradient/orb/blob/bokeh/hero` in touched frontend sources found no prohibited decorative treatment; glass recipe remains scoped to overlay chrome by code-read. |
| AC4 | code-read | Not re-opened structurally in round 4; the color correction did not change shared `Button` adoption except neutralizing former purple special buttons. |
| AC5 | code-read | Not re-opened in round 4; no backend status strings or shared status-tone mapping changed. |
| AC6 | code-read | `rg "purple-" frontend-react/src -g "*.tsx"` returns no rendered React source classes; former purple special controls use neutral/teal alternatives. Icon source remains lucide in touched files. |
| AC7 | code-read | Domains selected-row and selected-toolbar color treatments were checked by code-read; no table/filter behavior changed. |
| AC8 | code-read | `App.tsx` remains untouched; round-4 diff is limited to theme/sidebar/color classes and does not alter route/API handlers. |
| AC9 | NOT-VERIFIED | Reviewer did not run independent browser viewport checks at 390/768/1280/1440 in round 4. |
| AC10 | code-read | Global `:focus-visible` remains tokenized to `--color-ring`; round-4 class edits do not remove labels/titles. Rows-per-screen and glass-over-bright-content were not independently runtime-verified. |
| AC11 | code-read | No decorative hero/orb/blob/bokeh additions or redesign-announcement copy found in the round-4 review scans. |
| AC12 | test | Ran `flow gates --hermetic`; tests/typecheck/build/lint all passed. Final recorded hermetic run is in the Baton gate slot above. |

## 📋 Verification ledger (Reviewer; round 5 scoped)
| AC | method | note |
|----|--------|------|
| AC1 | code-read | Not re-opened in round 5; `index.css` still carries the original neutral gray ramp and Tailwind default pink ramp verified in round 4. |
| AC2 | code-read | Verified the round-5 fixes: campaign mode selected states are `bg-pink-600/15`; Inbox selected row is `bg-pink-600/15` with ring-only `/30`; selected/preferred Domain Detail cards are `bg-pink-600/10` with border-only `/30`; selected Domains rows are `bg-pink-600/10`; Domains resize hover is neutral `hover:bg-gray-500/40`. Source scan found no pink background fills over `/15` outside allowed primary/checkbox uses. |
| AC3 | code-read | Not re-opened in round 5; the scoped diff adds no glass/decorative treatment. |
| AC4 | code-read | Not re-opened in round 5; the scoped diff changes color class strings only and does not change button structure. |
| AC5 | code-read | Not re-opened in round 5; no status-pill or backend status mapping code changed. |
| AC6 | code-read | `rg "purple-" frontend-react/src -g "*.tsx"` returns no rendered React source classes; CSS status token names remain only as theme variables, not React classes. |
| AC7 | code-read | Domains table selected row and resize-hover treatments are now neutral/≤10% tint by code-read; no table/filter behavior changed. |
| AC8 | code-read | Round-5 diff is class-only in existing JSX branches; no routes, API calls, handlers, or state transitions changed. |
| AC9 | NOT-VERIFIED | Reviewer did not run independent browser viewport checks at 390/768/1280/1440 in round 5. |
| AC10 | code-read | Scoped color edits do not remove focus-visible handling, labels, titles, or keyboard behavior. Rows-per-screen and glass-over-bright-content remain not independently runtime-verified by Reviewer. |
| AC11 | code-read | Round-5 diff adds no decorative hero/orb/blob/bokeh treatment and no redesign-announcement copy. |
| AC12 | test | Ran `flow gates --hermetic --record`; tests/typecheck/build/lint passed. Final recorded hermetic run is in the Baton gate slot above. |
