# Floorplan-Aware Search — Design

*2026-07-15 · status: design approved (D1–D4 decided) · Phase 1–2 implemented, validated on QA*

## Implementation status

- **Phase 1** (schema, `ApartmentFloorplanModel`, `build_floorplan_buckets`, `backfill_floorplans`): done.
- **Phase 2** (`USE_FLOORPLAN_SEARCH`-gated join in `_search_database`, projection, D1/D3): done.
- **Phase 3** (scoring on the matched floorplan): done. Heuristic drops the budget term and
  renormalizes for price-on-request (null rent) instead of scoring a fabricated fallback; and
  the Claude AI path (`score_batch` → `get_apartments_by_ids`) now projects each building onto
  its matching floorplan bucket when the flag is on, so the AI scores the searched unit, not the
  collapsed studio. Building-level dedup: IDs reaching `score_batch` are already deduped by
  search, so DISTINCT ON id suffices there.
- **QA validation (2026-07-21):** migration applied; backfill built **4,088 buckets across
  1,792 buildings**. Boston 3BR ≤ $4,800 search returned **20 results (was 0)** via the join,
  with price-on-request (D1) and matched-floorplan projection confirmed on real data.

### Finding: duplicate building rows — FIXED

**Resolution (2026-07-21):** the join now keys `DISTINCT ON` on
`COALESCE(address_normalized, address, id)` instead of `apartments.id`, keeping the cheapest
matching bucket per *physical building*. Re-validated on QA: Boston 3BR ≤ $4,800 collapsed
**20 → 11 rows, 11 distinct addresses, zero duplicate addresses**; `24 Oyster Bay Rd` (6 rows)
now appears once at its cheapest 3BR ($4,156). Original finding below for context.

---


QA validation, Boston 3BR ≤ $4,800: **20 result rows = 20 distinct `apartments.id`, but only
11 distinct addresses.** Three addresses carry duplicate building rows: `24 Oyster Bay Rd` ×6,
`3200 Washington St` ×4, `43 Smith St` ×2. `DISTINCT ON (apartments.id)` is working exactly as
designed (20 distinct ids → 20 rows); the *data* holds multiple building rows per physical
address (scraper/dedup produced them), so "one card per building" does not fully hold — ~45% of
these rows are dupes.

This is **pre-existing** (building-level search would also duplicate these once matched) and is
surfaced more because floorplan search matches more inventory. Options for a later phase:
collapse by `address_normalized` (or content-hash) in the query/projection, or a dedup pass
upstream. Tracked as a follow-up; does not block the Phase 2 flag rollout, but should be fixed
before the flag is turned on for users (duplicate cards are visible).

## Problem

The apartments.com scraper stores **one `ApartmentModel` row per building**, with a single
`bedrooms` value parsed from the building's bedroom **range** string
(`_parse_bedrooms` in `base_scraper.py:266`): `"Studio - 3 bd"` → `0`,
`"1 bd - 3 bd"` → `1`, `"2 bd - 4 bd"` → `2`. It always keeps the **low end**, so every
larger floorplan is invisible to the exact-match search filter `bedrooms == N`.

Validated against the raw Apify payload (Boston run `zvpMrxcRyJrcJPbmm`):

- 100 buildings → **1,958 floorplans** in the `models` arrays.
- Bedroom mix in the raw data: Studio 408, 1BR 756, 2BR 655, **3BR 121, 4BR 18**.
- The search returns **0** 3BR in Boston. E.g. *Peninsula Apartments* (stored as a studio)
  actually has `3 Beds / 2 Baths · $4,624–4,952 · 3 available` — a match for the tester's
  $4,800 / 3BR search that never surfaces.

This is systemic (thin 3BR in every city), and distinct from the NYC borough bug
(that was city-value normalization; this is floorplan collapse).

## Goal & the core tension

Two requirements pull in opposite directions:

1. **Search must be floorplan-granular** — a 3BR search must match a building that has a 3BR
   floorplan, priced/scored on *that* floorplan.
2. **Results must stay one card per building** — Peninsula has ~20 floorplans / 5–7
   available bed-bath buckets; expanding each into its own search result would flood the page
   and return the same building many times.

So: **expand for matching, collapse for display.**

## Key existing assets (why this is cheaper than it looks)

- `ApartmentModel.floor_plans` (JSONB, `apartment.py:101`) **already persists the full `models`
  array per building**, and `available_units` persists `rentals`. → We can restructure and
  **backfill from existing rows without re-scraping**.
- One-row-per-building identity is load-bearing: favorites, tours, and the availability-date
  design (`docs/archive/plans/2026-03-30-availability-date-extraction-design.md`) all key off
  the building row. The design must **preserve building identity**.

## Raw `models` shape (confirmed)

