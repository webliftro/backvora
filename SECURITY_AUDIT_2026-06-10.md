# BackVora Security Audit - 2026-06-10

Scope: BackVora/linkbuilder codebase at `/home/slither/clawd/projects/linkbuilder`.

This was a code and runtime review of auth, internal endpoints, secrets/config, frontend token handling, email rendering, uploads, scraping/SSRF surfaces, dependency audit, runtime exposure, and backup permissions. No fixes were applied during the audit pass except the earlier registration-disable change.

## Critical Findings

### 1. Unauthenticated Internal Endpoints Can Mutate State

Files:
- `backend/main.py:70-306`
- `frontend-react/src/api.ts:130-151`

The `/api/v1/internal/*` endpoints do not require authentication. They can generate/send articles, approve/reject orders, mark/confirm payments, run campaigns, reload scheduler jobs, and run link checks.

Live verification:
- `GET /api/v1/internal/scheduler/status` returns `200` anonymously.
- `GET /api/v1/domains` correctly returns `401` anonymously.

Impact: anyone who can reach `backvora.com` can potentially trigger costly AI work, send emails, alter order/payment lifecycle, or run automation if they know or guess IDs.

Recommended fix:
- Require normal user auth for UI-used internal routes.
- Add separate signed action tokens for Slack approval/rejection links.
- Add an `INTERNAL_API_TOKEN` dependency for cron-only automation.

### 2. Live Secrets Are Hardcoded in Tracked Config

File:
- `backend/config.py:24-70`

Secrets and sensitive defaults are hardcoded in tracked source, including fallback JWT secret, email password, Anthropic key, Slack webhook, and payment/email addresses.

`.gitignore` ignores `backend/config.py`, but `git ls-files` shows it is already tracked.

Impact: repo access equals credential compromise.

Recommended fix:
- Rotate exposed Anthropic, Slack, email/app password, JWT secret, and any keys present in tracked history.
- Move all secrets to `.env` or real environment variables only.
- Remove real secret defaults from `backend/config.py`.

### 3. Default JWT Fallback Is Unsafe

Files:
- `backend/config.py:27`
- `backend/auth.py:30-42`

The app has a static fallback JWT secret. If `.env` is missing or misloaded, tokens become forgeable.

Impact: full auth bypass under misconfiguration.

Recommended fix:
- Make `JWT_SECRET_KEY` required.
- Fail startup if it is missing or still set to a placeholder.

## High Findings

### 4. Slack Approval Links Are Public Mutating URLs

Files:
- `backend/services/slack_notifier.py:72-83`
- `backend/main.py:182-193`

Slack review messages link directly to unauthenticated `/api/v1/internal/orders/{id}/approve` and `/reject` endpoints.

Impact: leaked Slack message/history or guessed order IDs can approve/reject orders.

Recommended fix:
- Use signed, short-lived one-time action tokens.
- Require auth or internal-token validation before mutating order state.

### 5. Tokens Are Stored in `localStorage` and Email HTML Is Rendered

Files:
- `frontend-react/src/contexts/AuthContext.tsx:20-56`
- `frontend-react/src/api.ts:5-16`
- `frontend-react/src/pages/InboxPage.tsx:188-197`

Access and refresh tokens are stored in `localStorage`. The inbox renders sanitized email HTML using `dangerouslySetInnerHTML` after DOMPurify.

`npm audit --omit=dev` flags XSS advisories for the current DOMPurify version.

Impact: any XSS or sanitizer bypass can steal access and refresh tokens.

Recommended fix:
- Move tokens to secure HttpOnly cookies.
- Upgrade DOMPurify.
- Remove `style` and `class` from allowed email HTML attributes unless required.
- Add a strict CSP.

### 6. Production Dependency Vulnerabilities

Command run:

```bash
npm audit --omit=dev
```

Result:
- 7 total advisories
- 5 high
- 2 moderate

Relevant packages:
- `dompurify`
- `react-router-dom`
- `react-router`
- `vite`
- `rollup`
- `picomatch`
- `postcss`

Recommended fix:
- Run dependency upgrades and rebuild the frontend.
- Prioritize DOMPurify and React Router.

## Medium Findings

### 7. Missing Browser Security Headers

Live `/login` response lacks:
- `Content-Security-Policy`
- `Strict-Transport-Security`
- `X-Frame-Options` or CSP `frame-ancestors`
- `X-Content-Type-Options`
- `Referrer-Policy`

This matters more because tokens are currently in `localStorage` and the app renders email HTML.

Recommended fix:
- Add security header middleware in FastAPI or configure them at Cloudflare.

### 8. SSRF and Egress Abuse Risk in Scraping/Form Submission

Files:
- `backend/services/scraper.py:56-87`
- `backend/services/scraper.py:477-484`
- `backend/routers/contacts.py:240-337`
- `backend/routers/domains.py:1369-1380`

Authenticated users can trigger outbound HTTP requests to stored domains/forms. There is no private-IP/localhost block, no egress allowlist, and no response size cap.

Impact: SSRF/resource abuse if an account is compromised or malicious.

Recommended fix:
- Validate hostnames and resolved IPs before outbound requests.
- Block private, loopback, link-local, multicast, and metadata IP ranges.
- Add response size limits and tighter timeout/retry controls.

### 9. Unbounded Bulk Operations and Uploads

Files:
- `backend/routers/import_export.py:36`
- `backend/routers/import_export.py:222`
- `backend/routers/domains.py:820-855`
- `backend/routers/campaigns.py:1387-1408`

CSV uploads are read fully into memory. Bulk domain and bulk order inputs have no list-size limits.

Impact: memory/CPU/database exhaustion from oversized authenticated requests.

Recommended fix:
- Add max upload size.
- Stream or cap CSV parsing.
- Add maximum item counts for bulk operations.

### 10. Runtime Exposure and File Permissions

Runtime:
- BackVora uvicorn runs on `0.0.0.0:8001`.
- Cloudflare Tunnel is also running.

Local files:
- `.env` has mode `664`.
- code backup tarballs have mode `664`.
- DB backups have mode `644`.

Impact: not directly web-served by the app, but too permissive for a secrets/data directory on a shared host.

Recommended fix:
- Bind uvicorn to `127.0.0.1` if Cloudflare Tunnel is the only intended public path.
- Restrict `.env`, DB, and backup permissions to owner-only where practical.

## Recommended Patch Order

1. Protect `/api/v1/internal/*` immediately:
   - normal auth for UI-used routes
   - signed one-time tokens for Slack actions
   - internal API token for cron callbacks

2. Rotate and remove exposed secrets:
   - Anthropic key
   - Slack webhook
   - email/app password
   - JWT secret
   - any keys present in tracked history

3. Update frontend dependencies:
   - DOMPurify
   - React Router
   - Vite/Rollup/PostCSS transitive chain

4. Move auth tokens to secure HttpOnly cookies, or at minimum shorten access token lifetime and remove refresh token from `localStorage`.

5. Add browser security headers:
   - CSP
   - HSTS
   - frame blocking
   - content-type sniffing protection
   - referrer policy

6. Add SSRF guards, upload limits, bulk list limits, and egress size/time caps.

## Notes

The earlier public registration change is already live:
- `/api/v1/auth/register` returns `403`.
- Login remains available to existing active users.
