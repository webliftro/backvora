# SPEC — BackVora Operational AI Agent

**Status:** Ready-for-Builder
**Architect:** Codex
**Date:** 2026-07-08
**Task slug:** backvora-operational-ai-agent
**Issue:** `webliftro/backvora#4`

## Intent & Surface
- **What R wants:** add an AI agent inside BackVora with full operational access to existing BackVora features, so R can tell it what to do in natural language.
- **Hard boundary:** operational only. The agent may read and mutate BackVora data through explicit application actions, but it must not be able to change code, deploy, run migrations, execute shell commands, edit files, access env/secrets, or alter infrastructure.
- **Primary backend surface:** new authenticated `/api/v1/agent/*` router plus a service layer that maps approved natural-language intents to whitelisted typed actions.
- **Primary frontend surface:** a compact authenticated Agent page reachable from the app sidebar, with chat-style command entry, action results, confirmation prompts, and audit/history visibility.
- **Persistence surface:** new DB tables/columns as needed for agent sessions/messages/action audit records. Existing project style uses SQLAlchemy `create_all` plus explicit idempotent migration scripts, not Alembic.

## Architecture Direction
- Do not give an LLM arbitrary router, Python, SQL, shell, browser, or file-system access.
- Implement a tool/action registry in application code. Every executable operation must be a named typed action with:
  - input schema/validation,
  - permission level,
  - read-only vs mutating classification,
  - confirmation requirement for risky mutations,
  - structured result,
  - audit record before/after execution.
- Start with a useful MVP action set covering high-value BackVora operations. Keep it extensible, but avoid overbuilding a generic agent framework.
- The LLM should only choose among registered actions and produce arguments. The server validates everything before execution.
- If no LLM key/config is available, the feature should fail gracefully with a clear error, while still preserving the API/UI shape and tests around action execution.

## Initial Action Set
- **Read/search actions**
  - Search/list domains by text, status, adult verdict, DR/traffic filters, category/tag, and target backlinks.
  - Get domain details including contacts, prices, notes, adult classification metadata, and backlink targets.
  - Search/list campaigns, orders, inbox items, and target sites using existing models/routers as references.
  - Summarize a domain/campaign/order from stored BackVora data.
- **Safe mutating actions**
  - Update domain fields already editable in the app: status, category, tags, notes, contact fields, adult override/classification where supported.
  - Add domains using the existing domain import/create semantics.
  - Trigger existing domain metrics/classification checks.
  - Create/update contacts and link prices.
- **High-risk mutating actions requiring explicit confirmation**
  - Send outreach/order emails.
  - Generate or regenerate articles.
  - Mark payments sent/confirmed.
  - Verify or mark live URLs.
  - Bulk updates/deletes/imports.
- **Forbidden actions**
  - Shell/code/file execution.
  - Git, deploy, systemd, migration, backup, or environment access.
  - Direct arbitrary SQL.
  - Unauthenticated internal automation endpoints.
  - Exfiltrating secrets, tokens, passwords, env vars, or raw config.

## Acceptance Criteria
- [ ] **AC1 — Authenticated Agent API.** Add authenticated `/api/v1/agent` endpoints for sending a command, listing sessions/messages/audit, and confirming or cancelling pending actions. Endpoints use the existing JWT auth dependency.
- [ ] **AC2 — Agent page.** Add an authenticated frontend page (for example `/agent`) linked from the sidebar. It supports entering commands, seeing assistant responses, viewing proposed actions, and confirming/cancelling actions that require confirmation.
- [ ] **AC3 — Whitelisted action registry.** All operations are executed through a server-side registry of named actions. The registry contains action metadata, validates input, and rejects unknown actions.
- [ ] **AC4 — No arbitrary execution.** The implementation contains no path that lets model output execute shell commands, Python code, JavaScript code, arbitrary SQL, file writes, deploy commands, migrations, or internal unauthenticated endpoints.
- [ ] **AC5 — Permission and confirmation model.** Read actions can execute immediately. Mutating actions are audited. High-risk mutations require an explicit second-step confirmation tied to the pending action id/session/user.
- [ ] **AC6 — Audit trail.** Every command and every action attempt is persisted with user id, session id, action name, sanitized input, status, result/error summary, timestamps, and whether confirmation was required/granted.
- [ ] **AC7 — Operational MVP coverage.** The shipped registry includes at least domain search/detail/update, contact create/update, link price create/update, metrics/classification trigger, and order/campaign summary actions. Risky order/email/payment actions may be present as confirmation-required actions or explicitly unavailable with a clear response if implementation risk is too high for the first pass.
- [ ] **AC8 — LLM integration is configurable and safe.** Provider/model/API key come from env/config. Missing config returns a clear UI/API error. Prompts/tool schemas instruct the model to use only registered actions and to refuse forbidden operations, but server-side validation remains the real boundary.
- [ ] **AC9 — Tests.** Add focused backend tests for action registry validation, forbidden action rejection, confirmation gating, audit persistence, and at least two real action handlers. Add frontend type/build coverage through existing gates.
- [ ] **AC10 — Migration script.** If new tables/columns are added, include an idempotent migration script consistent with the existing `scripts/migrate_*.py` pattern.
- [ ] **AC11 — Gates.** `flow gates --record backvora-operational-ai-agent` is green before handoff. Reviewer re-runs at least hermetic gates.

## Out Of Scope
- Giving the agent autonomous background scheduling.
- Telegram/Slack/voice access to the BackVora agent.
- Browser automation for external publisher sites.
- Production deployment, running production migrations, or touching system services.
- A separate role/permission administration UI unless it is required to keep the first version safe.
- Rewriting existing BackVora routers around a new command bus.

## Constraints
- Reuse existing service/router patterns where possible. Do not duplicate business logic if a router/service already has a clean callable boundary.
- Keep UI dense and operational. This is an app tool, not a landing page.
- Do not hardcode model names or API keys. Add config/env entries with safe defaults.
- Sanitize audit payloads: never persist auth tokens, passwords, API keys, full env/config, or raw LLM secrets.
- Keep the first action set narrow enough to review. A small safe registry is better than a broad ambiguous one.
- Respect existing dirty worktree state: do not touch unrelated `data/imports/` or `scripts/bulk_classify_adult.py`.

## Test Plan
- Unit-test action registry:
  - unknown action rejected,
  - forbidden action names cannot be registered/executed,
  - schema validation rejects bad arguments,
  - high-risk action returns pending confirmation,
  - confirmation executes only for the same user/session and only once.
- Unit/integration-test audit records for success, failure, rejected action, and pending confirmation.
- Test representative handlers against a temporary DB:
  - search/list domains,
  - update domain notes/status/category/tags,
  - create/update contact or link price.
- Frontend: run TypeScript and build gates; ensure page compiles and API types match backend responses.
- Security/code-read: verify there is no `subprocess`, shell execution, `eval`, arbitrary SQL, file write, or internal endpoint proxy in the agent path.

## Notes For Builder
- `backend/main.py` includes routers with `Depends(get_current_user)`. The agent router should follow the same authenticated-router pattern.
- Existing internal endpoints in `backend/main.py` are unauthenticated automation endpoints. Do not call them from the agent as a shortcut; use service functions or authenticated-safe wrappers with audit/confirmation.
- Current auth has active users but no roles. If a role model is necessary, keep it minimal and backward-compatible.
- Frontend navigation lives in `frontend-react/src/components/Layout.tsx`; routes live in `frontend-react/src/App.tsx`; API wrapper lives in `frontend-react/src/api.ts`.
- Existing tests use pytest; frontend gates use Vite/TypeScript.
