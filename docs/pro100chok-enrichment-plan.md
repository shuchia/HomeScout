# Per-Tour pro100chok Enrichment — Implementation Plan

> Status: planned (not yet implemented)
> Owner: tied to task #29
> Origin: 2026-06-17 spike + brainstorm; see memory `project_scraper_migration.md` for the decision history

## TL;DR

Keep epctex for the bulk-search pipeline. Add a per-listing pro100chok detail call that fires async when a user signals interest (favorite, compare-add, or tour-add). Cost: ~$3/month at beta scale. Unlocks authoritative utility-inclusion data via apartments.com's own FAQ Q&A, plus office hours, property flags, and bike/sound scores.

## Architecture context (what surprised the spike)

Two architectural surprises that drove the trigger design:

1. **Favorites is client-side direct to Supabase.** `frontend/hooks/useFavorites.ts:108` calls `supabase.from('favorites').insert(...)` — no backend endpoint exists for the favorite-click. To trigger enrichment, we need a new lightweight backend endpoint the hook calls after its Supabase write.
2. **Compare is also client-side**, stored in a zustand cookie named `snugd-comparison`. Same bridge requirement.

Both are async, fire-and-forget actions from the user's perspective. Neither is latency-sensitive, which makes them ideal enrichment triggers.

## Trigger plan

| Trigger | Endpoint | Frontend touch |
|---|---|---|
| Tour add | `POST /api/tours` (existing) | None — wire `BackgroundTasks` to existing handler |
| Favorite add | `POST /api/apartments/{id}/track-interest` (new) | One line in `useFavorites.addFavorite()` |
| Compare add | `POST /api/apartments/{id}/track-interest` (new) | One line in `useComparison` add-handler |

All three call the same `enrich_apartment(apartment_id)` service. The 7-day TTL on `last_enriched_at` deduplicates — first trigger wins, subsequent triggers within the window are no-ops.

The `track-interest` endpoint is single-purpose: takes an apartment ID, schedules `BackgroundTasks.add_task(enrich_apartment, id)`, returns `204`. Authenticated but tier-agnostic. Failures are silent — never block the user's primary action.

## Data model changes

Migration adds:

| Column | Type | Source |
|---|---|---|
| `faq` | JSONB | `pro100chok.faq` (array of {question, answer}) |
| `office_hours` | JSONB | `pro100chok.officeHours` |
| `property_flags` | JSONB | `pro100chok.flags` (15 booleans) |
| `bike_score` | Integer | `pro100chok.scores.bikeScore` |
| `sound_score` | Integer | `pro100chok.scores.soundScore` |

