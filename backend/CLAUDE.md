# Backend CLAUDE.md

Claude Code guidance for the Snugd backend (FastAPI). Covers authentication, monetization, data collection, the touring pipeline, and API architecture.

> Product name is **Snugd**; module/path names still say "HomeScout".

## Quick Commands

```bash
# Activate virtual environment first
source .venv/bin/activate

# Start API server (use python -m to avoid --reload issues with venv)
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Start Celery worker (data collection, tours, transcription) - requires Redis
celery -A app.celery_app worker --loglevel=info -Q celery,scraping,maintenance

# Start Celery beat (scheduler)
celery -A app.celery_app beat --loglevel=info

# Run database migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"
```

**Never use `--reload`** — it watches `.venv/` and breaks.

## Startup Prerequisites

```bash
# 1. PostgreSQL must be running (for database mode)
brew services start postgresql@16
lsof -i :5432  # Verify

# 2. Redis must be running (for Celery + rate limiting + search metering)
brew services start redis
redis-cli ping  # Should return PONG

# 3. Environment variables (.env) — see full list below
USE_DATABASE=true
DATABASE_URL=postgresql+asyncpg://user@localhost:5432/homescout
REDIS_URL=redis://localhost:6379/0
ANTHROPIC_API_KEY=your-key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret
```

## Verification

```bash
# Check API health
curl http://localhost:8000/health

# Check database stats
curl http://localhost:8000/api/apartments/stats

# List apartments by city
curl "http://localhost:8000/api/apartments/list?city=Pittsburgh"

# Prometheus-style metrics
curl http://localhost:8000/metrics

# Trigger manual scrape for a specific market (note: /jobs is broken,
# see docs/launch-readiness.md #9). Body for /markets/{id}/scrape is empty.
# All admin endpoints require X-Admin-Key — pull from AWS Secrets Manager.
ADMIN_API_KEY=$(aws secretsmanager get-secret-value --secret-id snugd/qa/secrets \
  --region us-east-1 --query SecretString --output text | jq -r .ADMIN_API_KEY)
curl -X POST http://localhost:8000/api/admin/data-collection/markets/pittsburgh/scrape \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

## Architecture Overview

Two data modes:

1. **JSON Mode** (default): static `app/data/apartments.json`
2. **Database Mode**: PostgreSQL + automated data collection

Set `USE_DATABASE=true` in `.env` to enable database mode. **All apartment endpoints** (`get/{id}`, `batch`, `compare`, `list`, `count`, `stats`) check `is_database_enabled()` and query the appropriate source.

### Tier-Gated Endpoints
- **`/api/search`**: Pro gets `heuristic_score` immediately + Claude AI scoring via a separate `/api/search/score-batch` call (lazy AI); free gets filtered results (20/day via Redis counter, `FREE_DAILY_SEARCH_LIMIT` in `tier_service.py`); anonymous gets filtered results with no limit tracking.
- **`/api/apartments/compare`**: Pro gets Claude head-to-head analysis; free/anonymous get a basic comparison table.
- Auth is via Supabase JWT (`auth.py` → `get_optional_user`), tier checked via `TierService.get_user_tier()`.

### Claude Models
| Use | Model |
|-----|-------|
| Search scoring, inquiry emails, note enhancement, day plan | `claude-haiku-4-5-20251001` |
| Head-to-head comparison, decision brief | `claude-sonnet-4-5-20250929` |

15 s timeout (search), 45 s (compare); heuristic fallback on any exception; max 5 concurrent via `asyncio.Semaphore(5)`; system-prompt caching enabled. See `services/claude_service.py`.

## Data Collection Pipeline

```
Celery Beat (scheduler)
    │
    ↓ dispatch_scrapes, hourly at :00 — picks markets that are due
    │
tasks/dispatcher.py → scrape_source (tasks/scrape_tasks.py)
    │
    ↓ selects scraper based on source
    │
┌───┴───────────────────────────────────────┐
│ ApifyService              │ ScrapingBeeService │
│ (Zillow, Apartments.com,  │ (Craigslist)       │
│  Realtor, Rent.com)       │                    │
└───────────────────────────┴────────────────────┘
    │
    ↓ raw listings
    │
NormalizationService (services/normalization/normalizer.py)
    │ - validates required fields (address, rent, beds, baths)
    │ - standardizes address format
    │ - normalizes property type
    │ - calculates quality score (0-100)
    │
    ↓ normalized listings
    │
