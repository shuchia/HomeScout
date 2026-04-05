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

---

# Phase 2: Fee Extraction Fixes (2026-04-04)

## Problem

The fee extraction pipeline has three bugs causing silent data loss. Fees that apartments.com provides are being dropped, making `true_cost_monthly` inaccurate for many listings.

### Bug 1: Nested `fees` list format silently ignored

The epctex Apify actor returns `fees` as a **list** of nested objects:
```json
"fees": [
  {
    "title": "Pet Policies (Pets Negotiable)",
    "policies": [{
      "header": "Dogs Allowed",
      "values": [{"key": "Monthly Pet Rent", "value": "$35"}]
    }]
  },
  {
    "title": "Details",
    "policies": [{
      "header": "Utilities Included",
      "values": [{"key": "Water", "value": ""}, {"key": "Trash Removal", "value": ""}]
    }]
  }
]
```

But line 518-520 of `apify_service.py` does:
```python
fees_data = raw.get("fees", {})
if not isinstance(fees_data, dict):
    fees_data = {}
```
A list fails the `isinstance(dict)` check, gets reset to `{}`, and all nested fee data is lost. Only flat `monthlyFees`/`oneTimeFees` arrays at the top level (from alternative actors) are parsed.

### Bug 2: Common monthly fees have no matching pattern

These apartments.com fees are silently dropped:

| Fee | Typical Amount | Why Dropped |
|-----|---------------|-------------|
| Utility billing admin fee | ~$6/mo | No "utility" or "billing" pattern |
| Mandatory renters insurance | $14-20/mo | No "insurance" pattern; conflicts with `est_renters_insurance` |
| Pest control | $1-12/mo | No "pest" pattern |
| Sewer fee | $10-30/mo | No "sewer" pattern |
| Cable/Internet (when charged) | $30-70/mo | No pattern; conflicts with `est_internet` |

Current patterns only match: pet/dog/cat, parking, amenity/community/trash, application/admin, deposit/security.

### Bug 3: Unmatched fees silently vanish

Any fee that doesn't match the 5 hardcoded categories is discarded with no logging and no catch-all field. There's no way to know data is being lost.

## Fix 1: Parse Nested Fees List Format

Add `_extract_fees_from_nested_list()` method to `ApifyService` that walks the `[{title, policies: [{header, values: [{key, value}]}]}]` structure and flattens it into the `[{name, amount}]` format the existing fee matching loop expects.

Update the fee extraction block to try both formats:

```python
fees_raw = raw.get("fees")
if isinstance(fees_raw, dict):
    # Flat dict format: {monthly: [...], oneTime: [...]}
    monthly_fees = fees_raw.get("monthly", [])
    one_time_fees = fees_raw.get("oneTime", [])
elif isinstance(fees_raw, list) and fees_raw:
    # Nested list format from epctex actor
    monthly_fees, one_time_fees, included_utilities = self._extract_fees_from_nested_list(fees_raw)
```

The nested parser also detects "Utilities Included" sections and injects them into the amenities list (e.g., `"Water Included"`) so the `CostEstimator` can zero out those estimates.

**Classification heuristics for nested fees:**
- Pet section → monthly if key contains "rent"/"monthly", one-time if "deposit"/"fee"
- Parking section → always monthly
- Keys with "deposit", "application", "admin", "one time" → one-time
- Default: fees < $200 → monthly, >= $200 → one-time

**Files changed:** `apify_service.py`
**Tests:** `test_apify_type_safety.py` (4 new tests for nested format)

## Fix 2: Add `other_monthly_fees` Catch-All

New field across the entire stack to capture fees that don't match pet/parking/amenity categories.

### Schema Changes

**ScrapedListing** (`base_scraper.py`):
```python
other_monthly_fees: Optional[int] = None  # Catch-all for unmatched monthly fees
```

**ApartmentModel** (`models/apartment.py`):
```python
other_monthly_fees = Column(Integer, nullable=True)
```

**CostBreakdown** (`schemas.py`):
```python
other_monthly_fees: int = 0
```

**CostEstimator** (`cost_estimator.py`):
- Accept `other_monthly_fees` in `scraped_fees` dict
- Include in `monthly_extras` sum → `true_cost_monthly`
- Track in `sources.scraped` when non-zero

**Frontend** (`types/apartment.ts`, `CostBreakdownPanel.tsx`):
- Add `other_monthly_fees: number` to `CostBreakdown` interface
- Render as "Other Fees" line item when > 0, with scraped indicator

