# Pagination & Lazy AI Scoring — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Decouple search from Claude AI scoring so results appear instantly with heuristic scores, AI scores lazy-load via a separate endpoint, and users can paginate with "Load More."

**Architecture:** The search endpoint returns heuristic-scored results with Redis-cached pagination. A new `score-batch` endpoint handles Pro-only AI scoring asynchronously. The frontend renders heuristic results immediately and backfills AI scores with skeleton placeholders.

**Tech Stack:** FastAPI, Redis (aioredis), SQLAlchemy, Next.js/React, TypeScript, Claude API

---

### Task 1: Add pagination fields to backend schemas

**Files:**
- Modify: `backend/app/schemas.py` — `SearchRequest` and `SearchResponse` classes

**Step 1: Add pagination fields to SearchRequest**

In `SearchRequest` (after `max_distance_miles` field, around line 19), add:

```python
page: int = Field(1, ge=1, description="Page number (1-indexed)")
page_size: int = Field(10, ge=1, le=50, description="Results per page")
```

**Step 2: Update SearchResponse to include pagination metadata**

Find `SearchResponse` class and add `page` and `has_more` fields:

```python
class SearchResponse(BaseModel):
    apartments: List[ApartmentWithScore]
    total_results: int
    page: int = 1
    has_more: bool = False
    tier: Optional[str] = None
    searches_remaining: Optional[int] = None
```

**Step 3: Add ScoreBatchRequest and ScoreBatchResponse schemas**

After `SearchResponse`, add:

```python
class ScoreBatchRequest(BaseModel):
    """Request to score a batch of apartments via Claude AI."""
    apartment_ids: List[str] = Field(..., max_length=10)
    search_context: SearchContext

class ApartmentScore(BaseModel):
    """Score result for one apartment."""
    apartment_id: str
    match_score: int = Field(..., ge=0, le=100)
    reasoning: str
    highlights: List[str]

class ScoreBatchResponse(BaseModel):
    """Response with AI scores for a batch of apartments."""
    scores: List[ApartmentScore]
```

Note: `ApartmentScore` may already exist — check and reuse if so.

**Step 4: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat(schemas): add pagination and score-batch request/response models"
```

---

### Task 2: Add `get_apartments_paginated()` to apartment service

**Files:**
- Modify: `backend/app/services/apartment_service.py`

**Step 1: Add the new paginated method**

After the existing `search_apartments()` method (around line 203), add a new method. This replaces the Claude-coupled `get_top_apartments()` for search:

```python
async def get_apartments_paginated(
    self,
    city: str,
    budget: int,
    bedrooms: int,
    bathrooms: int,
    property_type: str,
    move_in_date: str,
    other_preferences: str = None,
    page: int = 1,
    page_size: int = 10,
) -> Tuple[List[Dict], int, bool]:
    """
    Get paginated heuristic-scored apartments.

    Returns:
        Tuple of (page_results, total_count, has_more)
    """
    from app.services.scoring_service import ScoringService

    # Build cache key from search params (excluding page)
    raw = f"{city}:{budget}:{bedrooms}:{bathrooms}:{property_type}:{move_in_date}:{other_preferences or ''}"
    cache_key = f"search_pages:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    # Try cache first (for page 2+)
    cached = None
    if self._redis and page > 1:
        try:
            cached = await self._redis.get(cache_key)
        except Exception:
            pass

    if cached:
        all_scored = json.loads(cached)
        # Reset TTL on access
        try:
            await self._redis.expire(cache_key, 600)
        except Exception:
            pass
    else:
        # Filter and score
        filtered = await self.search_apartments(
            city=city, budget=budget, bedrooms=bedrooms,
            bathrooms=bathrooms, property_type=property_type,
            move_in_date=move_in_date,
        )

        if not filtered:
            return [], 0, False

        all_scored = ScoringService.score_apartments_list(
            apartments=filtered, budget=budget,
            bedrooms=bedrooms, bathrooms=bathrooms,
            other_preferences=other_preferences,
        )

        # Cache the full list (10 min TTL)
        if self._redis:
            try:
                await self._redis.setex(cache_key, 600, json.dumps(all_scored))
            except Exception:
                pass

    total_count = len(all_scored)
    start = (page - 1) * page_size
    end = start + page_size
    page_results = all_scored[start:end]
    has_more = end < total_count

    return page_results, total_count, has_more
