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