### API Response Change

```json
{
  "cost_breakdown": {
    "base_rent": 1800,
    "pet_rent": 50,
    "parking_fee": 150,
    "amenity_fee": 40,
    "other_monthly_fees": 27,
    "est_electric": 95,
    ...
  }
}
```

**DB migration:** `ALTER TABLE apartments ADD COLUMN other_monthly_fees INTEGER;`

## Fix 3: Widen Fee Matching Patterns

Expand the monthly fee matching in `apify_service.py`:

| Pattern | Fee Type | Destination |
|---------|----------|-------------|
| `"pet"`, `"dog"`, `"cat"` | Pet rent | `pet_rent` (unchanged) |
| `"parking"`, `"garage"` | Parking | `parking_fee` (add garage) |
| `"amenity"`, `"community"`, `"trash"`, `"valet"` | Amenity | `amenity_fee` (add valet) |
| `"insurance"` | Mandatory insurance | `amenity_fee` (see Fix 4) |
| Everything else | Misc | `other_monthly_fees` (catch-all) |

All unmatched fees log at DEBUG level: `"Unmatched monthly fee: '{name}' = ${amount}"`.

## Fix 4: Resolve Estimated vs Scraped Conflicts

Two conflict scenarios where scraped data should override estimates:

### Mandatory Renters Insurance
When a property charges mandatory insurance (matched by `"insurance"` in monthly fees), it goes into `amenity_fee`. The `CostEstimator` should then zero out `est_renters_insurance` to avoid double-counting.

**Detection:** New amenity constant in `cost_estimator.py`:
```python
_INSURANCE_REQUIRED = {"renters insurance required", "renters insurance program", "insurance required"}
```
When the scraper finds a mandatory insurance fee, it also injects `"Renters Insurance Required"` into amenities. The estimator sees this and zeros the estimate.

### Internet/WiFi Included
Student housing commonly bundles WiFi. New detection:
```python
_INTERNET_INCLUDED = {"internet included", "wifi included", "wi-fi included", "high-speed internet included"}
```
When matched, `est_internet` is zeroed. The nested fees parser also detects internet in "Utilities Included" sections and injects the amenity string.

## Testing Plan

### New Tests for Bug 1 (nested format)
- `test_fees_as_nested_list_extracts_application_fee` — one-time fee extraction
- `test_fees_as_nested_list_extracts_monthly_fees` — pet rent + parking from nested
- `test_fees_as_nested_list_extracts_deposit` — security deposit from nested
- `test_fees_nested_list_with_included_utilities` — utilities added to amenities

### New Tests for Bug 2 (catch-all)
- `test_other_monthly_fees_included_in_total` — accumulates in true_cost_monthly
- `test_other_monthly_fees_in_sources` — appears in scraped sources
- `test_other_monthly_fees_defaults_to_zero` — absent = 0

### New Tests for Bug 3 (wider patterns)
- `test_utility_admin_fee_captured` — goes to other_monthly_fees
- `test_pest_control_fee_captured` — goes to other_monthly_fees
- `test_sewer_fee_captured` — goes to other_monthly_fees
- `test_mandatory_insurance_overrides_estimate` — goes to amenity_fee
- `test_multiple_unmatched_fees_accumulate` — sum into other_monthly_fees

### New Tests for Bug 4 (conflicts)
- `test_scraped_insurance_zeroes_estimate` — est_renters_insurance = 0
- `test_internet_included_zeroes_estimate` — est_internet = 0

### Existing Tests
All 11 existing `test_cost_estimator.py` tests and 31 `test_apify_type_safety.py` tests must continue to pass.

## Post-Deploy

Run `recompute_true_costs` Celery task to recalculate all existing listings with the new logic. Trigger a fresh scrape for at least one market to verify nested fees are now being captured.

---

# Phase 3: Per-Person Pricing & Occupancy Calculator (Future)

## Problem

Student housing and co-living properties advertise rent **per person** (per bed/per room), not per unit. Examples:
- One on Centre (Pittsburgh): 3BR/3BA at **$1,030/person** (unit total: $3,090)
- Individual leases — each tenant signs independently

The current system stores a single `rent` integer with no concept of pricing model. A 3BR at "$1,030" looks like a steal compared to a traditional 1BR at "$1,500" — but the real comparison is $1,030/person vs $1,500/person.

Users (students, parents, groups) need to answer: **"What will I actually pay per month?"**

