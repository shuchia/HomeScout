# Pagination & Lazy AI Scoring — Design

*2026-04-01*

## Problem

Search returns a maximum of 10 results. Users want to see more listings. The current search endpoint blocks for 5-10 seconds waiting for Claude AI scoring before returning any results.

## Solution

Decouple search from AI scoring. All pages return heuristic-scored results immediately (~1 second). AI scores load asynchronously on a separate endpoint. Users can paginate through all matching results with a "Load More" button.

## Architecture

### Endpoint 1: `POST /api/search` (modified)

Returns heuristic-scored results with pagination. No Claude call.

**New request fields:**
- `page: int = 1` — page number (1-indexed)
- `page_size: int = 10` — results per page

**Response changes:**
- `page: int` — current page
- `has_more: bool` — whether more results exist
- `total_results: int` — total matching count (existing field)

**Flow (page 1):**
1. Filter from DB (city, budget, beds, baths, property type, freshness >= 40)
2. Heuristic score and sort all filtered results
3. Add distances if `near_lat`/`near_lng` provided
4. Filter by `max_distance_miles` if Pro + distance provided
5. Add cost breakdown data
6. Cache full sorted list in Redis (key = search params hash, TTL 10 min, reset on access)
7. Return requested page slice with `has_more` flag

**Flow (page 2+):**
1. Read cached list from Redis (reset TTL on access)
2. If cache miss: re-run steps 1-6
3. Return requested page slice

**What gets removed from search endpoint:**
- All Claude scoring logic (`_score_batch`, `_claude_semaphore`, batch splitting)
- Claude cache lookup/write
- The `top_n * 2` → Claude → merge → re-sort flow
- `get_top_apartments()` replaced by `get_apartments_paginated()`

### Endpoint 2: `POST /api/search/score-batch` (new)

AI scoring for a batch of apartment IDs. Pro only.

```
Request:
  apartment_ids: string[]     (max 10)
  search_context: {
    city, budget, bedrooms, bathrooms,
    property_type, move_in_date, other_preferences
  }

Response:
  scores: [
    { apartment_id, match_score, reasoning, highlights }
  ]
```

**Rules:**
- Pro only (403 for free tier)
- Max 10 IDs per call (400 if exceeded)
- Uses `ClaudeService.score_apartments()` with apartment data + search context
- Cached in Redis (sorted apartment IDs + search context hash, TTL 1 hour)
- On Claude timeout: returns empty scores array

### Redis Caching

**Search results cache:**
- Key: `search_results:{sha256(params_json)[:16]}`
- Value: JSON array of full sorted+scored apartment list
- TTL: 10 minutes, reset on every page fetch
- Evicted on new search with different params (different key)

**AI score cache (existing pattern):**
- Key: `claude_score:{sha256(ids+context)[:16]}`
- Value: JSON array of score objects
- TTL: 1 hour

## Frontend Changes

### Search Page (`app/page.tsx`)

**New state:**
- `currentPage: number` (starts at 1)
- `hasMore: boolean` (from API response)
- `loadingMore: boolean` (Load More button spinner)
- `aiLoadingIds: Set<string>` (apartment IDs awaiting AI scores)

**Search flow:**
1. User submits search → `POST /api/search` (page 1)
2. Results render immediately with heuristic scores
3. If Pro: call `POST /api/search/score-batch` with visible apartment IDs
4. While waiting: skeleton placeholders on score badge + reasoning area
5. Scores arrive → merge into results, skeletons replaced

**Load More flow:**
1. User clicks "Load More" → `POST /api/search` (page N+1)
2. Append new apartments to results array
3. If Pro: call `score-batch` for new apartment IDs
4. Same skeleton → score replacement as above

**"Load More" button:**
- Appears below results grid when `hasMore && !isLoading`
- Shows spinner while `loadingMore` is true
- Hidden when no more results

### ApartmentCard Changes

**New prop:** `aiLoading?: boolean`
- When `true`: pulsing skeleton on score badge + small skeleton bar for reasoning
- When `false` or omitted: render real score/reasoning or heuristic label

### Session Persistence

Extend `sessionStorage` to include `currentPage`, `hasMore`, and all loaded results across pages. Tab switch preserves full state.

### New Search Reset

Changing any search parameter resets `currentPage` to 1, clears all results, and starts fresh.

## Tier Behavior

| Feature | Free | Pro |
|---------|------|-----|
| Pagination (Load More) | Yes | Yes |
| Heuristic scores | All pages | All pages |
| AI score backfill | No | Yes (auto) |
| AI skeleton placeholders | No | Yes |
| Max distance filter | No | Yes |
| Searches per day | 3 | Unlimited |

Free users see heuristic labels (Excellent/Great/Good/Fair Match) on all pages permanently. No skeleton, no AI backfill call.

## Test Cases (22)

### Backend — Search Pagination

1. Page 1 returns heuristic-scored results only (no Claude, fast)
2. Page 2 returns next 10 from cached list
3. Cache miss on page 2 re-runs query transparently
4. Cache TTL resets on each page fetch
5. `has_more: false` when results exhausted
6. Page beyond available results returns empty, `has_more: false`
7. Distance and cost data included on all pages
8. New search params create new cache
9. Free tier: pagination works, no score-batch available

### Backend — Score Batch

10. Pro gets AI scores for given IDs
11. Free gets 403
12. More than 10 IDs rejected with 400
13. Claude timeout returns empty scores (no 500)
14. Same IDs + context returns cached scores

### Frontend

15. Results appear immediately with heuristic scores
16. AI skeleton shows on all cards while score-batch loads (Pro)
17. AI scores replace skeleton when backfill completes
18. Free tier: heuristic labels permanent, no skeleton
19. "Load More" appears when `has_more` is true
20. Load More appends results, triggers new score-batch
21. Session persistence includes all loaded pages
22. New search resets to page 1