DeduplicationService (services/deduplication/deduplicator.py)
    │ - generates SHA256 content hash
    │ - checks against existing hashes
    │ - fuzzy address matching (90% threshold)
    │ - reactivates decayed listings on re-see instead of colliding on insert
    │
    ↓ unique listings only
    │
PostgreSQL (ApartmentModel)
    │
    ├─→ floorplan buckets built inline (services/floorplans.py)
    ├─→ pricing model detected (services/pricing_model_detector.py)
    └─→ true cost precomputed (services/cost_estimator.py)
```

## Key Files

### Core Infrastructure

| File | Purpose |
|------|---------|
| `main.py` | App setup, router registration, `/health`, `/metrics`, `/api/search`, `/api/search/score-batch` |
| `celery_app.py` | Celery config, task routes, beat schedule (5 tasks) |
| `database.py` | Async SQLAlchemy engine, session management |
| `auth.py` | Supabase JWT verification (`get_current_user`, `get_optional_user`) |
| `schemas.py` | Pydantic models — **must stay in sync with `frontend/types/`** |
| `alembic/` | Database migrations |

### Routers (`routers/`)

| File | Prefix | Purpose |
|------|--------|---------|
| `apartments.py` | `/api/apartments` | list, get, batch, compare |
| `tours.py` | `/api/tours` | Full touring pipeline — tours, notes, photos, tags, AI features |
| `commute.py` | `/api/user/locations`, `/api/apartments/commute` | Saved locations + commute times |
| `billing.py` | `/api/billing`, `/api/webhooks/stripe` | Stripe checkout, portal, webhooks |
| `saved_searches.py` | `/api/saved-searches` | Saved search CRUD (Pro only to create) |
| `invite.py` | `/api/invite`, `/api/admin/invite-codes` | Beta invite redeem/status, code minting |
| `feedback.py` | `/api/feedback` | Beta feedback submission |
| `waitlist.py` | `/api/waitlist`, `/api/admin/waitlist` | Public waitlist signup + admin listing |
| `analytics.py` | `/api/analytics/event` | Fire-and-forget event logging |
| `beta_admin.py` | `/api/admin` | `GET /beta-report` — beta usage snapshot |
| `data_collection.py` | `/api/admin/data-collection` | Scrape jobs, sources, markets, metrics |
| `webhooks.py` | `/webhooks` | Supabase `check-matches` webhook |

### Auth & Monetization

| File | Purpose |
|------|---------|
| `auth.py` | JWT decode (HS256, audience "authenticated"), `UserContext` dataclass |
| `services/tier_service.py` | Tier checking (Supabase), Redis daily search metering, tier updates |
| `services/analytics_service.py` | Fire-and-forget event logging to Supabase `analytics_events` |
| `middleware/rate_limit.py` | Redis-based rate limiting (120/min auth, 30/min anon, 20/min expensive) |
| `tasks/alert_tasks.py` | Daily email alerts for Pro users via Resend |

### ORM Models (`models/`)

| Model | Table | Purpose |
|-------|-------|---------|
| `ApartmentModel` | `apartments` | Listings with source tracking, freshness, true cost |
| `ApartmentFloorplanModel` | `apartment_floorplans` | Per-bedroom/bath buckets for floorplan-aware search |
| `ScrapeJobModel` | `scrape_jobs` | Scrape job status and metrics |
| `DataSourceModel` | `data_sources` | Source configuration (rate limits, schedules) |
| `MarketConfigModel` | `market_configs` | Market scraping config (tier, frequency, circuit breaker) |

### Scrapers (`services/scrapers/`)

| File | Purpose |
|------|---------|
| `base_scraper.py` | Abstract base class, `ScrapedListing` dataclass |
| `apify_service.py` | Apify SDK — Zillow, Apartments.com, Realtor, Rent.com |
| `scrapingbee_service.py` | ScrapingBee API for Craigslist |

Apify actors (overridable by env var):

| Source | Default actor | Env override |
|--------|---------------|--------------|
| `zillow` | `maxcopell~zillow-scraper` | `APIFY_ZILLOW_ACTOR_ID` |
| `apartments_com` | `epctex~apartments-scraper-api` | `APIFY_APARTMENTS_ACTOR_ID` |
| `realtor` | `epctex~realtor-scraper` | `APIFY_REALTOR_ACTOR_ID` |
| `rent_com` | `jupri~rent-com-scraper` | `APIFY_RENT_ACTOR_ID` |

### Data Processing & Domain Services (`services/`)

| File | Purpose |
|------|---------|
| `apartment_service.py` | Search/filter core; floorplan routing behind `USE_FLOORPLAN_SEARCH` |
| `claude_service.py` | All Anthropic calls — scoring, compare, emails, briefs, day plan |
| `scoring_service.py` | Heuristic scoring (the non-AI path and the AI fallback) |
| `floorplans.py` | Floorplan bucket building + per-bucket pricing |
| `pricing_model_detector.py` | Per-unit vs per-person (by-the-room / co-living) detection |
| `cost_estimator.py` | True-cost monthly + move-in calculation |
| `commute_service.py` | Commute time computation (Google Maps) |
| `distance.py` | Haversine / proximity helpers for radius search |
| `normalization/normalizer.py` | Field validation, quality scoring |
| `normalization/address_standardizer.py` | Address parsing and normalization |
| `deduplication/deduplicator.py` | Content hashing, fuzzy matching |
| `storage/s3_service.py` | Image caching in S3 |
| `storage/photo_service.py` | Tour photo upload + presigned URLs |
| `transcription/whisper_service.py` | OpenAI Whisper voice-note transcription |
| `monitoring/metrics.py` | `/metrics` counters |
| `monitoring/alerts.py` | Slack alerting via `SLACK_WEBHOOK_URL` |

### Celery Tasks (`tasks/`)

| File | Purpose |
|------|---------|
| `dispatcher.py` | `dispatch_scrapes` — pick due markets, spawn scrape tasks |
| `scrape_tasks.py` | `scrape_source`, `scrape_city_task`; builds floorplan buckets inline |
| `maintenance_tasks.py` | `decay_and_verify`, `cleanup_maintenance` |
| `alert_tasks.py` | `send_daily_alerts` — email Pro users with new matching apartments |
| `tour_reminder_tasks.py` | `check_tour_reminders` — upcoming-tour notifications |
| `transcription_tasks.py` | Async Whisper transcription of tour voice notes |
| `true_cost_tasks.py` | Backfill/recompute true cost |
| `_async_runner.py` | Helper to run async code inside sync Celery tasks |

## Environment Variables

Every variable actually read by `app/` (via `os.getenv` / `os.environ`):

### Required

```bash
ANTHROPIC_API_KEY=your-claude-api-key

