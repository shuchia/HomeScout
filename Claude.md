# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Build & Development Commands

### Frontend (Next.js)
```bash
cd frontend
npm install              # Install dependencies
npm run dev              # Start dev server (port 3000)
npm run build            # Production build
npm run lint             # Run ESLint
```

### Backend (FastAPI)
```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# API docs: http://localhost:8000/docs
```

### Celery Worker (for scraping/async tasks)
```bash
cd backend && source .venv/bin/activate
celery -A app.celery_app worker --loglevel=info -Q celery,scraping,maintenance
celery -A app.celery_app beat --loglevel=info  # optional: scheduled tasks
```

### Prerequisites
```bash
brew services start postgresql@16   # Required for DB mode
brew services start redis           # Required for Celery + rate limiting
```

### Testing
```bash
# Backend (259 tests)
cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v

# Frontend E2E
cd frontend && npx playwright test
```

### Quick Verification
```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/apartments/stats
curl "http://localhost:8000/api/apartments/list?limit=5"
```

## Architecture Overview

Full-stack apartment finder: **Next.js** (frontend) + **FastAPI** (backend) + **PostgreSQL** + **Redis** + **Supabase** (auth) + **Stripe** (billing) + **Claude AI** (scoring/analysis).

Key flows: Search → Claude AI scoring (Pro) or heuristic scoring (free) → Results. Compare → Claude analysis (Pro). Tours → lifecycle with notes/photos/voice/AI features. Upgrade → Stripe Checkout → webhook → tier update.

**Dual Data Mode** (`USE_DATABASE` env var): JSON mode (default, static file) or Database mode (PostgreSQL with scraped data).

## Critical Conventions

- **Never use `--reload`** with uvicorn (causes venv file watching issues)
- **Type sync required**: Frontend `types/apartment.ts` and `types/tour.ts` must match backend `schemas.py`
- **Budget filtering is strict** — no flexibility in `apartment_service.py`
- **Bedrooms = exact match**, bathrooms = "at least"
- **All apartment endpoints** support both DB and JSON modes via `is_database_enabled()`
- **Claude models**: Haiku for search scoring/emails/notes, Sonnet for comparison/decision briefs
- **Claude calls**: 15s timeout, heuristic fallback, max 5 concurrent via semaphore, prompt caching enabled
- **Rate limiting**: Redis sliding window (auth=120/min, anon=30/min, expensive=20/min), fail-open
- **Tests**: `TESTING=1` env var disables rate limiting; E2E mocks auth via `localStorage.__test_auth_user`
- **Auth**: 5-second timeout to prevent infinite loading; fail-open for Redis/Supabase
- **Analytics**: fire-and-forget, never blocks or raises
- **True cost**: precomputed at ingestion; `_add_cost_breakdown()` fills gaps for JSON mode

## Tier System (Quick Reference)

| Feature | Free | Pro ($12/mo) |
|---------|------|-------------|
| Search | 3/day, heuristic only | Unlimited + Claude AI |
| Compare | Basic table | Claude analysis |
| Favorites | 5 max | Unlimited |
| Tours AI | No | Yes (emails, planner, briefs) |
| Cost breakdown | Headline only | Full with sources |

## Common Issues

| Issue | Solution |
|-------|----------|
| `Event loop is closed` | Restart Celery worker |
| Server hangs at startup | Check PostgreSQL: `lsof -i :5432` |
| Celery tasks not running | Check Redis: `redis-cli ping` |
| `--reload` causes issues | Don't use `--reload` flag |
| Port 8000 in use | `pkill -f "uvicorn app.main"` |
