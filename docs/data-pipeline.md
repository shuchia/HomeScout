# Data Pipeline

> Last verified: 2026-05-04 | Source of truth: this doc + the code it references

Listings are scraped from third-party sources via Apify (and ScrapingBee for legacy Craigslist), normalized, deduplicated, cost-enriched, and stored in Postgres for the API to serve.

## Quick Commands

```bash
# Trigger a manual scrape (admin endpoint)
curl -X POST http://localhost:8000/api/admin/data-collection/jobs \
  -H "Content-Type: application/json" \
  -d '{"source": "apartments_com", "city": "Pittsburgh", "state": "PA", "max_listings": 30}'

# Trigger a market-config-driven scrape
curl -X POST http://localhost:8000/api/admin/data-collection/markets/{market_id}/scrape

# Inspect Celery
celery -A app.celery_app inspect active
celery -A app.celery_app inspect scheduled

# Re-run cost backfill on existing rows (batched, runs as Celery task)
curl -X POST http://localhost:8000/api/admin/data-collection/backfill-fees

# One-off scrape from Python REPL
python -c "from app.tasks.scrape_tasks import scrape_city_task; \
  print(scrape_city_task.delay('apartments_com', 'Boston', 'MA', max_listings=50).get())"
```

## Architecture

```
Celery Beat ─ dispatch_scrapes (hourly :00)
                │
                ▼ reads market_configs (due markets)
                │
        scrape_city_task per market
                │
        ┌───────┴────────────────┐
        │                        │
   ApifyService            ScrapingBeeService (legacy)
   (apartments.com,        (Craigslist)
    Zillow, Realtor,
    Rent.com)
        │                        │
        ▼                        ▼
        ScrapedListing[]
                │
                ▼
   NormalizationService  ←→  AddressStandardizer
   (validate, standardize, quality_score 0–100)
                │
                ▼
   DeduplicationService
   (SHA256 content hash + 0.9 fuzzy address)
                │
                ▼
   CostEstimator (fills utilities/parking/pet/etc. from cost_estimates.json)
                │
                ▼
   ApartmentModel (Postgres)  ──→  exposed via /api/apartments/*
```

## Scrapers

`backend/app/services/scrapers/`:

| Source key | Class | Actor / Endpoint | Status |
|------------|-------|------------------|--------|
| `apartments_com` | `ApifyService` | `epctex~apartments-scraper-api` | **Active — only one currently scheduled** |
| `zillow` | `ApifyService` | `maxcopell~zillow-scraper` | Configured, off schedule |
| `realtor` | `ApifyService` | `epctex~realtor-scraper` | Configured, off schedule |
| `rent_com` | `ApifyService` | `jupri~rent-com-scraper` | Configured, off schedule |
| `craigslist` | `ScrapingBeeService` | direct HTML scrape | Legacy, not scheduled |

`base_scraper.py` defines `ScrapedListing` (dataclass): `external_id`, `source`, `source_url`, `address`, `city`, `state`, `zip_code`, `latitude`, `longitude`, `rent`, `bedrooms`, `bathrooms`, `sqft`, `property_type`, `available_date`, `description`, `amenities`, `images`, plus optional fee fields (`utilities_included`, `parking_fee`, `pet_rent`, `pet_deposit`, `app_fee`, etc.).

## City Coverage

