# Backend CLAUDE.md

This file provides Claude Code guidance for the HomeScout backend, covering authentication, monetization, data collection, and API architecture.

## Quick Commands

```bash
# Activate virtual environment first
source .venv/bin/activate

# Start API server (use python -m to avoid --reload issues with venv)
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Start Celery worker (for data collection) - requires Redis
celery -A app.celery_app worker --loglevel=info -Q celery,scraping,maintenance

# Start Celery beat (scheduler) - for automated daily scrapes
celery -A app.celery_app beat --loglevel=info

# Run database migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"
```

## Startup Prerequisites

```bash
# 1. PostgreSQL must be running (for database mode)
brew services start postgresql@16
lsof -i :5432  # Verify

# 2. Redis must be running (for Celery)
brew services start redis
redis-cli ping  # Should return PONG

# 3. Environment variables (.env)
USE_DATABASE=true
DATABASE_URL=postgresql+asyncpg://user@localhost:5432/homescout
REDIS_URL=redis://localhost:6379/0
ANTHROPIC_API_KEY=your-key
APIFY_API_TOKEN=your-token  # For apartments.com scraping
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
```

## Verification

```bash
# Check API health
curl http://localhost:8000/health

# Check database stats
curl http://localhost:8000/api/apartments/stats

# List apartments by city
curl "http://localhost:8000/api/apartments/list?city=Pittsburgh"

# Trigger manual scrape
curl -X POST http://localhost:8000/api/admin/data-collection/jobs \
  -H "Content-Type: application/json" \
  -d '{"source": "apartments_com", "max_listings": 30}'
```

## Architecture Overview

HomeScout backend has two modes:

1. **JSON Mode** (default): Uses static `app/data/apartments.json`
2. **Database Mode**: Uses PostgreSQL + automated data collection

Set `USE_DATABASE=true` in `.env` to enable database mode.

**All apartment endpoints** (`get/{id}`, `batch`, `compare`, `list`, `count`, `stats`) check `is_database_enabled()` and query the appropriate source.

### Tier-Gated Endpoints
The search and compare endpoints are tier-gated:
- **`/api/search`**: Pro gets Claude AI scoring; free gets filtered results (3 searches/day via Redis counter); anonymous gets filtered results with no limit tracking
- **`/api/apartments/compare`**: Pro gets Claude head-to-head analysis; free/anonymous get basic comparison table without AI analysis
- Auth is via Supabase JWT (`auth.py` → `get_optional_user`), tier checked via `TierService.get_user_tier()`

## Data Collection Pipeline

```
Celery Beat (scheduler)
    │
    ↓ triggers every 6h (Zillow/Apartments.com) or daily (Craigslist)
    │
scrape_source task (tasks/scrape_tasks.py)
    │
    ↓ selects scraper based on source
    │
┌───┴───────────────────────────────────────┐
│ ApifyService          │ ScrapingBeeService │
│ (Zillow, Apartments.com) │ (Craigslist)     │
└───────────────────────┴────────────────────┘
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
    │
    ↓ unique listings only
    │
PostgreSQL (ApartmentModel)
```

## Key Files

### Core Infrastructure

| File | Purpose |
|------|---------|
| `celery_app.py` | Celery configuration, task routes, beat schedule (4 tasks) |
| `database.py` | Async SQLAlchemy engine, session management |
| `auth.py` | Supabase JWT verification (`get_current_user`, `get_optional_user`) |
| `alembic/` | Database migrations |

### Auth & Monetization

| File | Purpose |
|------|---------|
| `auth.py` | JWT decode (HS256, audience "authenticated"), `UserContext` dataclass |
| `services/tier_service.py` | Tier checking (Supabase), Redis daily search metering, tier updates |
| `services/analytics_service.py` | Fire-and-forget event logging to Supabase `analytics_events` table |
| `routers/billing.py` | Stripe checkout, portal, webhook endpoints |
| `routers/saved_searches.py` | Saved search CRUD (Pro only) |
| `middleware/rate_limit.py` | Redis-based rate limiting (60/min auth, 10/min anon, 10/min expensive) |
| `tasks/alert_tasks.py` | Daily email alerts for Pro users via Resend |

### ORM Models (`models/`)

| Model | Table | Purpose |
|-------|-------|---------|
| `ApartmentModel` | `apartments` | Apartment listings with source tracking |
| `ScrapeJobModel` | `scrape_jobs` | Scrape job status and metrics |
| `DataSourceModel` | `data_sources` | Source configuration (rate limits, schedules) |
| `MarketConfigModel` | `market_configs` | Market scraping configuration (tier, frequency, circuit breaker) |

