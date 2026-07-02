# CLAUDE.md - Link Builder Project Guidelines

## Project Overview
Link building outreach tool for adult niche SEO. Analyzes competitor backlinks, finds contacts, manages outreach campaigns.

## Tech Stack
- **Backend:** Python 3.11+, FastAPI
- **Database:** SQLite (SQLAlchemy ORM)
- **Frontend:** Jinja2 templates, Tailwind CSS, HTMX
- **External APIs:** Ahrefs MCP
- **Email:** SMTP (configurable)

---

## Coding Standards

### 1. Clean Code
- **Meaningful names:** Variables, functions, classes should clearly describe their purpose
- **Small functions:** Each function does ONE thing (< 20 lines ideal)
- **No magic numbers:** Use named constants
- **Comments:** Explain WHY, not WHAT (code should be self-documenting)

### 2. DRY (Don't Repeat Yourself)
- Extract repeated logic into utilities/helpers
- Use base classes for common patterns
- Shared validators, formatters in `utils/`
- If you copy-paste, you're doing it wrong

### 3. Modularity
- **Separation of concerns:** Routes → Services → Repositories → Database
- Each module should be independently testable
- Use dependency injection (FastAPI's `Depends()`)
- No circular imports

### 4. Configuration
- **ZERO hardcoding** - Everything configurable via:
  - Environment variables (`.env` file)
  - `config.py` with Pydantic Settings
- Sensitive data (API keys, SMTP creds) NEVER in code
- Use `config.VARIABLE` not raw strings

### 5. Error Handling
- Custom exception classes in `exceptions.py`
- Graceful degradation (don't crash on API failures)
- Meaningful error messages for debugging
- Log errors with context

### 6. Type Hints
- ALL functions must have type hints
- Use Pydantic models for request/response schemas
- Use `Optional[]` and `Union[]` properly

### 7. Async
- Use `async/await` for I/O operations
- Ahrefs calls, scraping, email - all async
- Don't block the event loop

---

## Project Structure
```
linkbuilder/
├── backend/
│   ├── main.py              # FastAPI app entry
│   ├── config.py            # Pydantic settings
│   ├── database.py          # SQLAlchemy setup
│   ├── models.py            # ORM models
│   ├── exceptions.py        # Custom exceptions
│   ├── routers/             # API route handlers
│   │   ├── domains.py
│   │   ├── contacts.py
│   │   └── outreach.py
│   ├── services/            # Business logic
│   │   ├── ahrefs.py        # Ahrefs MCP wrapper
│   │   ├── scraper.py       # Email scraper
│   │   └── email.py         # Email sender
│   ├── schemas/             # Pydantic schemas
│   │   ├── domain.py
│   │   └── contact.py
│   └── utils/               # Shared utilities
│       ├── validators.py
│       └── formatters.py
├── frontend/
│   └── templates/           # Jinja2 HTML
│       ├── base.html
│       ├── dashboard.html
│       └── components/
├── data/                    # SQLite DB lives here
├── scripts/                 # CLI utilities
├── tests/                   # pytest tests
├── .env.example             # Template for env vars
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Database Conventions
- Table names: plural, snake_case (`domains`, `contacts`)
- Primary keys: `id` (UUID string)
- Timestamps: `created_at`, `updated_at` on all tables
- Soft deletes: `deleted_at` (nullable)
- Foreign keys: `{table}_id` (e.g., `domain_id`)

---

## API Conventions
- RESTful routes: `/api/v1/{resource}`
- Use proper HTTP methods (GET, POST, PUT, DELETE)
- Consistent response format:
```json
{
  "success": true,
  "data": {...},
  "error": null
}
```
- Pagination: `?page=1&per_page=50`
- Filtering: `?status=pending&niche=adult`

---

## Git Workflow
- Meaningful commit messages
- Feature branches: `feature/backlink-analyzer`
- Keep commits atomic (one change per commit)

---

## Testing
- Write tests for services (business logic)
- Mock external APIs (Ahrefs, email)
- Test edge cases and error handling
- `pytest` with `pytest-asyncio`

---

## Before Committing
1. Run `ruff check .` (linting)
2. Run `ruff format .` (formatting)
3. Run `pytest` (tests pass)
4. Check for hardcoded values
5. Verify type hints present

---

## Key Principles
> "Code is read more often than written. Write for the reader."

> "Make it work, make it right, make it fast - in that order."

> "If it's not tested, it's broken."

---

## gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

### Available Skills
- `/plan-ceo-review` - CEO-level plan review
- `/plan-eng-review` - Engineering plan review
- `/review` - Code review
- `/ship` - Ship changes
- `/browse` - Web browsing
- `/qa` - QA testing
- `/setup-browser-cookies` - Set up browser cookies
- `/retro` - Retrospective

<!-- relayflow -->
## relayflow — task relay
This repo uses relayflow. When the user says a trigger phrase, run the matching role via the
`flow` CLI and follow its instructions exactly (don't ask for further instructions):
- **check the spec** → run `flow role spec-checker` (cross-model SPEC QA before the Builder; optional)
- **build the task** / **build next task** / **fix the task** → run `flow role builder`
- **review the task** → run `flow role reviewer` (you are the cross-model Reviewer; review only)
- **write the spec** / **spec the task** → run `flow role architect` (straight to the spec; skips the orchestrator's co-design gate)
- **verify the task** → run `flow role verifier` (the post-integration reality-check on the live deploy)
- **groom the relay** → run `flow role groomer` (distill the journal + batons into a ranked improvement digest; report-only)

**Default (no trigger phrase):** you are the **orchestrator** — the human's home session that drives a raw issue through recon → co-design → spec → dispatch → integrate. Run `flow role orchestrator` for your manual. Any worker trigger above wins, so a session given one is unaffected.

The role self-resolves the active task via `flow task <role>` — the one whose `docs/tasks/*/STATE.md`
baton has `Current owner = <role>`. The task's `SPEC.md` is the contract.
<!-- /relayflow -->