```jsonc
{
  "modelId": "c4071je",
  "modelName": "Current",
  "details": ["3 Beds", "2 Baths"],      // [beds, baths] — always well-formed in sample
  "totalPrice": "$4,624 - 4,952",         // range | single | "Call for Rent"
  "basePrice":  "$4,624 - 7,341",
  "squareFeet": "1,444",                   // single | range
  "availability": "3 Available units",     // "0 Available units" = none
  "availabilityInfo": "Now"
}
// rentals[] link per-unit availableDate by modelId (existing availability logic)
```

Data reality (Boston, 1,958 floorplans): **751 available**, 1,207 zero-available,
**~1,000 "Call for Rent"** (no price), 0 with malformed `details`.

## Design options

### A. One `ApartmentModel` row per floorplan (rejected)

Expand at ingestion into N building×floorplan rows. Search filters "just work."
**Rejected:** row explosion, dedup churn, and it breaks building identity — favorites/tours
would point at a floorplan row, and display would need to re-group anyway. Moves the collapse
problem downstream without solving it.

### B. Denormalize floorplan buckets onto the building (lighter)

Add a JSONB `floorplan_buckets` (and/or `bedroom_options int[]`) column on `apartments`,
computed at ingestion. Search with an `EXISTS (jsonb_array_elements … )` predicate.

- **Pros:** no new table; smallest migration; building identity untouched.
- **Cons:** nested JSONB predicates don't use btree indexes well; correct budget filtering
  ("3BR *of this building* ≤ $4,800", not the studio price) means unpacking JSONB per row.
  Fine at current scale (~thousands of rows), weaker long-term.

### C. Child `apartment_floorplans` table (DECIDED)

One building row (unchanged) + a child table of **aggregated floorplan buckets**, one per
`(bedrooms, bathrooms)` among *available, priced* floorplans.

```
apartment_floorplans
  id                       uuid pk
  apartment_id             fk → apartments.id (cascade delete)
  bedrooms                 int         # 0 = studio
  bathrooms                numeric     # min bath in this bucket (see edge cases)
  min_rent                 int  null   # cheapest available unit in bucket
  max_rent                 int  null
  min_sqft                 int  null
  max_sqft                 int  null
  available_units          int         # summed across matching models
  earliest_available_date  date null   # from rentals, upcoming-min
  model_ids                jsonb       # provenance
  UNIQUE (apartment_id, bedrooms, bathrooms)
  INDEX (bedrooms, min_rent)
  INDEX (apartment_id)
```

- **Pros:** clean indexed joins; correct per-bedroom budget filtering; building identity and
  all downstream features untouched; naturally extensible (later: bed+ ranges, per-unit rows).
- **Cons:** a migration + a child model + join query + backfill job.

**Decision: C** (child table). B (denormalized JSONB) is recorded only as the rejected
lighter-weight alternative.

## Aggregation granularity

Aggregate per **`(bedrooms, bathrooms)` bucket** over *available* (`availability` not
`"0 …"`) floorplans — **including "Call for Rent"** (see decision D1: price-on-request).
This collapses ~20 raw floorplans → ~5–7 buckets/building — precise enough that the
`bathrooms >= N` filter stays correct, without row explosion. (Per-bedrooms-only would be
lighter but loses bath precision; per-raw-floorplan would explode. `(beds, baths)` is the
sweet spot.)

Per bucket: `min_rent`/`max_rent` = min/max of parsed `totalPrice` (fallback `basePrice`)
**over the priced units only — `NULL` when every unit in the bucket is "Call for Rent"**;
`min/max_sqft` from `squareFeet`; `available_units` = Σ; `earliest_available_date` from
`rentals` matched by `modelId` (reuse existing logic). A bucket materializes as long as it has
`available_units > 0`, priced or not.

## Search query & result projection

Replace the building-level `bedrooms == N` / `rent <= budget*1.1` predicates
(`apartment_service._search_database`, `apartment_service.py:99-113`) with a join:

```sql
SELECT DISTINCT ON (a.id) a.*, fp.*    -- one row per building, cheapest matching bucket
FROM apartments a
JOIN apartment_floorplans fp ON fp.apartment_id = a.id
WHERE a.is_active = 1 AND a.freshness_confidence >= 40
  AND (a.city ILIKE :city OR a.address ILIKE :city_like)
  AND a.property_type IN (:types)
  AND (fp.bedrooms = :bedrooms          -- exact mode …
       OR (:mode = 'plus' AND fp.bedrooms >= :bedrooms))   -- … or "N+" mode (decision D3)
  AND fp.bathrooms >= :bathrooms         -- at-least (unchanged semantics)
  AND fp.available_units > 0
  AND (fp.min_rent <= :budget * 1.10     -- budget against the MATCHED floorplan …
       OR fp.min_rent IS NULL)           -- … but keep "price on request" (decision D1)
ORDER BY a.id,
         (fp.min_rent IS NULL),          -- priced buckets ahead of price-on-request
         fp.bedrooms,                     -- in "N+" mode, prefer the smallest qualifying size
         fp.min_rent                      -- then cheapest
```

