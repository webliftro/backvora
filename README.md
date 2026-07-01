# LinkBuilder

Link building outreach tool for SEO. Analyzes competitor backlinks, finds contacts, manages outreach campaigns.

## Features

- 🔍 **Competitor Analysis** - Fetch and analyze competitor backlink profiles via Ahrefs
- 📊 **Anchor Distribution** - Calculate anchor text distribution and link velocity
- 📧 **Contact Scraping** - Extract emails from contact/privacy/DMCA pages
- ✉️ **Outreach Management** - Email campaigns with templates and tracking
- 💰 **Deal Tracking** - Track negotiations, pricing, and link placements

## Quick Start

### 1. Setup

```bash
cd projects/linkbuilder

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your settings
nano .env
```

Required settings:
- `AHREFS_API_KEY` - Your Ahrefs MCP API key
- `SMTP_*` - Email settings for outreach

### 3. Run

```bash
# From project root
uvicorn backend.main:app --reload --port 8000

# Open http://localhost:8000
```

## Project Structure

```
linkbuilder/
├── backend/
│   ├── main.py          # FastAPI app
│   ├── config.py        # Settings
│   ├── database.py      # SQLAlchemy
│   ├── models.py        # ORM models
│   ├── routers/         # API endpoints
│   └── services/        # Business logic
├── frontend/
│   └── templates/       # Jinja2 HTML
├── data/                # SQLite DB
└── CLAUDE.md           # Coding guidelines
```

## API Endpoints

### Domains
- `GET /api/v1/domains` - List domains
- `POST /api/v1/domains` - Add domain
- `POST /api/v1/domains/bulk-import` - Import multiple domains
- `POST /api/v1/domains/{id}/analyze` - Fetch Ahrefs metrics

### Contacts
- `GET /api/v1/contacts` - List contacts
- `POST /api/v1/contacts/scrape/{domain_id}` - Scrape emails from domain

### Backlinks
- `POST /api/v1/backlinks/fetch/{domain}` - Fetch competitor backlinks
- `GET /api/v1/backlinks/analysis/{domain}` - Analyze backlink profile

### Outreach
- `GET /api/v1/outreach/campaigns` - List campaigns
- `POST /api/v1/outreach/messages/{id}/send` - Send email

## Development

```bash
# Linting
ruff check .

# Formatting
ruff format .

# Testing
pytest
```

## License

Private - All rights reserved