# Supabase (auth + tier management)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret

# Database
USE_DATABASE=true
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/homescout

# Redis (Celery broker + rate limiting + search metering)
REDIS_URL=redis://localhost:6379/0
```

### Required for Data Collection

```bash
APIFY_API_TOKEN=your_token          # Zillow, Apartments.com, Realtor, Rent.com
SCRAPINGBEE_API_KEY=your_key        # Craigslist
```

### Billing

```bash
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
```

### Feature Flags

```bash
USE_DATABASE=true                   # JSON mode vs Postgres
USE_FLOORPLAN_SEARCH=false          # Floorplan-aware search (true on QA)
```

### Optional

```bash
# Admin API
ADMIN_API_KEY=...                   # defaults to "homescout-dev-admin-key"

# Voice notes
OPENAI_API_KEY=sk-...               # Whisper transcription

# Commute
GOOGLE_MAPS_API_KEY=...

# Email alerts (Resend)
RESEND_API_KEY=re_...
ALERT_FROM_EMAIL=alerts@snugd.ai
ALERT_EMAIL_ENABLED=true
ALERT_EMAIL_FROM=...
ALERT_EMAIL_TO=...

# S3 / images / tour photos
S3_BUCKET_NAME=snugd-images
AWS_REGION=us-east-1
CLOUDFRONT_DOMAIN=d123.cloudfront.net

# Supabase webhook auth
SUPABASE_WEBHOOK_SECRET=...

# Monitoring
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
LOG_LEVEL=INFO