**Decision D1 — price-on-request:** budget predicate is
`min_rent <= budget*1.1 OR min_rent IS NULL`. A "Call for Rent" bucket with availability can't
be ruled out on price, so it stays in results, flagged, and sorted after priced matches.

**Decision D3 — bedroom mode + near-miss:** the bedroom control offers "N+" (`:mode='plus'`,
default for 3+). If the primary query returns **0 buildings**, run a **near-miss fallback**:
re-query for the nearest bedroom sizes (`bedrooms IN (N-1, N+1)`, widening until non-empty or
bounds), same city/budget/bath filters, and return them tagged so the UI can label them
"No exact 3BR — showing nearby options." Response carries
`match_type: "exact" | "plus" | "near_miss"`.

**Projection (critical):** the returned card and everything downstream must reflect the
**matched floorplan**, not the building's collapsed studio. Override `rent`, `bedrooms`,
`bathrooms`, `sqft` with the matched bucket's values, and attach:

- `matched_floorplan`: `{bedrooms, bathrooms, min_rent, max_rent, sqft_range, available_units, earliest_date, price_on_request: bool}`
- `floorplan_summary`: all bedroom options for the building (for the card, e.g. "Studio–3BR").

**Scoring** (heuristic + Claude) currently reads `rent`/`bedrooms`/`sqft` — it must score on the
matched floorplan, or a 3BR result gets scored on the studio's $2,150. Feed projected values in;
for price-on-request (null rent), the heuristic drops its budget-fit term rather than assuming
$0 or over-budget.

## Display / UX (one card per building)

- **Bedroom-filtered search:** headline = matched floorplan — "3 BR · 2 BA · from $4,624 ·
  1,444 sqft", plus a subtle "Also: Studio, 1, 2 BR" from `floorplan_summary`, and the existing
  "View units" deep link.
- **Price-on-request match** (D1): headline "3 BR · Price on request" with a "Contact for
  pricing" affordance instead of a rent figure; sorted below priced matches.
- **Near-miss results** (D3): rendered in a labeled section — "No exact 3-bedroom listings in
  Boston. Nearby options:" — each card badged with its actual size (2 BR / 4 BR) so the swap is
  never silent.
- **Browse / no bedroom filter** (`/api/apartments/list`): show the building's range —
  "Studio–3BR · from $2,150".
- Building appears **once** even if multiple buckets match (DISTINCT ON building).
- Pagination/sort operate on **buildings**, not floorplans (else dup buildings across pages).

## Persisting the searched bedroom on favorites & tours (decision D2)

Favorites and tours reference the **building**, but the user's intent ("I favorited the *3BR*")
must survive. Add a nullable `searched_bedrooms` column to the Supabase `favorites` and
`tour_pipeline` tables (migration `005`). On create-from-search, the API stores the matched
`bedrooms`; the favorites/tours list then re-projects each item onto that bedroom's bucket
(`apartment_floorplans` lookup by `apartment_id + bedrooms`) so the card shows the 3BR price,
not the studio.

