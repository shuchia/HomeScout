# Continuous Scraping Pipeline Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Production-grade continuous scraping pipeline for apartments.com across 20+ East Coast markets with tiered freshness, confidence-based invalidation, and resilient error handling.

**Architecture:** Enhanced Celery Pipeline — a dispatcher task runs hourly, queries a database-driven `MarketConfig` table to determine which cities need scraping, and spawns independent per-city scrape tasks. Listing freshness is tracked via a confidence score that decays over time and triggers active verification before deactivation.

**Tech Stack:** Celery + Redis (task queue), Apify (apartments.com scraper), PostgreSQL + async SQLAlchemy (storage), Alembic (migrations)

---

## 1. Market Configuration & City Onboarding

A `market_configs` database table drives all scheduling. Adding a new city = one INSERT. The dispatcher picks it up automatically.

### `market_configs` Table

| Column | Type | Purpose |
|--------|------|---------|
| `id` | String (PK) | e.g. `"nyc"`, `"philadelphia"`, `"boston"` |
| `display_name` | String | "New York City" |
| `city` | String | City name for scraper input |
| `state` | String | 2-letter state code |
| `tier` | Enum | `hot` (every 6h), `standard` (every 12h), `cool` (daily) |
| `is_enabled` | Boolean | Toggle scraping on/off without deleting |
| `max_listings_per_scrape` | Integer | Default 100, tunable per market |
| `scrape_frequency_hours` | Integer | Derived from tier but overridable (6, 12, 24) |
| `last_scrape_at` | DateTime | When the last scrape completed |
| `last_scrape_status` | String | `completed`, `failed`, `partial` |
| `consecutive_failures` | Integer | For circuit breaker logic |
| `created_at` | DateTime | When this market was added |

### Initial Market List

| Tier | Cities |
|------|--------|
| **Hot** (6h) | New York City, Boston, Washington DC, Philadelphia |
| **Standard** (12h) | Pittsburgh, Baltimore, Newark, Jersey City, Cambridge, Arlington VA |
| **Cool** (24h) | Bryn Mawr, Hoboken, Stamford, New Haven, Providence, Richmond, Charlotte, Raleigh, Hartford |

---

## 2. Dispatcher Pattern & Scheduling

Celery beat has 3 fixed orchestrator tasks. No city-specific entries.

### Beat Schedule

| Task | Frequency | Purpose |
|------|-----------|---------|
| `dispatch_scrapes` | Every 1 hour | Check which markets are due, spawn scrape tasks |
| `decay_and_verify` | Every 1 hour | Update confidence scores, dispatch verification |
| `cleanup_maintenance` | Daily at 3 AM | Deactivate dead listings, vacuum DB, reset counters |

### `dispatch_scrapes` Logic

```
Every hour:
  1. Query market_configs WHERE is_enabled = true
  2. For each market:
     - Skip if last_scrape_at + scrape_frequency_hours > now
     - Skip if consecutive_failures >= 3 (circuit breaker)
     - Skip if scrape already running (ScrapeJobModel status='running')
     - Dispatch scrape_city_task(market_id) with random 0-60s delay (staggering)
  3. Log: "Dispatched N scrapes for M markets"
```

### Queue Structure

- `scraping` queue — all scrape tasks
- `maintenance` queue — cleanup, verification, decay tasks
- `celery` (default) — everything else

---

## 3. Listing Lifecycle & Confidence Scoring

Every listing gets a `freshness_confidence` score (0-100) that decays over time based on market tier.

### New Columns on `apartments` Table

| Column | Type | Purpose |
|--------|------|---------|
| `freshness_confidence` | Integer | 0-100, resets to 100 on every re-see |
| `confidence_updated_at` | DateTime | When confidence was last recalculated |
| `verification_status` | String | `null`, `pending`, `verified`, `gone` |
| `verified_at` | DateTime | When last actively verified |
| `times_seen` | Integer | Total scrapes this listing appeared in |
| `first_seen_at` | DateTime | When first scraped |
| `market_id` | String (FK) | References market_configs.id |

