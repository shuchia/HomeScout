# Backend

> Last verified: 2026-05-04 | Source of truth: this doc + the code it references

FastAPI service for Snugd. Async SQLAlchemy + Postgres, Redis-backed rate limiting and Celery, Anthropic + OpenAI for AI, Supabase for auth, Stripe for billing.

## Quick Commands

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt

# Start API (NEVER use --reload — see Common Issues)
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# Docs: http://localhost:8000/docs

# Celery worker (scraping + maintenance + tours)
celery -A app.celery_app worker --loglevel=info -Q celery,scraping,maintenance

# Celery beat (scheduled tasks)
celery -A app.celery_app beat --loglevel=info

# Tests (env vars required for module import)
TESTING=1 ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret \
  python -m pytest tests/ -v
```

Prerequisites: `brew services start postgresql@16` (DB mode) and `brew services start redis` (Celery + rate limiting).

## Architecture

```
backend/app/
├── main.py              # FastAPI app, lifespan, /api/search + /api/search/score-batch
├── celery_app.py        # Celery config, beat schedule, queue routing
├── auth.py              # Supabase JWT verification (HS256, audience=authenticated)
├── database.py          # Async SQLAlchemy engine, is_database_enabled()
├── schemas.py           # Pydantic request/response models
├── routers/             # 9 routers — see endpoint table below
├── services/            # apartment_service, claude_service, tier_service, scrapers/, normalization/, deduplication/, transcription/, storage/, monitoring/
├── models/              # SQLAlchemy ORM models
├── tasks/               # Celery tasks (scrape, maintenance, tours, transcription)
├── middleware/          # rate_limit.py
└── data/                # apartments.json (JSON mode), cost_estimates.json
```

Two data modes (`USE_DATABASE` env var):
- **JSON mode** (default): reads `app/data/apartments.json` (60 mock apartments).
- **Database mode**: queries Postgres populated by the scraping pipeline.

Every apartment endpoint calls `is_database_enabled()` and dispatches to the right backend.

## API Endpoints

### Top-level (declared in `main.py`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | none | Root health |
| GET | `/health` | none | Health check |
| GET | `/api/apartments/count` | none | Total tracked apartments |
| GET | `/api/apartments/stats` | none | Listing statistics |
| POST | `/api/search` | optional | Pro: paginated heuristic results (AI backfill via score-batch); free: 3/day; anon: filtered |
| POST | `/api/search/score-batch` | required (Pro) | AI score up to 10 IDs per call, Redis-cached 1h |
| GET | `/metrics` | none | Prometheus metrics |
| POST | `/api/test` | none | Echo (dev only) |

### Apartments router (`routers/apartments.py`)

Registered LAST so `/{apartment_id}` does not capture `/count` or `/stats`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/apartments/list` | none | Paginated list with filters |
| GET | `/api/apartments/{id}` | none | Single apartment detail |
| POST | `/api/apartments/batch` | none | Hydrate multiple by IDs |
| POST | `/api/apartments/compare` | optional | Pro: Claude head-to-head; free/anon: basic table |

### Billing router (`routers/billing.py`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/billing/checkout` | required | Stripe Checkout Session for Pro |
| POST | `/api/billing/portal` | required | Stripe Customer Portal |
| POST | `/api/webhooks/stripe` | Stripe sig | Webhook handler |