- **Back-compat:** existing rows have `searched_bedrooms = NULL` → fall back to the building
  range (today's behavior).
- **Bucket disappeared** (that bedroom no longer available on re-scrape) → show the stored
  bedroom with "No longer listed / availability changed," never a wrong price.
- Type sync: `favorites`/`tour` payloads in `frontend/types/*` and `backend/app/schemas.py`.

## Backfill / migration

1. Alembic migration: create `apartment_floorplans` (Postgres). Supabase migration `005`:
   `searched_bedrooms int null` on `favorites` and `tour_pipeline` (D2).
2. Backfill job: parse each existing `apartments.floor_plans` JSONB into buckets — **no
   re-scrape needed**. Rows with null/empty `floor_plans` (zillow, craigslist, manual,
   single-unit) get **one implicit bucket** from the building's own `bedrooms`/`rent` so the
   join is uniform (every building has ≥1 bucket).
3. Wire ingestion (`_normalize_apartments_com_listing`) to emit buckets on every scrape;
   idempotent = delete+reinsert child rows keyed by `apartment_id`.
4. Cut the search query over to the join (exact + "N+" mode + near-miss fallback).

Keep `apartments.bedrooms` for back-compat/non-apartments.com sources; search stops relying
on it. Building content-hash/dedup is unchanged (still building-level).

## Edge cases

**Ingestion / parsing**
- **No `models`** (houses, craigslist, manual) → single implicit bucket from building fields.
- **"Call for Rent"** (~51%) → null `min_rent`. **Included** as price-on-request (D1): the
  bucket materializes if it has availability, passes the budget filter via the `min_rent IS NULL`
  branch, and renders "Price on request," sorted after priced matches. (Many are also
  0-available and thus dropped by the availability rule below anyway.)
- **0 available units** → excluded from search matching; may show as "not currently available".
  A building whose 3BR is 0-available but studio is available must **not** match a 3BR search.
- **Bucket with all-null price** counts toward `available_units` but has `min_rent = NULL` →
  price-on-request, never treated as $0.
- **Price ranges** `"$4,624 - 4,952"` → min=4624 (use for budget); keep max for display.
  `basePrice` fallback when `totalPrice` missing.
- **Malformed `details`** (none in sample, but defend): missing baths → bath=null, bucket by
  beds only; unparseable beds → skip floorplan, fall back to building bedroom.
- **Duplicate buckets** (Peninsula has 11× "1 Bed/1 Bath") → aggregated into one bucket
  (min/max rent, Σ available).
- **Studio** `details[0]="Studio"` → beds=0 (matches search studio semantics).

**Search / scoring**
- **Budget buffer** `*1.10` applies to `min_rent` of the matched bucket.
- **Bath precision:** aggregating per `(beds,baths)` keeps `bathrooms >= N` correct; the rare
  inaccuracy (min_rent of a bucket vs a specific higher-bath unit) is acceptable for v1.
- **Freshness/active/city/property_type** stay building-level (unchanged).
- **Scoring/AI** must use projected floorplan values (see Projection); null-rent buckets drop
  the budget-fit term.
- **Multiple matching buckets** (3BR/2BA and 3BR/3BA) → return building once, headline =
  cheapest matching bucket ("from $X").
- **"N+" mode (D3):** `bedrooms >= N`; a building with only a 4BR matches a "3+" search and the
  card shows 4BR. Projection picks the smallest qualifying size, then cheapest.
- **Near-miss fallback (D3):** fires only when the primary query returns **0 buildings**; keeps
  city/budget/bath filters, widens bedrooms to nearest sizes, and tags results `near_miss` so the
  UI labels them. If budget is the true blocker (e.g. all 3BR over budget), near-miss on
  bedrooms may still be empty → then optionally a second tier relaxes budget, clearly labeled
  ("above your budget"). *(second tier is v1.1, note only.)*

**Favorites / tours / compare**
- Favorites & tours reference the **building**; the searched bedroom is persisted via
  `searched_bedrooms` (D2, see section above) so the card re-projects onto the right bucket.
  Null (legacy/no-context) → building range. Bucket gone on re-scrape → stored bedroom +
  "availability changed," never a wrong price.
- Compare operates on buildings; carry the searched floorplan context (each item's
  `searched_bedrooms` / matched bucket) into compare so a 3BR-vs-3BR comparison isn't silently
  scored on studios. *(note; align with D2 projection.)*

**Display / pagination**
- DISTINCT ON building so a building never appears twice.
- Sort/paginate on buildings; matched-floorplan price is the per-building sort key.

**Availability drift**
- Buckets refresh on re-scrape (delete+reinsert). `earliest_available_date` recomputed.

## Rollout / phasing

1. **Migration + model + backfill** (`apartment_floorplans`; read-only; nothing uses it yet).
2. **Switch search to the join** behind a flag; verify Boston 3BR returns Peninsula et al.
   Includes D1 (price-on-request budget branch) and D3 exact/"N+" mode.
3. **Projection + scoring** on matched floorplan (incl. null-rent handling).
4. **Near-miss fallback** (D3) + `match_type` in the response.
5. **Card UX** — matched headline, price-on-request, range/summary, near-miss labeling.
6. **Favorites/tours** — `searched_bedrooms` (D2), create-from-search wiring, list re-projection,
   type sync.
7. Roll ingestion to all sources; re-scrape optional (backfill already covers existing rows).

## Resolved decisions

- **D1 — "Call for Rent" → include as "price on request".** Buckets materialize with
  `min_rent = NULL`; budget filter is `min_rent <= budget*1.1 OR min_rent IS NULL`; UI shows
  "Price on request," sorted after priced matches; scoring drops its budget term for them.
- **D2 — Persist the searched bedroom on favorites & tours.** New `searched_bedrooms` column
  (Supabase migration `005`); list views re-project onto the matched bucket; null → building
  range; missing bucket → "availability changed."
- **D3 — Offer "N+" and near-miss fallback.** Bedroom control supports "3+" (`bedrooms >= N`);
  when the primary query is empty, a labeled near-miss pass returns nearest bedroom sizes
  (`match_type = near_miss`). Never a silent size swap.
- **D4 — Data model: child `apartment_floorplans` table (option C).**