```

**Step 2: Commit**

```bash
git add backend/app/services/apartment_service.py
git commit -m "feat(service): add get_apartments_paginated with Redis caching"
```

---

### Task 3: Rewrite search endpoint to use pagination (no Claude)

**Files:**
- Modify: `backend/app/main.py` — the `search_apartments` endpoint (lines 153-290)

**Step 1: Replace the search endpoint body**

The new endpoint uses `get_apartments_paginated()` for ALL tiers (no Claude call). Replace the try block (lines 188-281) with:

```python
    try:
        page_results, total_count, has_more = await apartment_service.get_apartments_paginated(
            city=request.city,
            budget=request.budget,
            bedrooms=request.bedrooms,
            bathrooms=request.bathrooms,
            property_type=request.property_type,
            move_in_date=request.move_in_date,
            other_preferences=request.other_preferences,
            page=request.page,
            page_size=request.page_size,
        )

        # Add heuristic score fields, null out AI fields
        apartments_out = [
            {
                **apt,
                "match_score": None,
                "reasoning": None,
                "highlights": [],
            }
            for apt in page_results
        ]

        # Increment counter for free users (only on page 1)
        if tier == "free" and request.page == 1:
            await TierService.increment_search_count(user.user_id)
            searches_remaining = max(0, searches_remaining - 1)

        # Apply proximity distances
        from app.services.distance import add_distances

        if request.near_lat is not None and request.near_lng is not None:
            result_dicts = []
            for apt in apartments_out:
                if isinstance(apt, dict):
                    result_dicts.append(apt)
                elif hasattr(apt, 'model_dump'):
                    result_dicts.append(apt.model_dump())
                else:
                    result_dicts.append(apt.__dict__)

            max_dist = request.max_distance_miles if tier == "pro" else None
            result_dicts = add_distances(result_dicts, request.near_lat, request.near_lng, max_dist)
            apartments_out = result_dicts
            # Recalculate has_more after distance filtering
            if max_dist:
                total_count = len(result_dicts)
                has_more = False  # distance filtering applied to page, can't paginate further

        # Add true cost data
        from app.routers.apartments import _add_cost_breakdown
        is_pro = tier == "pro"
        final_apartments = []
        for apt in apartments_out:
            apt_dict = apt if isinstance(apt, dict) else apt.model_dump() if hasattr(apt, 'model_dump') else apt.__dict__
            apt_dict = _add_cost_breakdown(apt_dict, include_breakdown=is_pro)
            final_apartments.append(apt_dict)
        apartments_out = final_apartments

        await AnalyticsService.log_event(
            "search",
            user_id=user.user_id if user else None,
            metadata={"city": request.city, "tier": tier, "result_count": len(apartments_out)},
        )

        return {
            "apartments": apartments_out,
            "total_results": total_count,
            "page": request.page,
            "has_more": has_more,
            "tier": tier,
            "searches_remaining": searches_remaining,
        }
```

Key changes from current code:
- No `get_top_apartments()` call (no Claude)
- All tiers use the same paginated path
- Free tier counter only incremented on page 1
- Response includes `page` and `has_more`

**Step 2: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(search): use paginated heuristic search for all tiers"
```

---

### Task 4: Add score-batch endpoint

**Files:**
- Modify: `backend/app/main.py` — add new endpoint after search

**Step 1: Add the endpoint**

After the search endpoint (around line 290), add:

```python
@app.post("/api/search/score-batch")
async def score_batch(
    request: ScoreBatchRequest,
    user: UserContext = Depends(get_current_user),
):
    """Score a batch of apartments using Claude AI. Pro only."""
    tier = await TierService.get_user_tier(user.user_id)
    if tier != "pro":
        raise HTTPException(status_code=403, detail="AI scoring requires a Pro subscription.")

    if len(request.apartment_ids) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 apartments per batch.")

    try:
        # Fetch apartment data by IDs
        apartments = await apartment_service.get_apartments_by_ids(request.apartment_ids)
        if not apartments:
            return {"scores": []}

        # Check cache
        ids_key = ",".join(sorted(request.apartment_ids))
        ctx = request.search_context
        raw = f"{ids_key}:{ctx.city}:{ctx.budget}:{ctx.bedrooms}:{ctx.bathrooms}:{ctx.property_type}:{ctx.move_in_date}"
        cache_key = f"score_batch:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

        if apartment_service._redis:
            try:
                cached = await apartment_service._redis.get(cache_key)
                if cached:
                    return {"scores": json.loads(cached)}
            except Exception:
                pass

        # Call Claude
        from app.services.claude_service import ClaudeService
        claude = ClaudeService()

        scores = await asyncio.to_thread(
            claude.score_apartments,
            city=ctx.city,
            budget=ctx.budget,
            bedrooms=ctx.bedrooms,
            bathrooms=ctx.bathrooms,
            property_type=ctx.property_type,
            move_in_date=ctx.move_in_date,
            other_preferences="",
            apartments=apartments,
        )

        # Cache for 1 hour
        if apartment_service._redis:
            try:
                await apartment_service._redis.setex(cache_key, 3600, json.dumps(scores))
            except Exception:
                pass

        return {"scores": scores}

    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"Score batch failed: {e}")
        return {"scores": []}
```