See `docs/scraping-frequency.md` for the canonical live config (it's updated on every market change). Snapshot:

| Tier | Frequency | Cities | Scrapes/day |
|------|-----------|--------|-------------|
| Hot | 12h | NYC, Boston, DC, Philadelphia | 8 |
| Standard | 24h | Pittsburgh, Baltimore, Newark, Jersey City, Cambridge, Arlington | 6 |
| Cool | 48h | Bryn Mawr, Charleston, New Orleans, Towson, State College | 2.5 |
| **Total** | | **15 active** | **~16.5/day, ~1,650 listings/day** |

8 cool-tier markets are currently disabled (Hoboken, Stamford, New Haven, Providence, Richmond, Charlotte, Raleigh, Hartford) to conserve Apify credits.

## Celery Beat Schedule

`celery_app.py`:

| Task | Schedule | Purpose |
|------|----------|---------|
| `dispatch_scrapes` | hourly :00 | Read `market_configs`, spawn scrape tasks for due markets |
| `decay_and_verify` | hourly :30 | Recalculate freshness confidence, trigger HTTP verification (no Apify credit cost) |
| `cleanup_maintenance` | daily 3 AM | Deactivate dead listings, reset circuit breakers, fail stale jobs |
| `send_daily_alerts` | daily 13:00 UTC | Email Pro users with new matching listings |
| `check_tour_reminders` | every 10 min | Fire 30-min post-tour reminders |

## Normalization

`services/normalization/normalizer.py` — 11-step pipeline per listing:

1. Validate required fields (address, rent, beds, baths) — drop if missing.
2. Standardize address via `AddressStandardizer` (USPS-style canonicalization).
3. Parse city/state/zip from the address.
4. Normalize `property_type` against the `PROPERTY_TYPES` dict (Apartment, Condo, Townhouse, House, Studio).
5. Coerce numeric fields (rent, beds, baths, sqft).
6. Pick `available_date` — earliest **upcoming** date (recent fix `57e9e41`).
7. Detect utilities-included from description text (recent fix `9e87090`).
8. Run `pricing_model_detector` to set `pricing_model`.
9. Compute SHA256 `content_hash`.
10. Compute `data_quality_score` (0–100): 40 required + 40 optional + 20 bonuses.
11. Emit normalized record for dedup.

## Deduplication

`services/deduplication/deduplicator.py` — two-phase:

1. **Content hash match**: SHA256 of `(normalized_address + rent_rounded_to_$50 + beds + baths)`.
2. **Fuzzy match** if no hash hit: address similarity > 0.9 AND rent within 10% AND same bedrooms.

On duplicate: keep the higher-quality record, merge unique data (extra images, missing amenities, longer description). `deduplicate_batch_with_updates` returns buckets: `new`, `seen_again` (just bumps `last_seen_at`), `duplicate_merge`.

## True Cost Calculation

`services/cost_estimator.py` + `data/cost_estimates.json`. Each listing's `true_cost_monthly` blends:

- **Scraped** values (when present): `rent`, `parking_fee`, `pet_rent`, `pet_deposit`, `application_fee`, `utilities_included` flag.
- **Estimated** values from `cost_estimates.json`, looked up by **zip-code prefix** (e.g. `191` Philly, `152` Pittsburgh, `021` Boston, `100` NYC, `190` Wilmington-area). Estimates cover utilities (electric, gas, water, internet) by region + property-type.
- Pet rent and parking fee are **opt-in** — only included if the user toggles those in the UI (recent fix `7d0b26d`).

Two task entry points:

- `recompute_true_costs` — single-listing recompute.
- `backfill_fees_task` — batched (100 per batch, recent fix `29c7157`) re-extraction of fee data across all listings; runs as Celery task to avoid gateway timeout (`7041603`).

JSON-mode reads (no DB) call `_add_cost_breakdown()` in `routers/apartments.py` to produce the breakdown on the fly.

## Per-Person Pricing

`services/pricing_model_detector.py` detects "per bed" rentals (common in college towns). Signals: rent value relative to typical per-unit pricing for the market, description keywords ("per bed", "per person", "individual lease"), unit/property-type heuristics. Sets `pricing_model = 'per_bed' | 'per_unit'`. Search uses an occupancy calculator to display per-unit and per-person rent side-by-side.

## ScrapedListing → ApartmentModel

`tasks/scrape_tasks.py::_save_listings` maps each normalized record onto `ApartmentModel` and inserts. Indexed columns on `apartments`: `city`, `rent`, `bedrooms`, `bathrooms`, `property_type`, `source`, `content_hash`, `is_active`, plus composite `(city, rent, bedrooms)`.

`_update_reseen_listings` bumps `last_seen_at` on listings in the `seen_again` bucket without rewriting the row.

## Listings Lifecycle

| State | Trigger |
|-------|---------|
| `is_active = 1`, fresh `last_seen_at` | Seen in latest scrape |
| Decaying confidence | `decay_and_verify` runs HTTP HEAD checks; failures lower freshness score |
| `is_active = 0` | `cleanup_maintenance` deactivates rows not seen for N days |

## Common Issues

| Issue | Cause / Fix |
|-------|-------------|
| Apify credit exhaustion | 8 cool markets disabled; reduce frequency in `market_configs` via admin API |
| OOM kill on backfill | Mitigated by 100-row batching (`29c7157`) |
| RDS connection pool exhausted | Pool size reduced (`d17fe8d`) — don't open extra sessions per task |
| `Event loop is closed` in Celery | Restart the worker; async clients get bound to a closed loop on fork |
| Stuck scrape job | `cleanup_maintenance` fails it after N hours; check `scrape_jobs` table for stuck rows |
| Circuit breaker tripped | A market with 3 consecutive failures is paused; `cleanup_maintenance` resets daily, or reset manually via admin API |
| Stale `available_date` | We pick earliest upcoming, not earliest overall — old data may surface if the listing has only past dates (drop manually) |