### Scrapers (`services/scrapers/`)

| File | Purpose |
|------|---------|
| `base_scraper.py` | Abstract base class, `ScrapedListing` dataclass |
| `apify_service.py` | Apify SDK for Zillow, Apartments.com, Realtor.com |
| `scrapingbee_service.py` | ScrapingBee API for Craigslist |

### Data Processing (`services/`)

| File | Purpose |
|------|---------|
| `normalization/normalizer.py` | Field validation, quality scoring |
| `normalization/address_standardizer.py` | Address parsing and normalization |
| `deduplication/deduplicator.py` | Content hashing, fuzzy matching |
| `storage/s3_service.py` | Image caching in S3 |

### Celery Tasks (`tasks/`)

| File | Purpose |
|------|---------|
| `scrape_tasks.py` | `scrape_source`, `scrape_city_task` |
| `maintenance_tasks.py` | `cleanup_stale_listings`, `reset_rate_limits`, `vacuum_database` |
| `alert_tasks.py` | `send_daily_alerts` — email Pro users with new matching apartments |

## Environment Variables

### Required

```bash
# Claude AI
ANTHROPIC_API_KEY=your-claude-api-key

# Supabase (auth + tier management)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret

# Stripe (payments)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...

# Database
USE_DATABASE=true
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/homescout

# Redis (Celery broker + rate limiting + search metering)
REDIS_URL=redis://localhost:6379/0
```

### Required for Data Collection

```bash
# Apify (Zillow, Apartments.com)
APIFY_API_TOKEN=your_token

# ScrapingBee (Craigslist)
SCRAPINGBEE_API_KEY=your_key
```

### Optional

```bash
# Email alerts (Resend)
RESEND_API_KEY=re_...
ALERT_FROM_EMAIL=alerts@homescout.app

# S3 image caching
S3_BUCKET_NAME=homescout-images
AWS_REGION=us-west-2
CLOUDFRONT_DOMAIN=d123.cloudfront.net

# CORS
FRONTEND_URL=http://localhost:3000

# Debug
SQL_ECHO=false
```

## Celery Beat Schedule

Defined in `celery_app.py`:

| Task | Schedule | Description |
|------|----------|-------------|
| `dispatch_scrapes` | Every hour at :00 | Check market_configs, spawn scrape tasks for due markets |
| `decay_and_verify` | Every hour at :30 | Recalculate freshness confidence, trigger verification |
| `cleanup_maintenance` | Daily at 3 AM | Deactivate dead listings, reset circuit breakers, fail stale jobs |
| `send_daily_alerts` | Daily at 1 PM UTC (8 AM ET) | Email Pro users with new listings matching saved searches |

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

# Rich content
description: str
amenities: JSONB        # List of strings
images: JSONB           # Original URLs
images_cached: JSONB    # S3 cached URLs

# Quality & deduplication
content_hash: str       # SHA256 for deduplication
data_quality_score: int # 0-100

# Status
is_active: int          # 1=active, 0=removed
last_seen_at: datetime  # Last time seen in scrape
```

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

## API Endpoints

### Tier-Gated Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/search` | POST | Optional | Pro: Claude AI scoring; Free: filtered (3/day); Anonymous: filtered |
| `/api/apartments/compare` | POST | Optional | Pro: Claude analysis; Free/Anonymous: basic comparison |
| `/api/saved-searches` | GET | Required | List user's saved searches |
| `/api/saved-searches` | POST | Required (Pro) | Create saved search |
| `/api/saved-searches/{id}` | DELETE | Required | Delete saved search |

### Billing Endpoints

Router: `routers/billing.py`

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/billing/checkout` | POST | Required | Create Stripe Checkout Session for Pro upgrade |
| `/api/billing/portal` | POST | Required | Create Stripe Customer Portal session |
| `/api/webhooks/stripe` | POST | Stripe sig | Handle Stripe webhook events |

Stripe webhook events handled:
- `checkout.session.completed` → set tier to "pro", store stripe_customer_id
- `customer.subscription.updated` → update subscription_status, current_period_end
- `customer.subscription.deleted` → revert tier to "free"
- `invoice.payment_failed` → set subscription_status to "past_due"

### Admin API Endpoints

Router: `routers/data_collection.py`

```bash
# Trigger manual scrape
POST /api/admin/data-collection/jobs
{"source": "zillow", "city": "San Francisco", "state": "CA"}