# Runtime / infra
SERVICE_TYPE=api                    # api | worker | beat (set by ECS)
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
FRONTEND_URL=http://localhost:3000  # CORS
SQL_ECHO=false
TESTING=1                           # disables rate limiting in tests
```

## Celery Beat Schedule

Defined in `celery_app.py`:

| Task | Schedule | Description |
|------|----------|-------------|
| `dispatch_scrapes` | Every hour at :00 | Check `market_configs`, spawn scrape tasks for due markets |
| `decay_and_verify` | Every hour at :30 | Recalculate freshness confidence from `last_seen_at` using `TIER_DECAY_RATES`. Bulk verification off by default (`ENABLE_BULK_VERIFICATION`) |
| `cleanup_maintenance` | Daily at 3 AM UTC | Deactivate dead listings, reset circuit breakers, fail stale jobs |
| `send_daily_alerts` | Daily at 1 PM UTC (8 AM ET) | Email Pro users with new listings matching saved searches |
| `check_tour_reminders` | Every 10 minutes | Notify users about upcoming tours |

Task routes: `scrape_tasks.*` → `scraping` queue, `maintenance_tasks.*` → `maintenance` queue, everything else → `celery`.

## ApartmentModel Fields

Key fields in `models/apartment.py`:

```python
# Identity
id: str                 # Internal UUID
external_id: str        # ID from source (Zillow listing ID, etc.)
source: str             # "zillow", "apartments_com", "craigslist", "manual"
source_url: str         # Original listing URL

# Location
address: str            # Full address as displayed
address_normalized: str # Standardized format
city, state, zip_code   # Parsed components
latitude, longitude     # Coordinates

# Listing details
rent: int               # Monthly rent
bedrooms: int           # 0 = studio
bathrooms: float        # Supports 1.5
sqft: int
property_type: str      # "Apartment", "Condo", "House", "Townhouse"
available_date: str     # YYYY-MM-DD

# Pricing model
pricing_model: str              # "per_unit" (default) or "per_person"
pricing_model_confidence: float # 0.0-1.0

# True cost (precomputed at ingestion in DB mode)
true_cost_monthly: int
true_cost_move_in: int

# Rich content
description: str
amenities: JSONB        # List of strings
images: JSONB           # Original URLs
images_cached: JSONB    # S3 cached URLs

# Quality & deduplication
content_hash: str       # SHA256 for deduplication
data_quality_score: int # 0-100

# Freshness
freshness_confidence: int       # 0-100, decayed hourly by decay_and_verify
verification_status: str        # null | pending | verified | gone
                                # A blocked/ambiguous response leaves this null —
                                # never "verified" (see _verify_listing)
verified_at: datetime

# Status
is_active: int          # 1=active, 0=removed
last_seen_at: datetime  # Last time seen in scrape
```

**Freshness filter**: `/api/apartments/list` and `/api/search` only return rows with `freshness_confidence >= 40` (`apartments.py:147`). `/api/apartments/stats` counts all `is_active=1` rows, so the two intentionally diverge.

## ApartmentFloorplanModel Fields

`models/apartment_floorplan.py` — one row per (apartment, bedrooms, bathrooms) bucket:

```python
id: str                       # uuid4 hex
apartment_id: str             # FK → apartments
bedrooms: int                 # 0 = studio
bathrooms: float              # exact bath count of this bucket
min_rent, max_rent: int
min_sqft, max_sqft: int
available_units: int
earliest_available_date: str
model_ids: JSONB              # source-side floorplan/model identifiers
pricing_model: str            # per-bucket override of the parent listing
```

Search expands to floorplans for matching and collapses back to one card per physical building for display. See [docs/floorplan-search-architecture.md](../docs/floorplan-search-architecture.md).

## Quality Score Calculation

`NormalizationService._calculate_quality_score()` scores 0-100:

- **Required fields** (40 pts): address, rent, beds, baths
- **Optional fields** (40 pts): city, state, zip, neighborhood, sqft, date, description, amenities, images
- **Quality bonuses** (20 pts): 3+ images, 5+ amenities, coordinates, source URL

## Deduplication Strategy

`DeduplicationService.check_duplicate()`:

1. **Content hash match**: SHA256 of (normalized_address + rent_rounded_to_$50 + beds + baths)
2. **Fuzzy match**: Address similarity >90% AND rent within 10% AND same bedrooms

When duplicates found:
- Keep listing with higher quality score
- Merge unique data (images, amenities, description)
- A decayed/inactive listing seen again is **reactivated**, not re-inserted

## API Endpoints

### Core

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | — | Health check |
| `/metrics` | GET | — | Prometheus-style counters |
| `/api/apartments/count` | GET | — | Active listing count |
| `/api/apartments/stats` | GET | — | Stats over all `is_active=1` rows |
| `/api/apartments/list` | GET | — | Filtered list (freshness ≥ 40) |
| `/api/apartments/{id}` | GET | — | Single listing |
| `/api/apartments/batch` | POST | — | Up to 50 ids |

### Tier-Gated

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/search` | POST | Optional | Pro: heuristic + lazy Claude AI; Free: filtered (20/day); Anonymous: filtered |
| `/api/search/score-batch` | POST | Optional (Pro) | Claude AI scoring for an already-returned result set |
| `/api/apartments/compare` | POST | Optional | Pro: Claude analysis; Free/Anonymous: basic comparison |
| `/api/saved-searches` | GET | Required | List user's saved searches |
| `/api/saved-searches` | POST | Required (Pro) | Create saved search |
| `/api/saved-searches/{id}` | DELETE | Required | Delete saved search |