### Lifecycle States

```
NEW LISTING FOUND
    │
    ▼
Active (confidence=100, is_active=1)
    │
    │ ← Re-seen in scrape → confidence resets to 100
    │
    ▼ (not seen, confidence decays)
    │
Aging (confidence 50-99, is_active=1)
    │  UI shows: "Listed X days ago"
    │
    ▼ (confidence drops below 40)
    │
Verification Triggered (verification_status='pending')
    │
    ├─ Verified still active → confidence=80, verification_status='verified'
    │
    └─ Gone / 404 / rented → is_active=0, verification_status='gone'
    │
    ▼ (confidence decays below 10 with no verification possible)
    │
Inactive (is_active=0)
    Not shown in search results. Kept in DB for deduplication.
```

### Decay Formula

```
hours_since_seen = (now - last_seen_at).total_hours
decay_rate = based on market tier:
  hot:      -3 per hour  (hits 40 threshold in ~20h)
  standard: -2 per hour  (hits 40 threshold in ~30h)
  cool:     -1 per hour  (hits 40 threshold in ~60h)

freshness_confidence = max(0, 100 - (hours_since_seen * decay_rate))
```

### `decay_and_verify` Task (Hourly)

1. Recalculate `freshness_confidence` for all active listings based on `last_seen_at` and market tier
2. Find listings where `freshness_confidence < 40` AND `verification_status` is null → dispatch `verify_listing`
3. Find listings where `freshness_confidence = 0` AND `verification_status != 'verified'` → set `is_active = 0`

### `verify_listing` Task

- HTTP request to `source_url`
- 404 or "no longer available" text → mark `gone`
- Still live → confidence=80, mark `verified`
- Request fails (timeout, blocked) → leave `pending`, retry next cycle

---

## 4. Scrape Pipeline

### `scrape_city_task` Flow

```
scrape_city_task(market_id)
    │
    ▼
1. Load MarketConfig from DB
2. Create ScrapeJobModel (status='running')
3. Check rate limits on DataSourceModel → abort if exceeded
    │
    ▼
4. ApifyService.scrape(city, state, max_listings)
    │
    ├─ Success → raw listings
    ├─ Timeout → mark job 'failed', increment consecutive_failures, STOP
    └─ Error → retry up to 3x with exponential backoff
    │
    ▼
5. NormalizationService.normalize_batch(raw_listings)
    │  - Drop listings that fail validation (log + count as errors)
    │  - Return (normalized_listings, error_count)
    │
    ▼
6. Load existing hashes + listings for this market from DB
7. DeduplicationService.deduplicate_batch(normalized, existing)
    │  - New listings: insert with confidence=100, times_seen=1
    │  - Re-seen listings: update last_seen_at, confidence=100, times_seen+=1
    │  - Merges: update with richer data, reset confidence
    │  - Return (new_listings, updates_to_existing, duplicates_skipped)
    │
    ▼
8. Bulk save to PostgreSQL (batch INSERT/UPDATE)
9. Update ScrapeJobModel with metrics
10. Update MarketConfig: last_scrape_at=now, consecutive_failures=0
11. Update DataSourceModel rate limit counters
```

### Key Behaviors

- **Rate limiting enforced**: Check `DataSourceModel.can_make_request()` before calling Apify
- **Confidence reset on re-see**: Dedup finds existing listing → confidence=100, update `last_seen_at`
- **Batch DB operations**: Bulk INSERT/UPDATE for performance at scale
- **Partial success**: Failed normalization on 5 of 100 listings → save the other 95
- **Per-market job tracking**: Each city gets its own `ScrapeJobModel` record

### Dedup Return Signature Change

Old: `(unique_listings, duplicates)` — skips duplicates
New: `(new_listings, updates_to_existing, duplicates_skipped)` — updates existing on re-see

---

## 5. Error Handling & Resilience

### Task-Level Retries

