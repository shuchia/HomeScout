# Backend CLAUDE.md

This file provides Claude Code guidance for the HomeScout backend, focusing on the data collection architecture.

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

**All apartment endpoints** (`get/{id}`, `batch`, `compare`, `list`, `count`, `stats`) check `is_database_enabled()` and query the appropriate source. The compare endpoint also calls Claude AI for head-to-head analysis via `compare_apartments_with_analysis()`, using `asyncio.to_thread()` to avoid blocking the async event loop.

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
| `celery_app.py` | Celery configuration, task routes, beat schedule |
| `database.py` | Async SQLAlchemy engine, session management |
| `alembic/` | Database migrations |

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

## Environment Variables

### Required for Data Collection

```bash
# Database
USE_DATABASE=true
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/homescout

# Redis (Celery broker)
REDIS_URL=redis://localhost:6379/0

# Apify (Zillow, Apartments.com)
APIFY_API_TOKEN=your_token

# ScrapingBee (Craigslist)
SCRAPINGBEE_API_KEY=your_key
```

### Optional

```bash
# S3 image caching
S3_BUCKET_NAME=homescout-images
AWS_REGION=us-west-2
CLOUDFRONT_DOMAIN=d123.cloudfront.net

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

## Admin API Endpoints

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

## Database Indexes

`ApartmentModel` has indexes on:
- `city`, `rent`, `bedrooms`, `bathrooms`, `property_type`
- `source`, `content_hash`, `is_active`
- Composite: `(city, rent, bedrooms)` for search queries
