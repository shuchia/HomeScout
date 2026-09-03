# CLAUDE.md

**Snugd** ([snugd.ai](https://snugd.ai)) — AI-powered rental apartment hunting platform for students and young professionals.

> The codebase still uses "HomeScout" internally for module/path names. Product name is **Snugd**.

This file is a router. Read it first, then load only the subsystem doc(s) relevant to your task.

## Quick Start

```bash
# Frontend
cd frontend && npm install && npm run dev          # → :3000

# Backend (NEVER use --reload)
cd backend && source .venv/bin/activate
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000   # → :8000

# Celery worker + beat (scraping, tours, alerts)
celery -A app.celery_app worker --loglevel=info -Q celery,scraping,maintenance
celery -A app.celery_app beat --loglevel=info

# Prerequisites
brew services start postgresql@16   # DB mode
brew services start redis           # Celery + rate limiting

# Verify
curl http://localhost:8000/health
curl http://localhost:8000/api/apartments/stats
```

Architecture: Next.js (frontend) + FastAPI (backend) + PostgreSQL + Redis + Supabase (auth) + Stripe (billing) + Anthropic Claude (AI) + OpenAI Whisper (transcription). Backend on AWS ECS Fargate; frontend on Vercel.

## Per-Directory Guides

| Directory | Guide | Covers |
|-----------|-------|--------|
| `backend/` | [backend/CLAUDE.md](backend/CLAUDE.md) | Routers, services, models, Celery, tests, env vars |
| `frontend/` | [frontend/CLAUDE.md](frontend/CLAUDE.md) | Routes, components, state, PWA, Playwright E2E |
| `infra/` | [infra/CLAUDE.md](infra/CLAUDE.md) | Terraform modules, environments, deploy/promote flow |
| `supabase/` | [supabase/CLAUDE.md](supabase/CLAUDE.md) | Migrations, tables, RLS policies |

## Documentation Index

| Working on... | Read |
|---------------|------|
| Frontend UI, components, pages, routes | [docs/frontend.md](docs/frontend.md) |
| Backend API, routers, services, DB | [docs/backend.md](docs/backend.md) |
| AI features (scoring, comparison, emails, briefs, Whisper) | [docs/ai-features.md](docs/ai-features.md) |
| Scraping, normalization, true-cost calculation | [docs/data-pipeline.md](docs/data-pipeline.md) |
| Auth, tiers, Stripe, invite codes, rate limiting | [docs/auth-and-billing.md](docs/auth-and-billing.md) |
| Infrastructure, Terraform, deploys, CI/CD | [docs/deployment.md](docs/deployment.md) |
| Touring pipeline (core feature) | [docs/touring-pipeline.md](docs/touring-pipeline.md) |
| Floorplan-aware search (architecture) | [docs/floorplan-search-architecture.md](docs/floorplan-search-architecture.md) |
| Floorplan-aware search (original design) | [docs/floorplan-search-design.md](docs/floorplan-search-design.md) |
| What's next / planned features | [docs/roadmap.md](docs/roadmap.md) |
| Auth flow deeper diagrams | [docs/auth-flow.md](docs/auth-flow.md) |
| Live scraping config (cities + frequencies) | [docs/scraping-frequency.md](docs/scraping-frequency.md) |
| Beta launch open items | [docs/launch-readiness.md](docs/launch-readiness.md) |
| Old plans / superseded docs | [docs/archive/](docs/archive/) |

## Environments

| Env | Frontend | API | State |
|-----|----------|-----|-------|
| local | `:3000` | `:8000` | — |
| dev | snugd-dev (Vercel) | `api-dev.snugd.ai` | Not provisioned |
| qa | `qa.snugd.ai` | `api-qa.snugd.ai` | **Live — the only deployed env** |
| prod | `snugd.ai` | `api.snugd.ai` | **Not deployed yet** |

`infra/environments/prod.tfvars` exists but has never been applied: there is no `snugd/prod/secrets` in Secrets Manager, no prod ECS cluster, and `api.snugd.ai` has no DNS record. Anything that needs prod data (e.g. `scripts/beta-report.sh prod`) will fail until prod is stood up.

## Critical Conventions

- **Never use `--reload`** with uvicorn — it watches `.venv/` and breaks.
- **Type sync required**: `frontend/types/apartment.ts` and `frontend/types/tour.ts` must match `backend/app/schemas.py`.
- **Budget filtering is strict** — no flexibility (`apartment_service.py`).
- **Bedrooms = exact match**, **bathrooms = at-least**.
- **Dual data mode**: `USE_DATABASE` env var. Every apartment endpoint checks `is_database_enabled()` and routes to JSON or Postgres accordingly.
- **Claude models**: `claude-haiku-4-5-20251001` for search/emails/notes/day-plan; `claude-sonnet-4-5-20250929` for comparison and decision brief.
- **Claude calls**: 15 s timeout (search), 45 s (compare); heuristic fallback on any exception; max 5 concurrent via `asyncio.Semaphore(5)`; system-prompt caching enabled.
- **Rate limiting** (`middleware/rate_limit.py`): authed 120/min, anonymous 30/min, expensive paths (`/api/search`, `/api/apartments/compare`) 20/min. Fail-open on Redis errors.
- **Tests**: `TESTING=1` disables rate limiting; E2E mocks auth via `localStorage.__test_auth_user` (only when `NODE_ENV !== 'production'`).
- **Auth**: 5-second timeout in `AuthContext` to avoid infinite loading; fail-open for Redis/Supabase outages.
- **Analytics**: fire-and-forget — never blocks or raises.
- **True cost**: precomputed at ingestion in DB mode; `_add_cost_breakdown()` fills gaps in JSON mode.
- **Admin endpoints**: `/api/admin/data-collection/*`, `/api/admin/invite-codes`, `/api/admin/beta-report`, and `/api/admin/waitlist` require `X-Admin-Key`. Value is per-env in AWS Secrets Manager (`snugd/{env}/secrets:ADMIN_API_KEY`). Calling without it returns 422 (missing header) or 401 (wrong key).
- **Freshness filter**: `/api/apartments/list` and `/api/search` only return rows with `freshness_confidence >= 40` (apartments.py:147). `decay_and_verify` reduces scores hourly, so listings drop out unless a market is re-scraped. Stats endpoint counts all `is_active=1` rows so the two diverge.
- **Floorplan search is flag-gated**: `USE_FLOORPLAN_SEARCH` (backend) + `NEXT_PUBLIC_FLOORPLAN_SEARCH` (frontend). **On in QA**, off by default locally. Both must be set — the frontend flag is baked at build time, so changing it needs a rebuild, not just a redeploy.

## Feature Flags

| Flag | Where | Default | QA |
|------|-------|---------|-----|
| `USE_DATABASE` | backend | `false` | `true` |
| `USE_FLOORPLAN_SEARCH` | backend | `false` | `true` |
| `NEXT_PUBLIC_FLOORPLAN_SEARCH` | frontend (build-time) | unset | `true` |

## Tier System (Quick Reference)

| Feature | Free | Pro ($12/mo) |
|---------|------|--------------|
| Search | 20/day, heuristic only | Unlimited + Claude AI |
| Compare | Basic table | Claude head-to-head analysis |
| Favorites | 5 max | Unlimited |
| Tours | Full pipeline (manual) | Full pipeline + AI emails, day plan, decision brief, note enhancement |
| Saved searches | No | Unlimited + daily email alerts |
| Cost breakdown | Headline only | Full with sources |

Anonymous users get filtered search results with no AI and no daily metering. Free users get 20 searches/day (`FREE_DAILY_SEARCH_LIMIT` in `tier_service.py`).

## Live Markets

8 cities in the search dropdown (`frontend/components/SearchForm.tsx`): Boston MA, Bryn Mawr PA, Cambridge MA, New York NY, Philadelphia PA, Pittsburgh PA, San Francisco CA, State College PA. The scraper runs against a larger set of market configs — see [docs/scraping-frequency.md](docs/scraping-frequency.md).

## Beta Operations

```bash
# Weekly usage report (invite codes, cohort, tours, funnel, feedback)
./scripts/beta-report.sh qa 30 20 > reports/beta-$(date +%Y%m%d).md
```

A launchd agent (`~/Library/LaunchAgents/com.snugd.weekly-beta-report.plist`) runs this every Monday 9:00 AM local and writes into `reports/` (untracked). Backed by `GET /api/admin/beta-report` in `backend/app/routers/beta_admin.py`.

## Common Issues

| Issue | Fix |
|-------|-----|
| `Event loop is closed` | Restart Celery worker |
| Server hangs at startup | Check Postgres: `lsof -i :5432` |
| Celery tasks not running | Check Redis: `redis-cli ping` |
| `--reload` causes issues | Don't use it |
| Port 8000 in use | `pkill -f "uvicorn app.main"` |
| Floorplan results look wrong locally | `USE_FLOORPLAN_SEARCH` is off by default — QA has it on |
| `beta-report.sh prod` fails | Prod isn't deployed; use `qa` |