# List jobs
GET /api/admin/data-collection/jobs

# Get job status
GET /api/admin/data-collection/jobs/{job_id}

# Data sources
GET /api/admin/data-collection/sources
PUT /api/admin/data-collection/sources/{source_id}

# Metrics
GET /api/admin/data-collection/metrics

# Health check
GET /api/admin/data-collection/health
```

## Common Tasks

### Add a new scraping source

1. Create new service in `services/scrapers/` extending `BaseScraper`
2. Implement `scrape()` and `_normalize_listing()` methods
3. Add actor ID to `ApifyService.ACTORS` or subdomain to `ScrapingBeeService`
4. Add schedule to `celery_app.conf.beat_schedule`

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

# Synchronous call
result = scrape_city_task.delay("zillow", "San Francisco", "CA", max_listings=50)
print(result.get())  # Wait for result
```

## Authentication & Tier System

### JWT Verification (`auth.py`)
- Decodes Supabase JWTs using HS256 with `SUPABASE_JWT_SECRET`
- Audience: `"authenticated"`
- `get_current_user(authorization)` → `UserContext` or 401
- `get_optional_user(authorization)` → `UserContext | None` (never raises)
- `UserContext` dataclass: `user_id: str`, `email: str | None`

### Tier Service (`services/tier_service.py`)
- `TierService.get_user_tier(user_id)` → queries `profiles.user_tier` from Supabase (defaults to "free")
- `TierService.check_search_limit(user_id)` → Redis counter `search_count:{user_id}:{date}` with 48h TTL
- `TierService.increment_search_count(user_id)` → Redis INCR
- `TierService.update_user_tier(user_id, tier, **kwargs)` → updates Supabase profile (called from Stripe webhooks)
- Fail-open: if Redis or Supabase is down, defaults to allowing requests
- Module-level `supabase_admin` client using service role key (bypasses RLS)

### Tier Limits
| Feature | Free | Pro |
|---------|------|-----|
| Searches/day | 3 (Redis counter) | Unlimited |
| Claude AI scoring | No | Yes |
| Claude comparison analysis | No | Yes |
| Saved searches | No (403) | Unlimited |
| Email alerts | No | Daily digest |
| Rate limit | 10 req/min | 60 req/min |

### Rate Limiting (`middleware/rate_limit.py`)
- Redis sliding window counter per minute
- Identity: authenticated users keyed by token hash, anonymous by IP
- Expensive paths (`/api/search`, `/api/apartments/compare`): 10 req/min regardless of auth
- Returns 429 with `{"detail": "Rate limit exceeded. Please slow down."}`
- Fail-open on Redis errors
- Skipped when `TESTING` env var is set (conftest.py sets this)

## Testing

```bash
# Run all backend tests (77 tests)
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
```

| Test File | Count | Coverage |
|-----------|-------|----------|
| `test_auth.py` | 6 | JWT verification, get_current_user, get_optional_user |
| `test_tier_service.py` | 5 | Tier checking, Redis metering, fail-open |
| `test_billing.py` | 13 | Stripe checkout, portal, webhooks, customer lookup |
| `test_search_gating.py` | 9 | Anonymous/free/pro search behavior, daily limits |
| `test_compare_gating.py` | 9 | Anonymous/free/pro compare behavior |
| `test_saved_searches.py` | 8 | CRUD, auth required, Pro-only creation |
| `test_rate_limit.py` | 13 | Rate limits, expensive paths, fail-open |
| `test_alert_tasks.py` | 5 | Daily email alerts, filtering, error handling |
| `test_webhooks.py` | 2 | Supabase webhook auth |

Note: 5 pre-existing failures in `test_apartments_router.py` (don't mock TierService).

## Database Indexes

`ApartmentModel` has indexes on:
- `city`, `rent`, `bedrooms`, `bathrooms`, `property_type`
- `source`, `content_hash`, `is_active`
- Composite: `(city, rent, bedrooms)` for search queries

## Supabase Migrations

| Migration | Purpose |
|-----------|---------|
| `001_initial_schema.sql` | profiles, favorites, saved_searches, notifications tables + RLS |
| `002_add_tier_columns.sql` | user_tier, stripe_customer_id, subscription_status, current_period_end on profiles |
| `003_add_analytics_events.sql` | analytics_events table (event_type, metadata JSONB, user_id FK) |
| `004_update_saved_searches.sql` | last_alerted_at, is_active on saved_searches + service update policy |
