# Proximity Search Design

## Overview

Add the ability for users to search for apartments near a specific location — a school, hospital, office, or any landmark. Users type a place name (e.g. "Children's Hospital of Philadelphia"), the system geocodes it, and every result shows crow-flies distance. Pro users can filter by a max radius.

**Target user:** Med students, young professionals relocating — people with a specific place they need to commute to daily.

## User Experience

### Search Form

A new optional "Near" field appears in the SearchForm below the city selector:

- Text input with placeholder: *"e.g. Children's Hospital of Philadelphia"*
- As the user types (debounced 500ms), calls OpenStreetMap Nominatim API for autocomplete suggestions
- User picks a result, which resolves to lat/lng stored in component state
- Clear (×) button removes the reference location and hides distance/slider UI

### Distance Display (All Users)

Once a reference location is set, every result card shows crow-flies distance:

- Small pin icon with distance below the address (e.g. "0.8 mi from Children's Hospital...")
- Label truncated if long
- Results sorted by distance (nearest first) by default
- Apartments without lat/lng data appear at the end with no distance shown

### Radius Filter (Pro Only)

When a reference location is set:

- **Pro users:** radius slider appears (0.5–10 miles, step 0.5). Apartments beyond the radius are filtered out.
- **Free users:** slider shown disabled with a "Pro" badge linking to `/pricing`

### Comparison Page

Distance and reference label are passed through to the compare page via the Zustand search context store. The comparison table shows a "Distance" row when a reference location was used.

## Data Flow

```
User types "Children's Hospital of Philadelphia"
    │
    ↓ (debounced 500ms)
Frontend calls Nominatim API (no API key needed)
    │
    ↓ returns suggestions with lat/lng
User selects a suggestion
    │
    ↓ stores { lat, lng, label } in form state
searchApartments() sends near_lat, near_lng, near_label, max_distance_miles
    │
    ↓
Backend apartment_service.py
    ├── Calculates Haversine distance for each apartment
    ├── Filters by max_distance_miles (Pro only, ignored for free)
    ├── Sorts by distance (nearest first)
    └── Appends distance_miles to each result
    │
    ↓
Claude scoring prompt includes:
    "User wants to be near Children's Hospital of Philadelphia.
     Apartment A is 0.8 mi away, Apartment B is 3.2 mi away."
    │
    ↓
Frontend displays distance on each ApartmentCard
```

## Backend Changes

### schemas.py — SearchRequest

New optional fields:

```python
near_lat: Optional[float] = None       # Latitude of reference location
near_lng: Optional[float] = None       # Longitude of reference location
near_label: Optional[str] = None       # Display name (e.g. "Children's Hospital of Philadelphia")
max_distance_miles: Optional[float] = None  # Pro-only radius filter (0.5–10)
```

### apartment_service.py — Filtering

When `near_lat`/`near_lng` are provided:

- Calculate crow-flies distance using Haversine formula (pure Python, no external dependency)
- Append `distance_miles` (rounded to 1 decimal) to each apartment result
- If `max_distance_miles` is set AND user is Pro, exclude apartments beyond the radius
- If user is free, ignore `max_distance_miles` (don't filter, just show distance)
- Apartments without lat/lng: include but place at end with `distance_miles: null`
- Default sort: nearest first (when reference location is provided)

### claude_service.py — Scoring Prompt

When a reference location is provided, append to the scoring prompt:

```
The user wants to be near {near_label}.
Distances from reference location:
- {apartment_name}: {distance} miles
- {apartment_name}: {distance} miles
...
Factor proximity into your match scoring and reasoning.
```

### Tier Gating

- `max_distance_miles` is only respected when `TierService.get_user_tier()` returns "pro"
- Free users sending `max_distance_miles` have it silently ignored
- Distance calculation and display (`distance_miles` in response) is available to all users

## Frontend Changes

### New: lib/geocode.ts

Utility function calling Nominatim:

```
GET https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=5&countrycodes=us
```

- Debounced at 500ms
- Respects Nominatim's 1 request/second rate limit
- Returns array of `{ display_name, lat, lng }`
- User-Agent header set to "HomeScout/1.0" (Nominatim requires this)

### New: components/NearLocationInput.tsx

- Text input with dropdown suggestion list (combobox pattern)
- On selection, stores `{ lat, lng, label }` in parent form state
- Clear (×) button to remove reference location
- Loading spinner while geocoding

### New: components/RadiusSlider.tsx

- Only rendered when reference location is set
- Range: 0.5–10 miles, step 0.5
- Displays current value as "Within X mi"
- Pro users: functional slider
- Free users: disabled slider with "Pro" badge → `/pricing`

### Modified: components/SearchForm.tsx

- Add NearLocationInput below city selector
- Add RadiusSlider below NearLocationInput (conditional)
- Pass `near_lat`, `near_lng`, `near_label`, `max_distance_miles` to API call

### Modified: components/ApartmentCard.tsx

- When `distance_miles` is present, show pin icon with distance below address
- Format: "0.8 mi from Children's Hospital..." (truncate label if > 30 chars)

### Modified: types/apartment.ts

- Add `distance_miles?: number | null` to apartment interfaces
- Add `near_lat`, `near_lng`, `near_label`, `max_distance_miles` to SearchParams

### Modified: hooks/useComparison.ts

- Include `near_label` and `distance_miles` in search context passed to compare page

### Modified: app/compare/page.tsx

- Show "Distance" row in comparison table when `near_label` is in search context

## Tier Behavior Summary

| Feature | Free | Pro |
|---------|------|-----|
| "Near" text input | Yes | Yes |
| Distance shown on cards | Yes | Yes |
| Distance in Claude scoring | Yes (Pro only gets Claude) | Yes |
| Radius slider | Shown disabled + upgrade prompt | Functional (0.5–10 mi) |
| Distance in comparison table | Yes | Yes |

## What We're NOT Building

- **No map view** — no interactive map showing apartments as pins. Just text-based distance. Map can come later.
- **No real commute times** — no Google Maps Directions API, no walking/transit/driving time estimates. Just crow-flies miles.
- **No saved reference locations** — user enters it fresh each search. No "save my school" feature.
- **No multiple reference points** — one "Near" location per search, not "near school AND near grocery store."
- **No reverse geocoding** — we don't convert apartment lat/lng to neighborhood names.
- **No PostGIS** — Haversine in Python is sufficient for filtering ~100-200 results per city. No database extension needed.
- **No Nominatim self-hosting** — use the public API with rate limiting. Self-host only if we hit usage limits.

## Haversine Formula Reference

```python
import math

def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 3958.8  # Earth's radius in miles
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))
```
