# Floorplan-Aware Search — Architecture

*2026-07-29 · companion to [`floorplan-search-design.md`](floorplan-search-design.md)
(the design/decision record). This doc explains how the shipped system works end
to end, and how it interlocks with per-person (by-the-bed) pricing.*

## The problem

apartments.com listings are **one row per building**, not per unit. The scraper
stored a single `bedrooms` value parsed from the building's bedroom *range*, and
`_parse_bedrooms` keeps the **low end**: `"Studio - 3 bd"` → `0`. So a building's
3-bedroom floorplan was invisible to an exact `bedrooms == 3` search. A beta
tester searched "Boston, 3BR, $4,800" and got **zero results** — while 121 real
3BR floorplans existed in Boston, hidden inside buildings stored as studios.

## The core idea

Two requirements pull opposite ways:

- **Search must be floorplan-granular** — a 3BR search must match a building that
  *has* a 3BR floorplan, priced on that floorplan.
- **Results must stay one card per building** — a building has ~20 floorplans;
  expanding each into its own result would flood the page with duplicates.

The whole design is one sentence: **expand floorplans for matching, collapse to
one card for display.**

## Data model

The building row (`apartments`) stays authoritative and unchanged — favorites,
tours, and dedup all key off it. A **child table** holds the searchable
granularity:

```
apartment_floorplans
  apartment_id  → apartments.id (cascade delete)
  bedrooms, bathrooms          -- one bucket per (beds, baths)
  min_rent, max_rent           -- range across available units; NULL = price-on-request
  min_sqft, max_sqft
  available_units              -- summed; a bucket exists only if > 0
  earliest_available_date
  pricing_model                -- "per_unit" | "per_person"  ← the per-person hook
  UNIQUE (apartment_id, bedrooms, bathrooms)
  INDEX (bedrooms, min_rent), INDEX (apartment_id)
```

The building's raw `floor_plans` JSONB (already scraped — the apartments.com
`models` array) is aggregated into these **buckets**: one per distinct
`(bedrooms, bathrooms)` among the *available* floorplans. ~20 raw floorplans
collapse to ~5–7 buckets. This lives in `app/services/floorplans.py`
`build_floorplan_buckets()` — a **pure function** (no DB/network), so it's
unit-tested and reused by both the backfill and live ingestion. No re-scrape is
needed; buckets are derived from data already stored.

## End-to-end flow

```
Ingestion / backfill  (app/tasks/maintenance_tasks.py: backfill_floorplans)
  build_floorplan_buckets(floor_plans, rentals, description, city)
   → per-(beds,baths) buckets, each with pricing_model detected per bucket
   → delete + reinsert into apartment_floorplans (idempotent)

Search  (gated by USE_FLOORPLAN_SEARCH; app/services/apartment_service.py)
  _search_database  →  _search_database_floorplan
   ├─ _floorplan_rows(): JOIN apartments × apartment_floorplans
   │     WHERE  bedrooms match (== N, or >= N for "3+" / bedroom_mode="plus")
   │            AND baths >= N AND available_units > 0
   │            AND (min_rent <= budget*1.10 OR min_rent IS NULL)   -- keep price-on-request
   │     DISTINCT ON (COALESCE(address_normalized, address, id))    -- one card per building
   │            ORDER BY building, priced-first, smallest-beds, cheapest
   └─ _project_floorplan_rows(): project_matched_floorplan() overlays the
            matched bucket onto each building's card dict + tags match_type

  If the primary query is empty → near-miss: widen bedrooms (N±1, N±2, N±3),
  same filters, tag match_type="near_miss".

Scoring  (app/services/scoring_service.py, app/services/claude_service.py)
  heuristic + Claude read the PROJECTED dict → they judge the searched unit
  (e.g. the 3BR), not the collapsed studio.

Response / display
  /api/search returns each card + match_type ("exact"|"plus"|"near_miss"|"none").
  Card: matched headline, price-on-request affordance, per-bed label.
  Results page: near-miss banner when match_type == "near_miss".
```

**Projection is the linchpin.** The search matches a building on one of its
buckets, but the card dict from `to_summary_dict()` still describes the collapsed
studio. `project_matched_floorplan()` overlays the matched bucket's
`rent`/`bedrooms`/`bathrooms`/`sqft` onto a *copy* of that dict — so everything
downstream (heuristic scoring, the Claude prompt via `prepare_apartment_for_scoring`,
the rendered card) reflects the searched unit. That's why the AI reasons about
"3 bed, 3.5 bath" rather than the studio, and why the card headline shows the 3BR
price.