The existing `last_enriched_at` column (added in Commit 1's migration `k7g8h9i0j1k2`, sitting unused since the Commit 2 revert) is repurposed as the TTL gate.

## Service function (sketch)

```python
# backend/app/services/enrichment_service.py
ENRICHMENT_TTL_DAYS = 7

async def enrich_apartment(apartment_id: str) -> dict:
    """Fire-and-forget. Never raises; returns status dict."""
    if not is_database_enabled():
        return {"status": "skipped", "reason": "db_disabled"}

    # Phase 1: TTL gate (short session, no Apify call yet)
    async with get_session_context() as session:
        apt = await session.get(ApartmentModel, apartment_id)
        if not apt:
            return {"status": "not_found"}
        if not apt.source_url:
            return {"status": "skipped", "reason": "no_source_url"}
        if apt.last_enriched_at:
            age = datetime.now(tz=utc) - apt.last_enriched_at
            if age < timedelta(days=ENRICHMENT_TTL_DAYS):
                return {"status": "skipped", "reason": "fresh"}
        source_url = apt.source_url

    # Phase 2: pro100chok detail call (no DB session held)
    detail = await Pro100ChokService().scrape_listing_detail(source_url)
    now = datetime.now(tz=utc)

    if not detail:
        # Still stamp last_enriched_at to prevent retry storms
        await _stamp_enriched_at(apartment_id, now)
        return {"status": "no_data"}

    # Phase 3: merge + re-run cost calculation
    async with get_session_context() as session:
        apt = await session.get(ApartmentModel, apartment_id)
        _merge_pro100chok_into_apartment(apt, detail)  # fill-only for shared fields
        apt.faq = detail.get("faq")
        apt.office_hours = detail.get("officeHours")
        apt.property_flags = detail.get("flags")
        apt.bike_score = (detail.get("scores") or {}).get("bikeScore")
        apt.sound_score = (detail.get("scores") or {}).get("soundScore")
        apt.last_enriched_at = now

        # Re-run cost estimator with FAQ-authoritative utility data
        breakdown = cost_estimator.compute_true_cost(
            rent=apt.rent, zip_code=apt.zip_code, bedrooms=apt.bedrooms,
            amenities=apt.amenities or [], scraped_fees=_extract_fees(apt),
            description=apt.description or "",
            faq=apt.faq,  # FAQ-aware detector uses this
        )
        for field in ("est_electric", "est_gas", "est_water",
                      "utilities_included", "true_cost_monthly", "true_cost_move_in"):
            setattr(apt, field, breakdown[field])

        await session.commit()

    return {"status": "enriched", "apartment_id": apartment_id}
```

## pro100chok API integration

**Input shape** (verified by spike):

```json
{
  "action": "details",
  "listingUrls": [{"url": "https://www.apartments.com/aera/g5qm48y/"}],
  "startUrls":   [{"url": "https://www.apartments.com/aera/g5qm48y/"}],
  "maxPages": 1,
  "maxItems": 1,
  "concurrency": 5,
  "proxyConfiguration": {
    "useApifyProxy": true,
    "apifyProxyGroups": ["RESIDENTIAL"],
    "apifyProxyCountry": "US"
  }
}
```

Both `listingUrls` and `startUrls` are included for safety. Bare strings fail — must be `{url: "..."}` objects.

Actor ID: `2bXBHs5BF7iBki2rV` (`pro100chok/apartments-scraper-usage`).

## FAQ-aware utility detector

Lives in `cost_estimator.py`. Checks FAQ first; falls back to existing regex when FAQ missing.

```python
def _faq_utility_status(faq: List[Dict]) -> Optional[Dict[str, bool]]:
    """Return definitive utility-inclusion answers from FAQ, or None to fall back."""
    if not faq:
        return None
    for entry in faq:
        q = (entry.get("question") or "").lower()
        if "utilit" not in q or "include" not in q:
            continue
        a = re.sub(r"<[^>]+>", "", (entry.get("answer") or "").lower())
        if "not included" in a or "do not include" in a:
            return {"heat": False, "water": False, "electric": False,
                    "internet": False, "all_included": False}
        if "all utilities" in a and "include" in a:
            return {"heat": True, "water": True, "electric": True,
                    "internet": True, "all_included": True}
        # Some listings enumerate specific utilities
        return {
            "heat":     "heat" in a or "gas" in a,
            "water":    "water" in a or "sewer" in a,
            "electric": "electric" in a,
            "internet": "wifi" in a or "internet" in a,
            "all_included": False,
        }
    return None
```

`compute_true_cost()` accepts a new optional `faq` param; uses `_faq_utility_status()` when present, falls back to regex when not.

## Other pro100chok data worth extracting

Ranked by user value:

| Field | Value | Phase |
|---|---|---|
| `faq` | Authoritative utility/laundry/parking/pet answers | 1 |
| `officeHours` | "Office open until 6pm" badge on Contact tab | 1 |
| `flags.hasOnlineScheduling` | "Schedule a tour online" CTA | 1 |
| `flags.has3DTour` | "3D tour available" badge | 1 |
| `flags.hasRequestTour` | Tour-request CTA visibility | 1 |
| `scores.bikeScore` | Bike-friendliness badge | 1 |
| `scores.soundScore` | Quiet/noisy area badge | 1 |
| `flags.isGreystar`, `isMF` | Property-management classification for templated messaging | 2 |
| `reviews` (text) | If present, actual review excerpts | 2 (needs UX design) |
| Cleaner `fees` per-pet-type | Resolves pet one-time fee under-count flagged in readiness doc | 2 |
| `media` (videos, 3D) | Compare to epctex's `virtualTours` — may be equivalent | Investigate |
| `pointsOfInterest` | Duplicates `transit_options` already extracted | Skip |
| `breadcrumb`, `meta` | No incremental value | Skip |

## Scenarios + handling

| Scenario | Behavior |
|---|---|
| Happy path | Background task → 30-60s later, apartment has FAQ + updated cost |
| User favorites + compares within seconds | First trigger wins; second sees fresh `last_enriched_at` and skips |
| pro100chok times out or fails | Stamp `last_enriched_at` anyway. Silent failure. Log to CloudWatch. |
| Listing has no `source_url` | Skip with reason `no_source_url`. Very rare. |
| Listing removed from apartments.com | pro100chok returns 0 items. Stamp timestamp, no fields filled. Optionally bump `verification_status` to "gone". |
| Apify down | All enrichments fail silently. Retry on next favorite/compare/tour after the 60s in-flight gate clears. |
| Cost runaway (bug fires on every search result) | Worst case: 989 apartments × $0.002 = $2. Acceptable without a budget cap. |
| User favorites 50 in one session | 50 tasks queue. Apify concurrency sequences them. UI must handle mixed enriched/unenriched state. |
| Concurrent users favorite same apartment | First wins; rest skip on TTL or in-flight check |
| TTL expires mid-funnel | Compare-add at day 10 fires fresh enrichment → updated data in seconds |
| Anonymous browsing | No trigger (no favorites for anon users). Anon sees regex-quality only. |

## Pros / Cons

**Pros:**
- Low risk — bulk pipeline untouched
- Low cost — ~$3-5/month at beta scale (40-100× cheaper than full migration)
- High-value data lands where decisions are made
- Reuses validated Commit 2 architecture (BackgroundTasks + TTL + fill-only merge)
- Compare AI gets smarter for Pro users — FAQ goes into Claude prompt context
- Falls back gracefully if pro100chok fails
- Popular apartments enriched once, shared across users

**Cons:**
- Two utility-data sources of truth (regex for unenriched, FAQ for enriched) — debug noise
- Cold start: first favorite waits 30-60s for enrichment. UI must handle.
- 7-day TTL means same-week policy changes aren't reflected
- New `Pro100ChokService` + `track-interest` endpoint add test surface
- Anonymous + non-favorited apartments stay on regex quality

## Implementation phases

**Phase 1 — backend infra (M, ~1 day):**
- Alembic migration: 5 new columns
- `Pro100ChokService` (new file, mirrors `ApifyService` pattern)
- `enrichment_service.py` (recreated, pro100chok flavor)
- FAQ-aware extension to `cost_estimator.py`
- `POST /api/apartments/{id}/track-interest` endpoint
- Wire `BackgroundTasks` into `POST /api/tours` (Commit 2 redux)
- 4-6 unit tests covering FAQ parse cases + TTL gate

**Phase 2 — frontend triggers (S, ~½ day):**
- `useFavorites.addFavorite()` → fire-and-forget POST to track-interest
- `useComparison` add handler → same
- No UI changes

**Phase 3 — UI surfaces (M, ~1 day, optional for ship):**
- Office-hours badge on Contact tab
- "Schedule tour online" CTA when `flags.hasOnlineScheduling`
- Bike/sound score badges on apartment card
- FAQ accordion on apartment detail page (Pro-tier?)

**Phases 1+2 can ship without 3** — Compare AI quality and cost calculations improve immediately; phase 3 is pure visualization.

## Cost model

Beta assumptions:
- 100 active users
- ~15 favorites + 5 compares + 3 tours per user per month = 23 triggers
- Total: 2,300 events/month
- After TTL dedup: ~1,500 unique enrichments
- Apify cost: 1,500 × $0.002 = **$3/month**

At 1,000 active users: ~$30/month. Negligible.

## Open questions

1. Should `track-interest` accept anonymous calls? **Default: auth-only** — anon users don't have persisted favorites/compare anyway.
2. Should Compare page-load trigger enrichment as a safety net for users who added before the feature shipped? **Default: no** — backfill organically.
3. One-time backfill of top-N most-viewed listings before launch? **Default: no** — organic backfill happens fast at any active scale.
4. Keep Tour-add as the third trigger? **Default: yes** — safety net for users who skip favorite/compare.

## Related

- Memory: `project_scraper_migration.md` (decision history)
- Memory: `reference_epctex_modes_identical.md` (why epctex URL-mode failed)
- Previous attempt: commit `7e2a473` (Commit 2, used wrong actor) → reverted `0c51e1e`
- Task: #29