### Touring Pipeline

Router: `routers/tours.py`. All require auth; AI sub-features are Pro-gated.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tours` | POST / GET | Create tour (starts at stage `interested`) / list |
| `/api/tours/{id}` | GET / PATCH / DELETE | Read, update stage/decision, delete |
| `/api/tours/{id}/notes` | POST / GET | Text notes |
| `/api/tours/{id}/notes/voice` | POST (202) | Voice note → async Whisper transcription |
| `/api/tours/{id}/notes/{note_id}` | DELETE | Delete note |
| `/api/tours/{id}/photos` | POST / GET | Tour photos (presigned S3) |
| `/api/tours/{id}/photos/{photo_id}` | PATCH / DELETE | Update caption, delete |
| `/api/tours/{id}/tags` | POST | Add tag |
| `/api/tours/{id}/tags/{tag_id}` | DELETE | Remove tag |
| `/api/tours/tags/suggestions` | GET | Suggested tags |
| `/api/tours/{id}/inquiry-email` | POST | **Pro** — AI-drafted landlord inquiry |
| `/api/tours/{id}/enhance-note` | POST | **Pro** — AI note cleanup |
| `/api/tours/day-plan` | POST | **Pro** — AI day plan across scheduled tours |
| `/api/tours/decision-brief` | POST | **Pro** — AI brief over `toured`/`deciding` tours |

Stages: `interested` → `outreach_sent` → `scheduled` → `toured` → `deciding`.

Presigned photo thumbnail URLs are regenerated on tour read (they expire).

### Commute

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/user/locations` | GET / POST | Required | Saved commute destinations |
| `/api/user/locations/{id}` | DELETE | Required | Delete a location |
| `/api/apartments/commute` | POST | Optional | Commute times for a set of listings |

### Beta / Growth

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/invite/redeem` | POST | Required | Redeem an invite code → Pro |
| `/api/invite/status` | GET | Required | Current user's invite status |
| `/api/admin/invite-codes` | POST | `X-Admin-Key` | Mint codes |
| `/api/admin/beta-report` | GET | `X-Admin-Key` | Usage snapshot (`days`, `top_n`, `feedback_limit`) |
| `/api/feedback` | POST | Optional | Beta feedback |
| `/api/waitlist` | POST | — | Public waitlist signup |
| `/api/admin/waitlist` | GET | — | List waitlist entries |
| `/api/analytics/event` | POST (202) | Optional | Fire-and-forget event log |

### Billing

Router: `routers/billing.py`

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/billing/checkout` | POST | Required | Stripe Checkout Session for Pro upgrade |
| `/api/billing/portal` | POST | Required | Stripe Customer Portal session |
| `/api/webhooks/stripe` | POST | Stripe sig | Handle Stripe webhook events |

Stripe webhook events handled:
- `checkout.session.completed` → set tier to "pro", store `stripe_customer_id`
- `customer.subscription.updated` → update `subscription_status`, `current_period_end`
- `customer.subscription.deleted` → revert tier to "free"
- `invoice.payment_failed` → set `subscription_status` to "past_due"

### Admin — Data Collection

Router: `routers/data_collection.py` — **all endpoints require `X-Admin-Key`** (router-level dependency, mirrors `invite.py` and `beta_admin.py`).