**Step 2: Add `get_apartments_by_ids` helper to apartment service**

In `apartment_service.py`, add after `get_apartments_paginated`:

```python
async def get_apartments_by_ids(self, apartment_ids: List[str]) -> List[Dict]:
    """Fetch apartments by their IDs."""
    if self._use_database:
        from sqlalchemy import select
        from app.models.apartment import ApartmentModel
        async with get_session_context() as session:
            stmt = select(ApartmentModel).where(
                ApartmentModel.id.in_(apartment_ids),
                ApartmentModel.is_active == 1,
            )
            result = await session.execute(stmt)
            return [apt.to_summary_dict() for apt in result.scalars()]
    else:
        if not self._apartments_data:
            self._apartments_data = self._load_apartments_from_json()
        id_set = set(apartment_ids)
        return [apt for apt in self._apartments_data if apt["id"] in id_set]
```

**Step 3: Add necessary imports to main.py**

At the top of main.py, add `ScoreBatchRequest` to the imports from schemas. Also ensure `hashlib`, `json`, `asyncio` are imported.

**Step 4: Commit**

```bash
git add backend/app/main.py backend/app/services/apartment_service.py
git commit -m "feat(api): add score-batch endpoint for async AI scoring"
```

---

### Task 5: Update frontend types and API client

**Files:**
- Modify: `frontend/types/apartment.ts` — `SearchResponse`
- Modify: `frontend/lib/api.ts` — `searchApartments`, add `scoreBatch`

**Step 1: Update SearchResponse type**

In `types/apartment.ts`, update `SearchResponse`:

```typescript
export interface SearchResponse {
  apartments: ApartmentWithScore[];
  total_results: number;
  page: number;
  has_more: boolean;
  tier?: string;
  searches_remaining?: number;
}
```

**Step 2: Add page param to searchApartments**

In `lib/api.ts`, update `searchApartments` to accept page:

```typescript
export async function searchApartments(params: SearchParams & { page?: number }): Promise<SearchResponse> {
```

The body already `JSON.stringify(params)` so `page` will be included when passed.

**Step 3: Add scoreBatch function**

In `lib/api.ts`, add:

```typescript
export async function scoreBatch(
  apartmentIds: string[],
  searchContext: SearchContext & { other_preferences?: string }
): Promise<{ scores: Array<{ apartment_id: string; match_score: number; reasoning: string; highlights: string[] }> }> {
  const response = await fetchWithAuth(`${API_URL}/api/search/score-batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      apartment_ids: apartmentIds,
      search_context: searchContext,
    }),
  })
  if (!response.ok) {
    return { scores: [] }  // Graceful degradation
  }
  return response.json()
}
```

**Step 4: Commit**

```bash
git add frontend/types/apartment.ts frontend/lib/api.ts
git commit -m "feat(frontend): add pagination and score-batch to types and API client"
```

---

### Task 6: Add AI loading skeleton to ApartmentCard

**Files:**
- Modify: `frontend/components/ApartmentCard.tsx`

**Step 1: Add `aiLoading` prop**

Update the interface and destructuring:

```typescript
interface ApartmentCardProps {
  apartment: ApartmentWithScore;
  moveInDate?: string;
  aiLoading?: boolean;
}

