# Enhanced Apartment Comparison Tool — Design

**Date:** 2026-02-17
**Status:** Approved

## Overview

Enhance the existing comparison tool so that when a user hits "Score" on the compare page, Claude performs a deep head-to-head analysis of the selected apartments. The analysis includes an overall winner pick, per-apartment scores, and category-by-category breakdowns driven by both standard fields and the user's stated preferences.

## User Flow

1. User must be signed in to search and compare (auth gate on both pages).
2. User searches with criteria (city, budget, beds, baths, property type, move-in date) plus "Other Preferences" free text.
3. Search results come back with Claude scores (existing behavior).
4. User adds 2-3 apartments to comparison via the Compare button.
5. Navigates to `/compare` — sees the side-by-side data table (basic data, no comparison scores yet).
6. Preferences input is pre-filled with the "Other Preferences" from the search form — user can edit/refine.
7. Hits Score — loading state while Claude analyzes.
8. Summary card appears at the top with winner, overall scores, and category breakdown.
9. Existing table below gets enhanced with category score rows and winner highlights.

## State Management — Connecting Search to Compare

The Zustand comparison store (`useComparison`) is extended with a `searchContext` field that stores the search criteria and preferences when a search is performed.

```typescript
interface ComparisonStore {
  apartmentIds: string[]
  searchContext: {
    city: string
    budget: number
    bedrooms: number
    bathrooms: number
    property_type: string
    move_in_date: string
    other_preferences: string
  } | null
  setSearchContext: (ctx: SearchContext) => void
  // ... existing methods
}
```

When the user submits a search on the home page, `SearchForm` calls `setSearchContext()` with the current form values. When the compare page loads, it reads `searchContext` to pre-fill the preferences input. The user can edit the preferences before hitting Score. When Score is hit, the full `searchContext` plus edited preferences are sent to the backend.

## Backend Changes

### Endpoint: `POST /api/apartments/compare` (enhanced)

**Request** (updated schema):
```json
{
  "apartment_ids": ["id-1", "id-2", "id-3"],
  "preferences": "parking, quiet for WFH, near transit",
  "search_context": {
    "city": "Pittsburgh, PA",
    "budget": 2000,
    "bedrooms": 1,
    "bathrooms": 1,
    "property_type": "Apartment",
    "move_in_date": "2026-03-01"
  }
}
```

**Response** (new `comparison_analysis` field when preferences provided):
```json
{
  "apartments": [],
  "comparison_fields": ["rent", "bedrooms", "..."],
  "comparison_analysis": {
    "winner": {
      "apartment_id": "id-1",
      "reason": "Best overall match — has dedicated parking and is in a quiet residential area ideal for working from home"
    },
    "categories": ["Value", "Space & Layout", "Amenities", "Parking", "WFH Suitability", "Transit Access"],
    "apartment_scores": [
      {
        "apartment_id": "id-1",
        "overall_score": 88,
        "reasoning": "Strong match on your top priorities...",
        "highlights": ["Dedicated parking", "Quiet floor"],
        "category_scores": {
          "Value": { "score": 82, "note": "$1.85/sqft — mid-range but fair for the area" },
          "Space & Layout": { "score": 75, "note": "750 sqft, open layout" },
          "Amenities": { "score": 80, "note": "Has laundry, gym, no pool" },
          "Parking": { "score": 95, "note": "Dedicated covered spot included" },
          "WFH Suitability": { "score": 90, "note": "Quiet residential block" },
          "Transit Access": { "score": 70, "note": "Bus stop 8 min walk, no direct rail" }
        }
      }
    ]
  }
}
```

When `preferences` is null or empty, `comparison_analysis` is omitted and the endpoint returns apartment data only (current behavior).

### Claude Prompt Context

The compare prompt includes both the search criteria and the user's preferences:

```
## Original Search Criteria
City: Pittsburgh, PA | Budget: $2,000/mo | Bedrooms: 1 | Bathrooms: 1 | Type: Apartment | Move-in: 2026-03-01

## What Matters Most to This User
parking, quiet for WFH, near transit

## Apartments to Compare
[slimmed apartment data]

Compare these apartments across categories. Always include Value, Space & Layout, and Amenities as standard categories. Add 1-3 custom categories based on what matters most to this user. Score each apartment 0-100 per category. Pick an overall winner.
```

### New Claude Service Method

`compare_apartments_with_analysis()` — separate from the existing `score_apartments()` used by search. Apartment data is slimmed the same way (max 15 amenities, 300-char descriptions). Called via `asyncio.to_thread()` to avoid blocking the async event loop.

## Frontend Changes

### A. Winner Summary Card (appears after scoring)

Green-bordered card at the top of the compare page. Shows the winning apartment's address with a winner indicator, plain-text reason why it won, and overall scores for all apartments as colored badges side by side.

### B. Category Scores Section (appears after scoring)

Grid of category rows below the summary card. Each row shows: category name, score per apartment (colored by score range), and a winner highlight on the highest score. Category notes displayed inline in smaller text beneath each score.

### C. Existing Comparison Table Enhanced

New "Overall Score" row at the top with winner ring highlight. AI Reasoning row updated with the richer per-apartment reasoning and highlights from the comparison analysis.

### D. Preferences Input Pre-fill

On page load, read `searchContext.other_preferences` from the Zustand store. Pre-fill the preferences text input with that value. User can edit before hitting Score.

### E. Auth Gate

Both `/` (search page) and `/compare` check for signed-in user. If not signed in, show sign-in prompt using the same pattern as the current favorites page.

## Schema Changes

### Backend — New Pydantic Models

- `SearchContext` — `city`, `budget`, `bedrooms`, `bathrooms`, `property_type`, `move_in_date`
- `CategoryScore` — `score: int`, `note: str`
- `ApartmentComparisonScore` — `apartment_id`, `overall_score`, `reasoning`, `highlights`, `category_scores: dict[str, CategoryScore]`
- `ComparisonWinner` — `apartment_id`, `reason`
- `ComparisonAnalysis` — `winner: ComparisonWinner`, `categories: list[str]`, `apartment_scores: list[ApartmentComparisonScore]`
- `CompareRequest` updated — add optional `search_context: SearchContext`
- `CompareResponse` updated — add optional `comparison_analysis: ComparisonAnalysis`

### Frontend — New TypeScript Interfaces

Mirror the backend models in `types/apartment.ts`:
- `SearchContext`
- `CategoryScore`
- `ApartmentComparisonScore`
- `ComparisonWinner`
- `ComparisonAnalysis`

Update `CompareResponse` to include optional `comparison_analysis`.

## Two Distinct Claude Scoring Purposes

| | Search Scoring | Compare Scoring |
|---|---|---|
| **When** | User hits "Find Apartments" | User hits "Score" on compare page |
| **Input** | Search criteria + preferences + ~20 filtered apartments | Search criteria + preferences + 2-3 specific apartments |
| **Purpose** | Broad triage — rank which apartments best match | Deep head-to-head — category breakdown + winner |
| **Output** | `match_score`, `reasoning`, `highlights` per apartment | `overall_score`, `category_scores`, `winner`, `reasoning` per apartment |
| **Claude method** | `score_apartments()` (existing) | `compare_apartments_with_analysis()` (new) |

## Out of Scope

- No charts or radar graphs — scores and text only
- No saving or sharing comparisons
- No comparison history
- No changes to CompareButton or ComparisonBar components
- No changes to the existing search scoring flow