## How per-person (by-the-bed) pricing interlocks

The app already had a **per-person pricing feature**: `detect_pricing_model()`
(regex on the description for "per bed" / "by the bed" / "individual lease" /
"per room", plus a `beds == baths` heuristic common in student housing) tags a
building `per_unit` or `per_person`, feeding the per-person true-cost math and a
"Per Person Pricing" badge.

**Floorplan search exposed a flaw in it and then fixed it.** By-the-bed student
buildings are stored collapsed as *studios* (`bedrooms = 0`), and the detector
short-circuits `bedrooms == 0` → always `per_unit`. So a by-the-bed 3BR
building's *building-level* value came back `per_unit` — wrong — and its 3BR
bucket surfaced `$1,792` (the per-*bedroom* share) as if it were a whole-unit 3BR
bargain.

The fix: run the **same `detect_pricing_model()` per bucket**, using the bucket's
*real* beds/baths + the building description, and store it on
`apartment_floorplans.pricing_model`. A 3BR/3BA bucket in a "leased by the bed"
building is now correctly flagged `per_person`, even though the building says
`per_unit`.

The product decision (recorded as a follow-up in the design doc) was **keep
per-bed matching, but label it**:

- **Matching/scoring stay on the per-bed price.** A student paying $849/bed sees
  it as affordable — which is the point. No normalization to whole-unit for the
  budget filter.
- **The projection exposes the truth for the card:**
  `matched_floorplan.{pricing_model, per_bed_rent, whole_unit_rent}`, where
  `whole_unit_rent = per_bed × bedrooms`. The card renders
  **"$849/bed · ≈ $2,547/unit total · By the bed"** — honest on both numbers.
- **Claude gets the correct per-bucket `pricing_model`** (via the projected
  dict + a `pricing_note`), so its reasoning about by-the-bed pricing is reliable
  rather than inferred from raw description text.

So the relationship is: **floorplan search consumes and corrects the per-person
feature.** Per-person detection was building-level and blind to the
collapsed-bedroom problem; floorplan buckets give it the right granularity, and
the projection carries both the per-bed price and the whole-unit estimate to the
UI and the AI.

## Per-person pricing across cities (QA data, 2026-07-29)

per-person is **rare and student-concentrated**:

| Metric | Value |
|---|---|
| Total buckets | 4,472 (`per_unit` 4,443 · **`per_person` 29** ≈ 0.6%) |
| Live per-person buckets (active + freshness ≥ 40) | **14** |
| — by city | **Philadelphia 12**, **Pittsburgh 2** |
| — price-on-request share | **9 of 14 (~64%)** have no listed rent |
| — by bedrooms | 1BR ×2, 2BR ×5, 3BR ×4, 4BR ×3 |

Observations:

- **Geographic signal is correct.** Every live per-person bucket is in a student
  market — Philadelphia's University City (19104, near Penn/Drexel) and
  Pittsburgh's 15213 (near CMU/Pitt). Boston/NYC/SF/Cambridge, despite large
  student populations, surfaced none in the fresh set (their apartments.com
  inventory skews to conventional whole-unit buildings).
- **By-the-bed buildings are multi-tier.** `101 S 39th St, Philadelphia` is the
  canonical example — the same building offers per-bed pricing that *drops as you
  add roommates*:

  | Floorplan | Per-bed | ≈ Whole-unit |
  |---|---:|---:|
  | 2 BR | $1,149/bed | ~$2,298 |
  | 3 BR | $849/bed | ~$2,547 |
  | 4 BR | $795/bed | ~$3,180 |

  This is exactly the pattern that would have been invisible (all collapsed to a
  studio) and misleading (per-bed shown as whole-unit) before the fix.
- **Most by-the-bed listings are price-on-request** (~64%). Student buildings
  frequently gate pricing behind a contact form, so these cards render "Price on
  request" (decision D1) rather than a per-bed figure — and the heuristic drops
  its budget term for them instead of scoring a fabricated number.

**Implication:** per-person is a low-volume but high-value correctness case —
it's concentrated exactly where students search, and it's where the "cheap 3BR
bargain" illusion was most damaging. The fix matters more than the 0.6% share
suggests, but it's not a broad-market feature; it's a targeted correctness
guarantee for student housing.

## The two flags

