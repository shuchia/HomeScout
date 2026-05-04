# Availability Date Extraction — Design

*2026-03-30*

## Problem

Apartments.com listings return availability data in `models` and `rentals` arrays, but the scraper hardcodes `available_date=None`. Users see "N/A" for availability on all apartments.com listings.

## Data Structure (Apify Response)

```
models[]:
  modelId       — floor plan identifier
  availability  — "2 Available units" or "0 Available units"
  availabilityInfo — "Now" or "N/A"

rentals[]:
  modelId       — links to parent model
  availableDate — ISO 8601: "2026-03-29T00:00:00-04:00"
  availability  — "Now" or other status
```

One Apify item = one property. One property has many models (floor plans) and many rentals (specific units).

## Approach: Earliest Available Date Across All Units

Since the normalizer creates one `ScrapedListing` per property, we extract a single `available_date` representing the soonest a renter could move in.

### Extraction Logic (backend)

1. Collect `modelId`s from `models` where `availability` does NOT start with `"0 "`.
2. From `rentals` matching those `modelId`s, collect `availableDate` values (parse ISO → `YYYY-MM-DD`).
3. Pick the earliest (min) date.
4. If available models exist but no rentals have dates → `"Now"`.
5. If no models have availability → `None`.

### Frontend Display (ApartmentCard)

- **Past date or "Now"**: Green "Available now" badge + "View units" link (`source_url`, opens new tab).
- **Future date**: Formatted date (e.g., "Apr 15, 2026") + "View units" link.
- **Null**: Gray "Availability not confirmed" text, no link.

### Move-in Date Mismatch Indicator

When the user provides a `move_in_date` in search, pass it as a prop to `ApartmentCard`. Show indicators:

- **available_date is after move_in_date**: Amber text `"Available after your move-in date"` below availability line.
- **available_date is null**: Gray text `"Availability not confirmed"`.
- **No move_in_date provided or no issue**: No indicator.

No filtering — all listings are shown regardless of availability mismatch. The indicator is informational only.

## Changes Required

### Backend

**`services/scrapers/apify_service.py`** — `_normalize_apartments_com_listing()`:
- Add availability extraction block before contact info extraction.
- Pass extracted date to `ScrapedListing(available_date=...)` instead of `None`.

**`schemas.py`** — No changes (available_date already exists as `Optional[str]`).

**`models/apartment.py`** — No changes (available_date already exists as `String(20)`).

### Frontend

**`types/apartment.ts`** — No changes (available_date already exists as `string`).

**`components/ApartmentCard.tsx`** — Add:
- Availability display section with conditional formatting.
- "View units" link using `source_url`.
- Move-in mismatch indicator (receives `moveInDate` prop).

**`app/page.tsx`** — Pass `move_in_date` from search form state to `ApartmentCard` as prop.

## Test Cases (21)

### Backend — Availability Extraction

1. Rentals with ISO dates → extracts earliest date.
2. All units "Now" (no ISO dates) → returns `"Now"`.
3. All models "0 Available units" → returns `None`.
4. Mixed model availability → only considers available models' rentals.
5. No models/rentals arrays in raw data → returns `None`.
6. Malformed availableDate string → skips without crashing.
13. Multiple rentals same model, different dates → picks earliest.
14. Rental modelId not in models array → ignored.
15. Timezone offset in availableDate → parses correctly.
16. Model has units but zero matching rentals → falls back to `"Now"`.
17. All rentals have past dates → returns earliest (frontend handles display).

### Backend — Search

7. Move-in date preserved in response for frontend indicator use.

### Frontend — Display

8. Past date → "Available now" badge + "View units" link.
9. Future date → formatted date + "View units" link.
10. Null → "Availability not confirmed", no link.
11. Listing date after move-in → amber warning text.
12. No move-in date provided → no indicator on any card.
18. Move-in is today, listing "Now" → no warning.
19. Move-in is today, listing available tomorrow → amber warning.
20. source_url is null → no "View units" link rendered.
21. available_date is string "Now" → displays "Available now" without date parse crash.