export default function ApartmentCard({ apartment, moveInDate, aiLoading }: ApartmentCardProps) {
```

**Step 2: Add skeleton in the AI reasoning section**

Find the AI Reasoning section (after the `<hr>` divider, around line 220). Before the existing `{match_score != null && reasoning ? (` block, add:

```tsx
{/* AI Score Loading Skeleton */}
{aiLoading && (
  <div className="space-y-2 animate-pulse">
    <div className="flex items-center gap-2">
      <div className="h-6 w-16 bg-gray-200 rounded-full" />
      <div className="h-4 w-24 bg-gray-100 rounded" />
    </div>
    <div className="h-3 w-full bg-gray-100 rounded" />
    <div className="h-3 w-3/4 bg-gray-100 rounded" />
  </div>
)}
```

Also update the match score badge in the image overlay to show a skeleton when `aiLoading`:

```tsx
{aiLoading ? (
  <div className="absolute top-3 right-3 bg-gray-300 animate-pulse px-3 py-1 rounded-full w-20 h-7" />
) : match_score != null ? (
  // ... existing score badge
```

Wrap the existing AI reasoning block so it doesn't render when `aiLoading`:

```tsx
{!aiLoading && match_score != null && reasoning ? (
  // ... existing reasoning block
```

**Step 3: Commit**

```bash
git add frontend/components/ApartmentCard.tsx
git commit -m "feat(card): add AI loading skeleton state to ApartmentCard"
```

---

### Task 7: Update search page with pagination and AI backfill

**Files:**
- Modify: `frontend/app/page.tsx`

**Step 1: Add new state variables**

After the existing state declarations (around line 28), add:

```typescript
const [currentPage, setCurrentPage] = useState(1);
const [hasMore, setHasMore] = useState(false);
const [loadingMore, setLoadingMore] = useState(false);
const [aiLoadingIds, setAiLoadingIds] = useState<Set<string>>(new Set());
const [lastSearchParams, setLastSearchParams] = useState<SearchParams | null>(null);
```

**Step 2: Update handleResults to handle pagination and trigger AI backfill**

Replace the simple `handleResults` with a more complete handler. The `SearchForm` `onResults` callback should be replaced with a direct search call from the page:

Add a new function:

```typescript
async function handleSearch(params: SearchParams) {
  setIsLoading(true);
  setError(null);
  setCurrentPage(1);
  setResults([]);
  setLastSearchParams(params);

  try {
    const response = await searchApartments({ ...params, page: 1 });
    setResults(response.apartments);
    setHasSearched(true);
    setHasMore(response.has_more);
    setSearchesRemaining(response.searches_remaining ?? null);
    setMoveInDate(params.move_in_date);

    // Trigger AI backfill for Pro users
    if (isPro && response.apartments.length > 0) {
      const ids = response.apartments.map(a => a.id);
      setAiLoadingIds(new Set(ids));
      scoreBatch(ids, {
        city: params.city,
        budget: params.budget,
        bedrooms: params.bedrooms,
        bathrooms: params.bathrooms,
        property_type: params.property_type,
        move_in_date: params.move_in_date,
        other_preferences: params.other_preferences,
      }).then(({ scores }) => {
        if (scores.length > 0) {
          setResults(prev => prev.map(apt => {
            const score = scores.find(s => s.apartment_id === apt.id);
            return score ? { ...apt, match_score: score.match_score, reasoning: score.reasoning, highlights: score.highlights } : apt;
          }));
        }
        setAiLoadingIds(new Set());
      });
    }
  } catch (err) {
    if (err instanceof ApiError) {
      setError(err.message);
    } else {
      setError('An error occurred while searching');
    }
  } finally {
    setIsLoading(false);
  }
}
```

**Step 3: Add loadMore function**

```typescript
async function handleLoadMore() {
  if (!lastSearchParams || loadingMore) return;
  setLoadingMore(true);

  try {
    const nextPage = currentPage + 1;
    const response = await searchApartments({ ...lastSearchParams, page: nextPage });
    const newApts = response.apartments;
    setResults(prev => [...prev, ...newApts]);
    setCurrentPage(nextPage);
    setHasMore(response.has_more);

    // Trigger AI backfill for Pro users
    if (isPro && newApts.length > 0) {
      const newIds = newApts.map(a => a.id);
      setAiLoadingIds(prev => new Set([...prev, ...newIds]));
      scoreBatch(newIds, {
        city: lastSearchParams.city,
        budget: lastSearchParams.budget,
        bedrooms: lastSearchParams.bedrooms,
        bathrooms: lastSearchParams.bathrooms,
        property_type: lastSearchParams.property_type,
        move_in_date: lastSearchParams.move_in_date,
        other_preferences: lastSearchParams.other_preferences,
      }).then(({ scores }) => {
        if (scores.length > 0) {
          setResults(prev => prev.map(apt => {
            const score = scores.find(s => s.apartment_id === apt.id);
            return score ? { ...apt, match_score: score.match_score, reasoning: score.reasoning, highlights: score.highlights } : apt;
          }));
        }
        setAiLoadingIds(prev => {
          const next = new Set(prev);
          newIds.forEach(id => next.delete(id));
          return next;
        });
      });
    }
  } catch {
    setError('Failed to load more results');
  } finally {
    setLoadingMore(false);
  }
}
```

**Step 4: Update SearchForm to call handleSearch**

Change `SearchForm` to accept an `onSearch` callback instead of `onResults`. Or simpler: keep `onResults` but have the page intercept the search. The easiest approach is to add an `onSearchParams` callback to `SearchForm` that passes the params up, and the page handles the API call.

Alternatively, update `SearchForm` to expose the params via `onSearchMeta` and have the page call `searchApartments` directly. The simplest change: add `onSearch?: (params: SearchParams) => void` to SearchForm props and call it alongside the existing flow.

**Step 5: Pass `aiLoading` prop to ApartmentCard**

In the results grid where `ApartmentCard` is rendered:

```tsx
<ApartmentCard
  key={apartment.id}
  apartment={apartment}
  moveInDate={moveInDate ?? undefined}
  aiLoading={aiLoadingIds.has(apartment.id)}
/>
```

**Step 6: Add "Load More" button after the results grid**

After the results grid `</div>`, before the "No Results" section:

```tsx
{/* Load More */}
{hasMore && !isLoading && (
  <div className="flex justify-center mt-6">
    <button
      onClick={handleLoadMore}
      disabled={loadingMore}
      className="px-6 py-3 bg-[var(--color-primary)] text-white rounded-lg font-medium hover:bg-[var(--color-primary-light)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
    >
      {loadingMore ? (
        <>
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
          Loading...
        </>
      ) : (
        'Load More'
      )}
    </button>
  </div>
)}
```

**Step 7: Update session persistence**

Update the `sessionStorage` save to include pagination state:

```typescript
useEffect(() => {
  if (results.length > 0) {
    sessionStorage.setItem('snugd-search-results', JSON.stringify({
      results, remaining: searchesRemaining, currentPage, hasMore
    }));
  }
}, [results, searchesRemaining, currentPage, hasMore]);
```

And the `loadSessionResults` function at the top:

```typescript
function loadSessionResults(): { results: ApartmentWithScore[]; remaining: number | null; currentPage: number; hasMore: boolean } {
  if (typeof window === 'undefined') return { results: [], remaining: null, currentPage: 1, hasMore: false };
  try {
    const raw = sessionStorage.getItem('snugd-search-results');
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return { results: [], remaining: null, currentPage: 1, hasMore: false };
}
```

Initialize state from session:

```typescript
const [currentPage, setCurrentPage] = useState(() => loadSessionResults().currentPage);
const [hasMore, setHasMore] = useState(() => loadSessionResults().hasMore);
```

**Step 8: Add imports**

Add `scoreBatch` to the imports from `@/lib/api` and `ApiError` if not already imported. Add `SearchParams` to the type imports.

**Step 9: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(search): add Load More pagination with async AI score backfill"
```

---

### Task 8: Write backend tests

**Files:**
- Create: `backend/tests/test_pagination.py`
- Create: `backend/tests/test_score_batch.py`

**Step 1: Write pagination tests**

```python
# tests/test_pagination.py
"""Tests for paginated search endpoint."""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# Mock apartments for pagination
MOCK_APARTMENTS = [
    {"id": f"apt-{i}", "address": f"{i} Main St", "rent": 1000 + i * 100,
     "bedrooms": 1, "bathrooms": 1, "sqft": 500, "property_type": "Apartment",
     "available_date": "", "amenities": [], "neighborhood": "", "description": "",
     "images": [], "city": "Test", "state": "PA", "zip_code": "12345",
     "heuristic_score": 90 - i}
    for i in range(25)
]

@pytest.fixture
def mock_search():
    with patch.object(
        app.state if hasattr(app, 'state') else type('', (), {})(),
        'apartment_service', create=True
    ):
        yield

# Test: page 1 returns first 10
# Test: page 2 returns next 10
# Test: page 3 returns last 5 with has_more=False
# Test: page beyond results returns empty with has_more=False
# Test: free tier counter only incremented on page 1
# Test: response includes page and has_more fields
```

**Step 2: Write score-batch tests**

```python
# tests/test_score_batch.py
"""Tests for score-batch endpoint."""
# Test: Pro user gets AI scores
# Test: Free user gets 403
# Test: More than 10 IDs returns 400
# Test: Claude timeout returns empty scores
# Test: Anonymous user gets 401
```

**Step 3: Commit**

```bash
git add backend/tests/test_pagination.py backend/tests/test_score_batch.py
git commit -m "test: add pagination and score-batch endpoint tests"
```

---

### Task 9: Build verification and integration test

**Step 1: Run backend tests**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
```

**Step 2: Run frontend build**

```bash
cd frontend
npm run build
```

**Step 3: Manual smoke test**

1. Start backend and frontend locally
2. Search for a city — results should appear in ~1 second (no Claude wait)
3. If Pro: score badge should show skeleton, then fill in after a few seconds
4. Click "Load More" — next 10 results appear instantly with skeletons
5. Verify session persistence across tab switches

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: pagination and lazy AI scoring complete"
```