```bash
# Trigger manual scrape — prefer /markets/{id}/scrape; the /jobs route below
# has a signature bug, see docs/launch-readiness.md #9.
POST /api/admin/data-collection/markets/{market_id}/scrape

GET  /api/admin/data-collection/jobs
GET  /api/admin/data-collection/jobs/{job_id}
GET  /api/admin/data-collection/sources
PUT  /api/admin/data-collection/sources/{source_id}
GET  /api/admin/data-collection/markets
PUT  /api/admin/data-collection/markets/{market_id}   # {is_enabled, tier, scrape_frequency_hours, max_listings_per_scrape}
GET  /api/admin/data-collection/metrics
GET  /api/admin/data-collection/health
POST /api/admin/data-collection/reset-false-verifications  # ?apply=true to write
POST /api/admin/data-collection/normalize-boston-cities     # fold Boston neighbourhood names
GET  /api/admin/data-collection/pipeline-health            # is work actually happening?
```

Markets are the only enable/disable lever for scheduled scraping.

## Authentication & Tier System

### JWT Verification (`auth.py`)
- Decodes Supabase JWTs using HS256 with `SUPABASE_JWT_SECRET`
- Audience: `"authenticated"`
- `get_current_user(authorization)` → `UserContext` or 401
- `get_optional_user(authorization)` → `UserContext | None` (never raises)
- `UserContext` dataclass: `user_id: str`, `email: str | None`

### Tier Service (`services/tier_service.py`)
- `FREE_DAILY_SEARCH_LIMIT = 20`
- `TierService.get_user_tier(user_id)` → queries `profiles.user_tier` from Supabase (defaults to "free")
- `TierService.check_search_limit(user_id)` → Redis counter `search_count:{user_id}:{date}` with 48h TTL
- `TierService.increment_search_count(user_id)` → Redis INCR
- `TierService.update_user_tier(user_id, tier, **kwargs)` → updates Supabase profile (called from Stripe webhooks and invite redemption)
- Fail-open: if Redis or Supabase is down, defaults to allowing requests
- Module-level `supabase_admin` client using service role key (bypasses RLS) — also used by `beta_admin.py`

### Tier Limits
| Feature | Free | Pro |
|---------|------|-----|
| Searches/day | 20 (Redis counter) | Unlimited |
| Claude AI scoring | No | Yes |
| Claude comparison analysis | No | Yes |
| Favorites | 5 max — **enforced client-side only** (`frontend/hooks/useFavorites.ts`), not by the API | Unlimited |
| Saved searches | No (403) | Unlimited |
| Email alerts | No | Daily digest |
| Tour AI (email, brief, day plan, note enhance) | No | Yes |
| Rate limit | 120 req/min | 120 req/min |

### Rate Limiting (`middleware/rate_limit.py`)
- Redis sliding window counter per minute
- `GLOBAL_LIMIT = 120` (authenticated), `ANON_LIMIT = 30` (anonymous), `EXPENSIVE_LIMIT = 20`
- Identity: authenticated users keyed by token hash, anonymous by IP
- Expensive paths (`/api/search`, `/api/apartments/compare`): 20 req/min regardless of auth
- Returns 429 with `{"detail": "Rate limit exceeded. Please slow down."}`
- Fail-open on Redis errors
- Skipped when `TESTING` env var is set (conftest.py sets this)

## Testing

```bash
# Run all backend tests (398 tests across 32 files)
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
```