Webhook events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`.

### Saved searches router (`routers/saved_searches.py`)

| Method | Path | Auth | Tier | Description |
|--------|------|------|------|-------------|
| GET | `/api/saved-searches` | required | any authed | List user's saved searches |
| POST | `/api/saved-searches` | required | Pro only | Create |
| DELETE | `/api/saved-searches/{id}` | required | any authed | Delete |

### Tours router (`routers/tours.py`)

Full CRUD plus AI endpoints (inquiry email, day plan, decision brief, note enhance), voice-note upload, photo upload, tags. See `docs/touring-pipeline.md` for the full inventory.

### Data collection router (`routers/data_collection.py`)

Prefix `/api/admin/data-collection`. Admin endpoints: `/jobs` (POST/GET), `/jobs/{id}` (GET), `/sources` (GET/PUT), `/metrics`, `/health`, `/markets` (GET/POST), `/markets/{id}` (PUT), `/markets/{id}/scrape` (POST), `/backfill-fees` (POST), `/listings` (DELETE). See `docs/data-pipeline.md`.

### Other routers

| Router | Endpoint(s) | Auth |
|--------|-------------|------|
| `feedback.py` | POST `/api/feedback` | optional |
| `invite.py` | POST `/api/invite/redeem`, GET `/api/invite/status`, POST `/api/admin/invite-codes` | last requires `X-Admin-Key` |
| `waitlist.py` | POST `/api/waitlist`, GET `/api/admin/waitlist` | admin on second |
| `webhooks.py` | POST `/webhooks/supabase/check-matches` | HMAC `x-webhook-secret` |

## Service Layer

| Service | Purpose |
|---------|---------|
| `apartment_service.py` | Pagination, filtering (strict budget, exact beds, "at-least" baths), Redis-backed search caching, batch fetch by IDs |
| `claude_service.py` | All Anthropic calls (scoring, comparison, emails, day plan, decision brief, note enhancement) — see `docs/ai-features.md` |
| `tier_service.py` | Supabase tier lookup, Redis daily search counter, tier updates from Stripe webhook |
| `analytics_service.py` | Fire-and-forget event logging to `analytics_events` (never blocks/raises) |
| `scoring_service.py` | Heuristic match scoring (free/anonymous tier, AI fallback) |
| `cost_estimator.py` + `pricing_model_detector.py` | True-cost calculation and per-bed pricing detection |
| `distance.py` | Geographic proximity scoring (`add_distances`) |
| `scrapers/` | `apify_service`, `scrapingbee_service`, `base_scraper` — see data-pipeline doc |
| `normalization/` | Field validation, address standardization, quality score 0–100 |
| `deduplication/` | SHA256 content hash + fuzzy address match |
| `transcription/` | OpenAI Whisper for voice notes |
| `storage/` | S3 image caching + voice-note storage |
| `monitoring/metrics.py` | Prometheus metrics for `/metrics` endpoint |

## Database Models

| Model | Table | Purpose |
|-------|-------|---------|
| `ApartmentModel` | `apartments` | Listings with source tracking, cached images, content hash, quality score |
| `ScrapeJobModel` | `scrape_jobs` | Scrape job status + metrics |
| `DataSourceModel` | `data_sources` | Source config (rate limits, schedule) |
| `MarketConfigModel` | `market_configs` | City + tier + frequency + circuit breaker |

`ApartmentModel` indexes: `city`, `rent`, `bedrooms`, `bathrooms`, `property_type`, `source`, `content_hash`, `is_active`, plus composite `(city, rent, bedrooms)` for search.

Tour-related tables live in Supabase (Postgres) — see `docs/touring-pipeline.md`.

## Middleware Stack

Added in `main.py` in this order; Starlette runs them **in reverse**, so the request hits CORS first, then RateLimit, then GZip:

1. `GZipMiddleware` (responses ≥ 1KB) — added first.
2. `RateLimitMiddleware` — added second.
3. `CORSMiddleware` — added last (allows `FRONTEND_URL` plus `localhost:3000` in deployed envs).

## Rate Limiting

`middleware/rate_limit.py` — Redis sliding-window counters. **Verified current values:**

| Identity | Limit | Notes |
|----------|-------|-------|
| Authenticated (token-hash key) | **120 req/min** (`GLOBAL_LIMIT`) | |
| Anonymous (IP key) | **30 req/min** (`ANON_LIMIT`) | |
| Expensive paths (`/api/search`, `/api/apartments/compare`) | **20 req/min** (`EXPENSIVE_LIMIT`) | Applies regardless of auth |

Returns 429 `{"detail": "Rate limit exceeded. Please slow down."}`. **Fail-open** on Redis errors. Skipped when `TESTING=1`. (Older numbers in `backend/CLAUDE.md` — 60/10/10 — are stale; the root `CLAUDE.md` matches reality.)

## Dual Data Mode

`is_database_enabled()` returns true when `USE_DATABASE=true` and `DATABASE_URL` is set. Apartment endpoints check it and route accordingly. JSON mode does not have precomputed cost breakdowns — `_add_cost_breakdown()` (in `routers/apartments.py`) fills the gap on read.

## Environment Variables

**Required**

| Var | Purpose |
|-----|---------|
| `ANTHROPIC_API_KEY` | Claude calls |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` | Auth + tier table |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID` | Billing |
| `USE_DATABASE`, `DATABASE_URL` | DB mode |
| `REDIS_URL` | Celery broker + rate limiting + search metering |

**Data collection**

| Var | Purpose |
|-----|---------|
| `APIFY_API_TOKEN` | Apify actors |
| `SCRAPINGBEE_API_KEY` | ScrapingBee (Craigslist) |
| `OPENAI_API_KEY` | Whisper transcription |

**Optional**

| Var | Purpose |
|-----|---------|
| `RESEND_API_KEY`, `ALERT_FROM_EMAIL` | Daily Pro email alerts |
| `S3_BUCKET_NAME`, `AWS_REGION`, `CLOUDFRONT_DOMAIN` | Image cache + voice notes |
| `FRONTEND_URL` | CORS origin |
| `SQL_ECHO` | SQLAlchemy query logging |
| `TESTING` | Disables rate limiting (set in `conftest.py`) |

## Celery Beat Schedule

| Task | Schedule | Purpose |
|------|----------|---------|
| `dispatch_scrapes` | Every hour at :00 | Read `market_configs`, spawn scrape tasks for due markets |
| `decay_and_verify` | Every hour at :30 | Recalculate freshness confidence, trigger HTTP verification |
| `cleanup_maintenance` | Daily at 3 AM | Deactivate dead listings, reset circuit breakers, fail stale jobs |
| `send_daily_alerts` | Daily at 13:00 UTC (8 AM ET) | Email Pro users with new matching listings |
| `check_tour_reminders` | Every 10 min | Fire 30-min post-tour reminder notifications |

## Testing

Run from `backend/`:

```bash
TESTING=1 ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret \
  python -m pytest tests/ -v