## Solution: Occupancy Input on Cost Breakdown

Add a "How many people?" input to the `CostBreakdownPanel`. For any listing, the user can divide shared costs by occupant count to see their per-person share.

### How It Works

**Per-person listings** (auto-detected):
- Badge on card: "Per Person Pricing"
- Default occupancy = bedroom count
- True cost shows per-person by default
- User can adjust occupancy count

**Traditional listings** (default):
- No badge, no auto-splitting
- User can optionally set occupancy to split costs
- Shared costs (rent, utilities) divided; personal costs (pet rent) not divided

### Cost Splitting Logic

```
Per-person costs (NOT divided):
  - pet_rent (your pet, your cost)

Shared costs (divided by occupancy):
  - base_rent (for traditional listings only — per-person listings already per-person)
  - est_electric, est_gas, est_water
  - amenity_fee, other_monthly_fees
  - est_laundry (building laundry is per-person anyway — keep as-is)

Fixed costs (NOT divided):
  - est_internet (one connection per unit, but everyone uses it)
  - est_renters_insurance (per-person policy)
  - parking_fee (per-space, not per-person)
```

### Per-Person Detection Heuristics

Signals to detect per-person pricing from scraped data:

| Signal | Source | Confidence |
|--------|--------|------------|
| "individual lease" in description | Apify description field | High |
| "/person", "/bed", "/room" in rent label | Apify models[].rentLabel | High |
| bedrooms == bathrooms (2/2, 3/3, 4/4) | Listing data | Medium (common in student housing) |
| "student" in property name or description | Apify fields | Medium |
| Rent < $800 for multi-BR in expensive city | Heuristic | Low (supporting signal only) |

Store detection result in new fields:

```python
# ApartmentModel
pricing_model: String  # "per_unit" (default) or "per_person"
pricing_model_confidence: Float  # 0.0-1.0
```

### Data Model Changes

**ApartmentModel** (new columns):
```python
pricing_model = Column(String(20), default="per_unit")  # "per_unit" or "per_person"
pricing_model_confidence = Column(Float, nullable=True)
```

**ScrapedListing** (new fields):
```python
pricing_model: Optional[str] = None
```

**Frontend types** (new fields):
```typescript
pricing_model?: 'per_unit' | 'per_person' | null;
```

### UI Changes

**ApartmentCard:**
- Per-person badge: `"Per Person"` in blue, next to rent
- Rent display: `"$1,030/person"` instead of `"$1,030/mo"` when per-person

**CostBreakdownPanel (Pro):**
- New occupancy input (1-6 stepper) at top of panel
- Default: 1 for per-unit, bedrooms for per-person
- All shared line items show `/person` suffix when occupancy > 1
- Total recalculates client-side based on occupancy

**Compare Page:**
- Per-person badge on per-person listings
- Occupancy input per listing for fair comparison
- "Normalize" toggle to view all listings at same occupancy

### Claude AI Changes

- `prepare_apartment_for_scoring()` includes `pricing_model` field
- System prompt updated: "When `pricing_model` is 'per_person', the rent shown is per-occupant, not per-unit. For budget comparison, compare the per-person cost against the user's budget. Highlight when a seemingly cheap multi-BR listing is actually per-person pricing."
- Comparison prompt: "When comparing per-person and per-unit listings, normalize to per-person cost for fair comparison."

### Scraper Changes

In `_normalize_apartments_com_listing()`:
1. Check `models[].rentLabel` for "/person", "/bed", "/room"
2. Check description for "individual lease", "per person", "by the bed"
3. Check bedrooms == bathrooms pattern
4. Set `pricing_model` and confidence based on signals

### Edge Cases

- **Mixed unit types**: A property may have both per-person and per-unit floor plans. Use the dominant pricing model for the property.
- **Unknown pricing model**: Default to `per_unit` — conservative, doesn't mislead.
- **Occupancy > bedrooms**: Allow it (couples sharing rooms) but show warning.
- **Studio per-person**: Shouldn't happen, but if detected, ignore and default to per-unit.
- **Utilities for per-person**: Regional estimates are per-unit. When occupancy > 1, divide utility estimates by occupancy count.

### Testing Plan

- Detection: test each heuristic signal individually and in combination
- Splitting: test cost division math for various occupancy counts
- Frontend: E2E tests for occupancy input, per-person badge, cost recalculation
- Claude: verify scoring prompt includes pricing_model context
- Edge cases: studio per-person, occupancy > bedrooms, mixed properties
