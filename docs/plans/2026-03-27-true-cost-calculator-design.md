# True Cost Calculator — Design

## Problem

Advertised rent is never the real price. Renters don't discover the true monthly cost — utilities, parking, pet rent, mandatory fees, insurance — until after they sign. This makes it impossible to accurately compare apartments.

## Solution

Augment every listing with a precomputed "true cost" estimate that includes base rent + all known and estimated monthly costs. Show the headline number to all users; gate the detailed breakdown to Pro.

## Data Source Strategy

- **Scraped data (Apify)**: Extract structured fee fields from apartments.com listings that we currently discard (pet rent, parking fees, amenity fees, application fees, security deposits).
- **Static estimation (lookup tables)**: Fill gaps with regional averages by zip code prefix + bedroom count, sourced from EIA/BLS public data. Fallback chain: zip prefix → state → national.

## Data Model

### New DB Columns on `ApartmentModel`

```
# Scraped fee fields (nullable, from Apify)
pet_rent: Integer              # monthly, e.g. $50/pet
parking_fee: Integer           # monthly
amenity_fee: Integer           # mandatory monthly community/amenity fee
application_fee: Integer       # one-time
security_deposit: Integer      # one-time

# Estimation fields (computed at ingestion)
est_electric: Integer          # monthly, null if included
est_gas: Integer               # monthly, null if included
est_water: Integer             # monthly, null if included
est_internet: Integer          # monthly
est_renters_insurance: Integer # monthly
est_laundry: Integer           # monthly, null if in-unit W/D

# Flags (derived from amenities during normalization)
utilities_included: JSONB      # e.g. {"heat": true, "water": true, "electric": false}

# Precomputed totals
true_cost_monthly: Integer     # rent + all monthly costs
true_cost_move_in: Integer     # application + deposit + first month true cost
```

### Frontend `Apartment` Type

Matching fields plus a `cost_breakdown` object for the detail view.

### Static Lookup Tables

New `backend/app/data/cost_estimates.json` keyed by zip code prefix (first 3 digits) + bedroom count, with regional averages. Fallback to state-level if zip not found, then national.

## Ingestion Pipeline

### Apify Normalizer Changes

Update `_normalize_apartments_com_listing()` to extract fee fields currently being discarded: pet rent, parking fees, mandatory amenity fees, application fees, security deposits.

### New Cost Estimator Service

`backend/app/services/cost_estimator.py`:
- Takes zip code, bedroom count, sqft, and `utilities_included` flags
- Looks up regional averages from `cost_estimates.json`
- Zeroes out any utility flagged as included
- Checks amenities for "In-Unit Washer/Dryer" — if present, `est_laundry = 0`
- Returns all estimate fields

### Integration Point

Called at the end of normalization, after amenities are parsed but before DB insert:
1. Parse amenities → `utilities_included` flags
2. Call cost estimator → fill estimate fields
3. Sum everything → `true_cost_monthly` and `true_cost_move_in`

### Recompute Task

New Celery task `recompute_true_costs` — triggered manually or scheduled when lookup tables update. Iterates all active listings and recalculates estimates.

### DB Migration

Alembic migration adding new columns, with backfill step running the estimator on existing listings.

## API Changes

No new endpoints. True cost data rides on existing responses.

### Response Shape (added to apartment schema)

```json
{
  "rent": 1800,
  "true_cost_monthly": 2340,
  "true_cost_move_in": 4690,
  "cost_breakdown": {
    "base_rent": 1800,
    "pet_rent": 50,
    "parking_fee": 150,
    "amenity_fee": 40,
    "est_electric": 95,
    "est_gas": 45,
    "est_water": 0,
    "est_internet": 60,
    "est_renters_insurance": 25,
    "est_laundry": 75,
    "application_fee": 50,
    "security_deposit": 1800,
    "sources": {
      "scraped": ["pet_rent", "parking_fee", "amenity_fee"],
      "estimated": ["est_electric", "est_gas", "est_internet", "est_renters_insurance", "est_laundry"],
      "included": ["water"]
    }
  }
}
```

### Tier Gating

- **Free/Anonymous**: `true_cost_monthly` and `true_cost_move_in` included. `cost_breakdown` is null.
- **Pro**: Full `cost_breakdown` object included.

### Claude AI Integration

`score_apartments()` and `compare_apartments_with_analysis()` prompts updated to include `true_cost_monthly` and `cost_breakdown` in apartment data, so Claude reasons about real costs in scoring and comparison.

## Frontend UI

### ApartmentCard

- Below rent: `Est. True Cost: $2,340/mo` in muted style
- Delta line: `+$540/mo in fees & utilities`
- Hidden if true cost equals rent (no extra costs)
- Free users: clicking delta → `UpgradePrompt` (inline mode)
- Pro users: clicking expands breakdown panel

### Breakdown Panel (Pro Only)

```
Base Rent                    $1,800
Pet Rent                        $50  ● scraped
Parking                        $150  ● scraped
Amenity Fee                     $40  ● scraped
Electric                        $95  ○ estimated
Gas                             $45  ○ estimated
Internet                        $60  ○ estimated
Renter's Insurance              $25  ○ estimated
Laundry                         $75  ○ estimated
Water                        Included
─────────────────────────────────
Est. Monthly Total           $2,340

Move-in Costs
Application Fee                 $50  ● scraped
Security Deposit             $1,800  ● scraped
First Month                  $2,340
─────────────────────────────────
Est. Move-in Total           $4,190
```

Dot indicators: `●` scraped (from listing) vs `○` estimated (regional avg) for transparency.

### Compare Page

Comparison table gets a "True Cost" row alongside rent for immediate side-by-side real cost comparison.

## Edge Cases

- **Missing zip code in lookup table**: Fall back to state-level averages, then national averages
- **No scraped fees found**: Fee fields null, true cost = rent + estimates only
- **All utilities included**: Estimate fields zeroed, true cost closer to rent
- **No amenities data at all**: Assume nothing included, estimate everything (conservative/higher)
- **"Est." prefix**: Shown everywhere to set expectations on accuracy

## Testing

- **Backend unit tests** for `cost_estimator.py`: various zip codes, bedroom counts, included utility combos
- **Tier gating tests**: free gets null `cost_breakdown`, Pro gets full object
- **Normalization tests**: verify fee extraction from Apify raw data
- **Recompute task tests**: verify existing listings get updated
- **Frontend E2E tests**: card display, breakdown expand (Pro), upgrade prompt (free)
- **Fallback chain tests**: zip → state → national

## Data Maintenance

- `cost_estimates.json` updated quarterly from EIA/BLS public data
- `recompute_true_costs` task triggered after table updates
- No user-facing staleness concern since estimates are regional averages