| Test File | Count | Coverage |
|-----------|------:|----------|
| `test_apify_type_safety.py` | 42 | Apify payload shape/type guards |
| `test_tours.py` | 39 | Tour CRUD, notes, photos, tags, AI gating |
| `test_scoring_service.py` | 33 | Heuristic scoring |
| `test_cost_estimator.py` | 17 | True-cost monthly + move-in |
| `test_pricing_model_detector.py` | 17 | Per-unit vs per-person detection |
| `test_floorplans.py` | 16 | Bucket building, per-bucket pricing |
| `test_billing.py` | 13 | Stripe checkout, portal, webhooks |
| `test_rate_limit.py` | 13 | Rate limits, expensive paths, fail-open |
| `test_apartments_router.py` | 12 | Apartment endpoints |
| `test_compare_gating.py` | 11 | Anonymous/free/pro compare behavior |
| `test_apify_availability.py` | 11 | Availability parsing |
| `test_distance.py` | 10 | Haversine / proximity |
| `test_search_gating.py` | 10 | Anonymous/free/pro search, daily limits |
| `test_commute.py` | 9 | Locations CRUD, commute computation |
| `test_search_endpoint.py` | 8 | Search request/response |
| `test_search_floorplan_routing.py` | 8 | Flag-gated floorplan routing |
| `test_saved_searches.py` | 8 | CRUD, auth required, Pro-only creation |
| `test_auth.py` | 6 | JWT verification |
| `test_photo_service.py` | 6 | Tour photo upload/presign |
| `test_alert_tasks.py` | 5 | Daily email alerts |
| `test_tier_service.py` | 5 | Tier checking, Redis metering, fail-open |
| `test_proximity_search.py` | 5 | Radius search |
| `test_claude_cache.py` | 4 | System-prompt caching |
| `test_claude_data.py` | 4 | Claude payload construction |
| `test_whisper_service.py` | 4 | Transcription service |
| `test_budget_filter.py` | 3 | Strict budget filtering |
| `test_tour_reminder_tasks.py` | 3 | Reminder scheduling |
| `test_transcription_tasks.py` | 3 | Async transcription task |
| `test_webhooks.py` | 2 | Supabase webhook auth |

## Database Indexes

`ApartmentModel` has indexes on:
- `city`, `rent`, `bedrooms`, `bathrooms`, `property_type`
- `source`, `content_hash`, `is_active`, `freshness_confidence`
- Composite: `(city, rent, bedrooms)` for search queries

## Supabase Migrations

Applied in `supabase/migrations/` — see [supabase/CLAUDE.md](../supabase/CLAUDE.md) for table/RLS detail.

| Migration | Purpose |
|-----------|---------|
| `001_initial_schema.sql` | profiles, favorites, saved_searches, notifications + RLS + new-user trigger |
| `002_add_tier_columns.sql` | user_tier, stripe_customer_id, subscription_status, current_period_end |
| `003_add_analytics_events.sql` | analytics_events table |
| `004_update_saved_searches.sql` | last_alerted_at, is_active + service update policy |
| `005_tour_pipeline.sql` | tour_pipeline, tour_notes, tour_photos, tour_tags |
| `006_beta_launch.sql` | invite_codes, invite_redemptions, beta_feedback |
| `007_waitlist.sql` | waitlist table |
| `008_tour_contact_info.sql` | Contact fields on tour_pipeline |
| `009_add_user_locations.sql` | user_locations (commute destinations) |
| `010_tour_apartment_snapshot.sql` | apartment_snapshot/snapshot_at on tour_pipeline |

## Common Tasks

### Add a new scraping source

1. Create new service in `services/scrapers/` extending `BaseScraper`
2. Implement `scrape()` and `_normalize_listing()` methods
3. Add actor ID to `ApifyService.ACTORS` or subdomain to `ScrapingBeeService`
4. Add a `data_sources` row and enable it in `market_configs`

### Modify normalization rules

Edit `services/normalization/normalizer.py`:
- `PROPERTY_TYPES` dict for property type mapping
- `_validate_*` methods for field validation
- `_calculate_quality_score()` for scoring weights

### Change deduplication sensitivity

Edit `services/deduplication/deduplicator.py`:
- `generate_content_hash()` for hash components
- `_find_fuzzy_match()` threshold (default 0.9)
- Rent tolerance (default 10%)

### Run a one-off scrape

```python
from app.tasks.scrape_tasks import scrape_city_task

result = scrape_city_task.delay("zillow", "San Francisco", "CA", max_listings=50)
print(result.get())  # Wait for result
```

### Work on floorplan search

Set `USE_FLOORPLAN_SEARCH=true` locally — it is **off by default** and on in QA. Entry point is `apartment_service.py:96`; bucket construction is `services/floorplans.py` and happens inline during scrape (`scrape_tasks.py:462`).

## Common Issues

| Issue | Fix |
|-------|-----|
| `Event loop is closed` | Restart Celery worker |
| Server hangs at startup | Check Postgres: `lsof -i :5432` |
| Celery tasks not running | Check Redis: `redis-cli ping` |
| `--reload` causes issues | Don't use it |
| Port 8000 in use | `pkill -f "uvicorn app.main"` |
| Listings vanish from search but stats still counts them | Freshness filter (≥ 40) vs stats counting all active rows |
| Floorplan behavior differs from QA | `USE_FLOORPLAN_SEARCH` unset locally |