```

`TESTING=1` disables rate limiting (`conftest.py` honors it). The test suite has **~342 tests across 26 files** (counted via `grep -cE "^\s*(async )?def test_|^class Test" tests/*.py`). Highlights:

| File | Coverage |
|------|----------|
| `test_auth.py` | JWT verification, get_current_user, get_optional_user |
| `test_tier_service.py` | Tier lookup, Redis metering, fail-open |
| `test_billing.py` | Stripe checkout, portal, webhooks |
| `test_search_gating.py`, `test_compare_gating.py` | Tier-based behavior |
| `test_saved_searches.py` | Pro-only creation |
| `test_rate_limit.py` | All three limits, expensive paths, fail-open |
| `test_alert_tasks.py` | Daily email alerts |
| `test_apartments_router.py` | Apartment endpoints (DB + JSON modes) |
| `test_tours_*` | Tour CRUD, AI endpoints, voice notes |
| `test_webhooks.py` | Supabase HMAC auth |

## Common Issues

| Issue | Fix |
|-------|-----|
| `Event loop is closed` in Celery | Restart the worker — async clients get bound to a closed loop on task fork |
| Server hangs at startup | PostgreSQL down: `lsof -i :5432`; or `DATABASE_URL` typo |
| Celery tasks not running | Redis down: `redis-cli ping` should return PONG |
| `--reload` issues | Don't use `--reload` — uvicorn watches `.venv/` and explodes |
| Port 8000 in use | `pkill -f "uvicorn app.main"` |
| Tests fail importing app | Required env vars (`ANTHROPIC_API_KEY`, `SUPABASE_JWT_SECRET`) not set |
| RDS connection pool exhausted | Pool size capped — see recent commit `d17fe8d`; use one async session per request |