- **`USE_FLOORPLAN_SEARCH`** (backend env, Terraform-managed per env) — gates the
  whole search join. Off → the legacy building-level query runs, byte-identical
  to before. On (QA) → floorplan search. Live on QA.
- **`NEXT_PUBLIC_FLOORPLAN_SEARCH`** (frontend, build-time inlined) — gates only
  the **"3+" toggle** UI. The card rendering (price-on-request, per-bed label,
  near-miss banner) is naturally data-gated: it appears only when the API returns
  `matched_floorplan`, which only happens when the backend flag is on. Because
  `NEXT_PUBLIC_*` is inlined at build time, changing it requires a fresh Vercel
  build — and qa.snugd.ai builds from the `release/qa` branch, so it uses Vercel's
  *Preview*-scoped env vars.

## Detection coverage (why some student markets show few per-person)

A follow-up investigation (2026-07-29/30) asked why Boston / NYC / SF / Cambridge
surfaced almost no per-person buckets despite large student populations. The
answer: **it's a detection gap, not a data gap — and it's a precision/recall
tradeoff working mostly as intended.**

`detect_pricing_model()` fires with high confidence only on explicit phrases
("per bed", "by the bed", "individual lease", "per room"). The structural
`beds == baths` heuristic adds only `+0.25` — below the `0.6` threshold on its
own — precisely because in these markets a 2BR/2BA (or 3BR/3BA) is a normal
**whole-unit** luxury layout, not by-the-bed. QA has hundreds of such buckets
(Boston 109× 2/2, Cambridge 118× 2/2, NYC 72× 2/2, SF 85× 2/2) and **none** are
flagged.

**Precision is validated.** Spot-checking Boston/Cambridge 3BR/3BA buildings
(180 Brookline Ave, 260 Huntington Ave, 2 H St, 145 Larch Rd, …) confirmed they
are genuinely conventional whole-unit buildings ("spacious floor plans",
"premier destination") — correctly *not* flagged. Flagging beds==baths alone
would flood these markets with false positives.

**But there is a real recall gap.** Two concrete Cambridge/Boston findings:

- ✅ `744 Columbus Ave, Boston (LightView)` — *"Off Campus Housing Near
  Northeastern University… furnished student apartments"* — **is** correctly
  flagged `per_person`. Explicit "off campus / student housing" language is
  caught.
- ❌ `11-13 Plymouth St, Cambridge (RoostUp)` — *"a beautifully renovated
  **private bedroom** … in a **4 bedroom/2 bath apartment**"* — a genuine
  by-the-room co-living listing, tagged **`per_unit`**. It slips through:
  "private bedroom" isn't a trigger phrase, and 4bd/2ba breaks `beds == baths`.

So co-living / by-the-room operators (RoostUp and similar) that describe a
"private bedroom in an N-bedroom apartment" are **missed**. Candidate recall-tune
phrases (add to `_HIGH_SIGNALS` / `_MEDIUM_SIGNALS` in
`app/services/pricing_model_detector.py`), weighted to preserve precision:

- Unambiguous → high signal: `co-?living`, `rent by the room`, `by-the-room`,
  `individual bedroom lease`, `per-bedroom lease`, `room in a \d+ ?bed`.
- Contextual → medium (needs another signal): `private bedroom` **only** when
  paired with "in a N bedroom apartment" (bare "private primary bedroom suite"
  in luxury listings would false-positive).

Not yet actioned — this is a data-quality/recall improvement, tracked here. It
affects a small absolute count (per-person is ~0.6% of buckets) but concentrated
exactly where students search.

**Also noted:** building-level `apartments.pricing_model` and the per-bucket
`apartment_floorplans.pricing_model` can disagree (744 Columbus is per_person at
the building level; the earlier by-city *bucket* count showed 0 fresh Boston
per-person buckets). Expected — they're detected on different bedroom values and
freshness windows — but worth remembering when reconciling the two.

## Known edges / follow-ups

- **True-cost fields on a projected dict are still building-level** (studio-based).
  The projected `rent` is correct, but `true_cost_monthly` isn't re-derived per
  floorplan yet — so the true-cost line can mismatch the projected rent.
- **Near-miss only widens bedrooms** (not budget) in v1. If all 3BRs are over
  budget, near-miss on size may still be empty; a budget-relaxing second tier is
  noted for v1.1.
- **Per-person whole-unit is an estimate** (`per_bed × bedrooms`); it assumes
  full occupancy and doesn't model shared common-area fees.