| Failure Type | Retry Strategy | Max Retries |
|-------------|---------------|-------------|
| Apify timeout (>600s) | Retry with 2x timeout (1200s) | 2 |
| Apify rate limit (429) | Retry after 5 min backoff | 3 |
| Apify server error (5xx) | Exponential backoff (60s, 120s, 240s) | 3 |
| Network error | Exponential backoff (30s, 60s, 120s) | 3 |
| Normalization failure | No retry (bad data, skip listing) | 0 |
| DB write failure | Retry after 10s | 2 |
| Verification request blocked | Skip, retry next cycle | 0 |

### Market-Level Circuit Breaker

```
consecutive_failures on MarketConfig:
  0-2: Normal operation
  3+:  Circuit OPEN — dispatcher skips this market

Reset: cleanup_maintenance resets to 0 daily at 3 AM
  → Market gets one fresh attempt per day when circuit is open
```

### Stale Job Detection

If `ScrapeJobModel` has `status='running'` for >30 minutes, maintenance marks it `failed` and increments `consecutive_failures`.

### Graceful Degradation

If scraping goes down entirely, the API serves existing data. Listings decay in confidence, UI shows increasingly stale data, but nothing breaks. When scraping resumes, confidence resets.

---

## 6. Frontend Integration & API Changes

### New Fields on Apartment Response

```json
{
  "freshness_confidence": 85,
  "first_seen_at": "2026-02-15T10:00:00Z",
  "times_seen": 4
}
```

### Freshness Badge on ApartmentCard

| Confidence | Display |
|-----------|---------|
| 80-100 | Green "Recently verified" or no badge |
| 50-79 | Yellow "Listed X days ago" |
| 40-49 | Orange "May no longer be available" |
| Below 40 | Not shown (filtered server-side) |

### API Filter

Search and list endpoints add default: `WHERE freshness_confidence >= 40 AND is_active = 1`

### New Admin Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/admin/markets` | GET | List all market configs |
| `/api/admin/markets` | POST | Add new market |
| `/api/admin/markets/{id}` | PUT | Update tier, enable/disable |
| `/api/admin/markets/{id}/scrape` | POST | Trigger immediate scrape |

---

## 7. Database Migration

### New Table

`market_configs` — see schema in Section 1.

### Altered Table: `apartments`

7 new columns: `freshness_confidence`, `confidence_updated_at`, `verification_status`, `verified_at`, `times_seen`, `first_seen_at`, `market_id` (FK)

3 new indexes: `freshness_confidence`, `verification_status`, `market_id`

### Migration Strategy

1. Single Alembic migration for all changes
2. Truncate `apartments` table (fresh start)
3. Seed `market_configs` with all East Coast markets
4. First scrape cycle populates fresh data with all new fields

---

## 8. Components Summary

| Component | Status | Work |
|-----------|--------|------|
| `MarketConfig` model | New | New table + ORM model |
| `apartments` schema | Modify | 7 new columns + 3 indexes |
| Alembic migration | New | Create table, alter columns, seed data, truncate |
| `dispatch_scrapes` task | New | Hourly dispatcher reading market_configs |
| `scrape_city_task` | Modify | Rate limit enforcement, confidence reset, per-market jobs |
| `DeduplicationService` | Modify | Return (new, updates, skipped) instead of (unique, duplicates) |
| `decay_and_verify` task | New | Confidence recalculation + verification dispatch |
| `verify_listing` task | New | HTTP check on source_url |
| `cleanup_maintenance` | Modify | Circuit breaker reset, stale job detection |
| Celery beat schedule | Modify | Replace city-specific entries with 3 orchestrator tasks |
| `ApartmentModel.to_dict()` | Modify | Expose freshness_confidence, first_seen_at, times_seen |
| API endpoints | Modify | Confidence filter, new admin/markets endpoints |
| Frontend types | Modify | Add freshness fields to Apartment interface |
| `ApartmentCard` | Modify | Freshness badge |
