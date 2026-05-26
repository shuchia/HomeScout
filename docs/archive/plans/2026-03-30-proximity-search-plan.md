# Proximity Search Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let users search for apartments near a specific place (school, hospital, office) with crow-flies distance display for all users and radius filtering for Pro users.

**Architecture:** Frontend geocodes place names via Nominatim, sends lat/lng to backend. Backend calculates Haversine distance for each apartment, appends `distance_miles`, filters by radius (Pro only), and feeds distance data into Claude scoring prompts.

**Tech Stack:** OpenStreetMap Nominatim (geocoding), Haversine formula (Python math), Zustand (state), existing FastAPI + Next.js stack.

**Design doc:** `docs/plans/2026-03-30-proximity-search-design.md`

---

### Task 1: Haversine Utility + Tests

**Files:**
- Create: `backend/app/services/distance.py`
- Create: `backend/tests/test_distance.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_distance.py
"""Tests for Haversine distance calculation."""
import pytest
from app.services.distance import haversine_miles, add_distances


class TestHaversine:
    def test_same_point_returns_zero(self):
        assert haversine_miles(39.95, -75.16, 39.95, -75.16) == 0.0

    def test_known_distance_philly_to_bryn_mawr(self):
        # Philadelphia City Hall to Bryn Mawr (~9.5 miles)
        dist = haversine_miles(39.9526, -75.1635, 40.0210, -75.3162)
        assert 9.0 < dist < 10.5

    def test_short_distance(self):
        # ~1 mile apart
        dist = haversine_miles(39.9526, -75.1635, 39.9670, -75.1635)
        assert 0.5 < dist < 1.5

    def test_returns_float(self):
        result = haversine_miles(40.0, -75.0, 40.1, -75.1)
        assert isinstance(result, float)


class TestAddDistances:
    def test_adds_distance_to_apartments(self):
        apartments = [
            {"id": "a1", "latitude": 39.9526, "longitude": -75.1635},
            {"id": "a2", "latitude": 40.0210, "longitude": -75.3162},
        ]
        result = add_distances(apartments, near_lat=39.95, near_lng=-75.16)
        assert result[0]["distance_miles"] is not None
        assert result[1]["distance_miles"] is not None
        # First apartment is closer
        assert result[0]["distance_miles"] < result[1]["distance_miles"]

    def test_sorts_by_distance(self):
        apartments = [
            {"id": "far", "latitude": 40.5, "longitude": -75.5},
            {"id": "close", "latitude": 39.95, "longitude": -75.16},
        ]
        result = add_distances(apartments, near_lat=39.95, near_lng=-75.16)
        assert result[0]["id"] == "close"
        assert result[1]["id"] == "far"

    def test_missing_coords_placed_last(self):
        apartments = [
            {"id": "no-coords", "latitude": None, "longitude": None},
            {"id": "has-coords", "latitude": 39.95, "longitude": -75.16},
        ]
        result = add_distances(apartments, near_lat=39.95, near_lng=-75.16)
        assert result[0]["id"] == "has-coords"
        assert result[1]["id"] == "no-coords"
        assert result[1]["distance_miles"] is None

    def test_filters_by_max_distance(self):
        apartments = [
            {"id": "close", "latitude": 39.9526, "longitude": -75.1635},
            {"id": "far", "latitude": 40.5, "longitude": -75.5},
        ]
        result = add_distances(apartments, near_lat=39.95, near_lng=-75.16, max_distance_miles=5.0)
        assert len(result) == 1
        assert result[0]["id"] == "close"

    def test_no_filter_when_max_distance_none(self):
        apartments = [
            {"id": "close", "latitude": 39.9526, "longitude": -75.1635},
            {"id": "far", "latitude": 40.5, "longitude": -75.5},
        ]
        result = add_distances(apartments, near_lat=39.95, near_lng=-75.16, max_distance_miles=None)
        assert len(result) == 2

    def test_empty_list(self):
        result = add_distances([], near_lat=39.95, near_lng=-75.16)
        assert result == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_distance.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.distance'`

**Step 3: Write minimal implementation**

```python
# backend/app/services/distance.py
"""Haversine distance calculation for proximity search."""
import math
from typing import List, Dict, Optional


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate crow-flies distance in miles between two lat/lng points."""
    R = 3958.8  # Earth's radius in miles
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def add_distances(
    apartments: List[Dict],
    near_lat: float,
    near_lng: float,
    max_distance_miles: Optional[float] = None,
) -> List[Dict]:
    """Add distance_miles to each apartment, sort by distance, optionally filter.

    Apartments without lat/lng get distance_miles=None and are placed last.
    """
    with_dist = []
    without_coords = []

    for apt in apartments:
        lat = apt.get("latitude")
        lng = apt.get("longitude")
        if lat is not None and lng is not None:
            dist = round(haversine_miles(near_lat, near_lng, lat, lng), 1)
            if max_distance_miles is not None and dist > max_distance_miles:
                continue
            with_dist.append({**apt, "distance_miles": dist})
        else:
            without_coords.append({**apt, "distance_miles": None})

    with_dist.sort(key=lambda x: x["distance_miles"])
    return with_dist + without_coords
```

**Step 4: Run test to verify it passes**

Run: `cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_distance.py -v`
Expected: All 9 tests PASS

**Step 5: Commit**

```bash
git add backend/app/services/distance.py backend/tests/test_distance.py
git commit -m "feat(proximity): add Haversine distance utility with tests"
```

---

### Task 2: Backend Schema + Search Endpoint Changes

**Files:**
- Modify: `backend/app/schemas.py:6-27` (SearchRequest)
- Modify: `backend/app/schemas.py:54-77` (Apartment)
- Modify: `backend/app/schemas.py:116-143` (ApartmentWithScore)
- Modify: `backend/app/schemas.py:146-153` (SearchContext)
- Create: `backend/tests/test_proximity_search.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_proximity_search.py
"""Tests for proximity search integration."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth import get_optional_user, UserContext

client = TestClient(app)

SEARCH_BODY_WITH_PROXIMITY = {
    "city": "Philadelphia, PA",
    "budget": 2000,
    "bedrooms": 1,
    "bathrooms": 1,
    "property_type": "Apartment",
    "move_in_date": "2026-06-01",
    "near_lat": 39.9483,
    "near_lng": -75.1932,
    "near_label": "Children's Hospital of Philadelphia",
}

SAMPLE_APT_CLOSE = {
    "id": "apt-close",
    "address": "100 Close St, Philadelphia, PA",
    "rent": 1800,
    "bedrooms": 1,
    "bathrooms": 1,
    "sqft": 700,
    "property_type": "Apartment",
    "available_date": "2026-05-01",
    "amenities": ["Parking"],
    "neighborhood": "University City",
    "description": "Close apartment",
    "images": ["https://example.com/img.jpg"],
    "latitude": 39.9490,
    "longitude": -75.1940,
}

SAMPLE_APT_FAR = {
    "id": "apt-far",
    "address": "999 Far Ave, Philadelphia, PA",
    "rent": 1500,
    "bedrooms": 1,
    "bathrooms": 1,
    "sqft": 600,
    "property_type": "Apartment",
    "available_date": "2026-05-01",
    "amenities": [],
    "neighborhood": "Northeast",
    "description": "Far apartment",
    "images": ["https://example.com/img2.jpg"],
    "latitude": 40.05,
    "longitude": -75.05,
}


def _mock_free_user():
    return UserContext(user_id="user-free-123", email="free@test.com")


def _mock_pro_user():
    return UserContext(user_id="user-pro-456", email="pro@test.com")


class TestProximitySearchSchema:
    """Test that proximity fields are accepted by the search endpoint."""

    @patch("app.main.apartment_service")
    @patch("app.main.TierService")
    def test_search_accepts_proximity_fields(self, mock_tier, mock_svc):
        """Search endpoint should accept near_lat, near_lng, near_label."""
        app.dependency_overrides[get_optional_user] = _mock_free_user
        mock_tier.get_user_tier = AsyncMock(return_value="free")
        mock_tier.check_search_limit = AsyncMock(return_value=(True, 2))
        mock_tier.increment_search_count = AsyncMock()
        mock_svc.search_apartments = AsyncMock(return_value=[SAMPLE_APT_CLOSE])

        response = client.post("/api/search", json=SEARCH_BODY_WITH_PROXIMITY)
        assert response.status_code == 200
        data = response.json()
        assert len(data["apartments"]) >= 1
        app.dependency_overrides.clear()

    @patch("app.main.apartment_service")
    @patch("app.main.TierService")
    def test_search_returns_distance_miles(self, mock_tier, mock_svc):
        """Results should include distance_miles when near_lat/near_lng provided."""
        app.dependency_overrides[get_optional_user] = _mock_free_user
        mock_tier.get_user_tier = AsyncMock(return_value="free")
        mock_tier.check_search_limit = AsyncMock(return_value=(True, 2))
        mock_tier.increment_search_count = AsyncMock()
        mock_svc.search_apartments = AsyncMock(return_value=[SAMPLE_APT_CLOSE, SAMPLE_APT_FAR])

        response = client.post("/api/search", json=SEARCH_BODY_WITH_PROXIMITY)
        assert response.status_code == 200
        apts = response.json()["apartments"]
        # All apartments should have distance_miles
        for apt in apts:
            assert "distance_miles" in apt
        app.dependency_overrides.clear()

    @patch("app.main.apartment_service")
    @patch("app.main.TierService")
    def test_search_sorted_by_distance(self, mock_tier, mock_svc):
        """Results should be sorted nearest-first when proximity is used."""
        app.dependency_overrides[get_optional_user] = _mock_free_user
        mock_tier.get_user_tier = AsyncMock(return_value="free")
        mock_tier.check_search_limit = AsyncMock(return_value=(True, 2))
        mock_tier.increment_search_count = AsyncMock()
        mock_svc.search_apartments = AsyncMock(return_value=[SAMPLE_APT_FAR, SAMPLE_APT_CLOSE])

        response = client.post("/api/search", json=SEARCH_BODY_WITH_PROXIMITY)
        apts = response.json()["apartments"]
        assert apts[0]["id"] == "apt-close"
        assert apts[1]["id"] == "apt-far"
        app.dependency_overrides.clear()

    @patch("app.main.apartment_service")
    @patch("app.main.TierService")
    def test_max_distance_ignored_for_free(self, mock_tier, mock_svc):
        """Free users sending max_distance_miles should have it silently ignored."""
        app.dependency_overrides[get_optional_user] = _mock_free_user
        mock_tier.get_user_tier = AsyncMock(return_value="free")
        mock_tier.check_search_limit = AsyncMock(return_value=(True, 2))
        mock_tier.increment_search_count = AsyncMock()
        mock_svc.search_apartments = AsyncMock(return_value=[SAMPLE_APT_CLOSE, SAMPLE_APT_FAR])

        body = {**SEARCH_BODY_WITH_PROXIMITY, "max_distance_miles": 1.0}
        response = client.post("/api/search", json=body)
        apts = response.json()["apartments"]
        # Both should be returned (far one not filtered out)
        assert len(apts) == 2
        app.dependency_overrides.clear()

    @patch("app.main.apartment_service")
    @patch("app.main.TierService")
    def test_max_distance_filters_for_pro(self, mock_tier, mock_svc):
        """Pro users with max_distance_miles should get filtered results."""
        app.dependency_overrides[get_optional_user] = _mock_pro_user
        mock_tier.get_user_tier = AsyncMock(return_value="pro")
        mock_svc.search_apartments = AsyncMock(return_value=[SAMPLE_APT_CLOSE, SAMPLE_APT_FAR])
        mock_svc.get_top_apartments = AsyncMock(return_value=([SAMPLE_APT_CLOSE, SAMPLE_APT_FAR], 2))

        body = {**SEARCH_BODY_WITH_PROXIMITY, "max_distance_miles": 1.0}
        response = client.post("/api/search", json=body)
        apts = response.json()["apartments"]
        # Only close apartment within 1 mile radius
        assert len(apts) == 1
        assert apts[0]["id"] == "apt-close"
        app.dependency_overrides.clear()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_proximity_search.py -v`
Expected: FAIL — SearchRequest does not accept `near_lat` etc.

**Step 3: Update schemas.py**

Add to `SearchRequest` (after `other_preferences`):

```python
    # Proximity search (optional)
    near_lat: Optional[float] = Field(None, description="Latitude of reference location")
    near_lng: Optional[float] = Field(None, description="Longitude of reference location")
    near_label: Optional[str] = Field(None, description="Display name of reference location")
    max_distance_miles: Optional[float] = Field(None, ge=0.5, le=10, description="Max distance filter (Pro only)")
```

Add to `Apartment` (after `cost_breakdown`):

```python
    # Proximity (populated when near_lat/near_lng provided in search)
    distance_miles: Optional[float] = None
```

Add to `SearchContext` (after `move_in_date`):

```python
    near_label: Optional[str] = None
```

**Step 4: Update search endpoint in main.py**

In the `search_apartments` function, after getting filtered/scored results and before building `apartments_out`, add distance calculation:

```python
from app.services.distance import add_distances

# After getting results (both pro and free paths), apply proximity:
if request.near_lat is not None and request.near_lng is not None:
    max_dist = request.max_distance_miles if tier == "pro" else None
    results_list = add_distances(results_list, request.near_lat, request.near_lng, max_dist)
```

This requires restructuring the endpoint slightly so both the pro and free paths produce a `results_list` before building `apartments_out`. The key change: apply `add_distances()` to the list of apartment dicts before converting to `ApartmentWithScore`.

**Step 5: Run test to verify it passes**

Run: `cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_proximity_search.py -v`
Expected: All 5 tests PASS

**Step 6: Run existing tests to check for regressions**

Run: `cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_search_gating.py tests/test_compare_gating.py -v`
Expected: All existing tests PASS (new optional fields shouldn't break anything)

**Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/main.py backend/tests/test_proximity_search.py
git commit -m "feat(proximity): add proximity fields to search schema and endpoint"
```

---

### Task 3: Claude Scoring Prompt Integration

**Files:**
- Modify: `backend/app/services/claude_service.py:20-55` (prepare_apartment_for_scoring)
- Modify: `backend/app/services/claude_service.py:57-125` (score_apartments)
- Modify: `backend/app/services/apartment_service.py:219-330` (get_top_apartments)

**Step 1: Update `prepare_apartment_for_scoring` in claude_service.py**

Add `distance_miles` to the scoring data dict (after `heuristic_score`):

```python
        # Include distance if available
        if apt.get("distance_miles") is not None:
            data["distance_miles"] = apt["distance_miles"]
```

**Step 2: Update `score_apartments` to accept proximity context**

Add `near_label` parameter to `score_apartments()`:

```python
    def score_apartments(
        self,
        city: str,
        budget: int,
        bedrooms: int,
        bathrooms: int,
        property_type: str,
        move_in_date: str,
        other_preferences: str,
        apartments: List[Dict],
        near_label: str = None,  # NEW
    ) -> List[Dict]:
```

In the user prompt, after `**Additional Preferences:**`, add:

```python
        proximity_section = ""
        if near_label:
            proximity_section = f"\n**Near:** {near_label}\n"
            distances = []
            for apt in slim_apartments:
                dist = apt.get("distance_miles")
                if dist is not None:
                    distances.append(f"- {apt['address']}: {dist} miles away")
            if distances:
                proximity_section += "Distances from reference location:\n" + "\n".join(distances) + "\n"

        user_prompt = f"""...
**Additional Preferences:**
{other_preferences if other_preferences else "None specified"}
{proximity_section}
---
...
"""
```

**Step 3: Update `get_top_apartments` in apartment_service.py**

Pass `near_label` through to `claude_service.score_apartments()`:

```python
    async def get_top_apartments(
        self,
        ...
        other_preferences: str = None,
        near_label: str = None,  # NEW
        top_n: int = 10
    ) -> Tuple[List[Dict], int]:
```

And in the Claude call:

```python
            scores = await asyncio.to_thread(
                self.claude_service.score_apartments,
                ...
                other_preferences=other_preferences or "None specified",
                apartments=apartments_to_score,
                near_label=near_label,  # NEW
            )
```

Also update `build_score_cache_key` to include `near_label` so proximity changes bust the cache.

**Step 4: Update the search endpoint call in main.py**

Pass `near_label` to `get_top_apartments`:

```python
            top_apartments, total_count = await apartment_service.get_top_apartments(
                ...
                other_preferences=request.other_preferences,
                near_label=request.near_label,  # NEW
                top_n=10,
            )
```

**Step 5: Run all backend tests**

Run: `cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add backend/app/services/claude_service.py backend/app/services/apartment_service.py backend/app/main.py
git commit -m "feat(proximity): feed distance data into Claude scoring prompt"
```

---

### Task 4: Frontend Types + Geocode Utility

**Files:**
- Modify: `frontend/types/apartment.ts:10-18` (SearchParams)
- Modify: `frontend/types/apartment.ts:52-74` (Apartment)
- Modify: `frontend/types/apartment.ts:110-117` (SearchContext)
- Create: `frontend/lib/geocode.ts`

**Step 1: Update TypeScript types**

In `types/apartment.ts`, add to `SearchParams`:

```typescript
export interface SearchParams {
  city: string;
  budget: number;
  bedrooms: number;
  bathrooms: number;
  property_type: string;
  move_in_date: string;
  other_preferences?: string;
  // Proximity search
  near_lat?: number;
  near_lng?: number;
  near_label?: string;
  max_distance_miles?: number;
}
```

Add to `Apartment`:

```typescript
  distance_miles?: number | null;
```

Add to `SearchContext`:

```typescript
export interface SearchContext {
  city: string;
  budget: number;
  bedrooms: number;
  bathrooms: number;
  property_type: string;
  move_in_date: string;
  near_label?: string;
}
```

**Step 2: Create geocode utility**

```typescript
// frontend/lib/geocode.ts

export interface GeocodeSuggestion {
  display_name: string
  lat: number
  lng: number
}

const NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'

let lastRequestTime = 0

export async function geocodeSearch(query: string): Promise<GeocodeSuggestion[]> {
  if (!query || query.length < 3) return []

  // Respect Nominatim 1 req/sec rate limit
  const now = Date.now()
  const elapsed = now - lastRequestTime
  if (elapsed < 1000) {
    await new Promise((resolve) => setTimeout(resolve, 1000 - elapsed))
  }
  lastRequestTime = Date.now()

  const params = new URLSearchParams({
    q: query,
    format: 'json',
    limit: '5',
    countrycodes: 'us',
  })

  const response = await fetch(`${NOMINATIM_URL}?${params}`, {
    headers: {
      'User-Agent': 'Snugd/1.0 (https://snugd.ai)',
    },
  })

  if (!response.ok) return []

  const data = await response.json()
  return data.map((item: { display_name: string; lat: string; lon: string }) => ({
    display_name: item.display_name,
    lat: parseFloat(item.lat),
    lng: parseFloat(item.lon),
  }))
}
```

**Step 3: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds (no type errors from new optional fields)

**Step 4: Commit**

```bash
git add frontend/types/apartment.ts frontend/lib/geocode.ts
git commit -m "feat(proximity): add proximity types and Nominatim geocode utility"
```

---

### Task 5: NearLocationInput Component

**Files:**
- Create: `frontend/components/NearLocationInput.tsx`

**Step 1: Create the component**

```tsx
// frontend/components/NearLocationInput.tsx
'use client'

import { useState, useRef, useCallback, useEffect } from 'react'
import { geocodeSearch, GeocodeSuggestion } from '@/lib/geocode'

interface NearLocation {
  lat: number
  lng: number
  label: string
}

interface NearLocationInputProps {
  value: NearLocation | null
  onChange: (location: NearLocation | null) => void
}

export default function NearLocationInput({ value, onChange }: NearLocationInputProps) {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<GeocodeSuggestion[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [showDropdown, setShowDropdown] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const handleSearch = useCallback((text: string) => {
    setQuery(text)
    if (debounceRef.current) clearTimeout(debounceRef.current)

    if (text.length < 3) {
      setSuggestions([])
      setShowDropdown(false)
      return
    }

    debounceRef.current = setTimeout(async () => {
      setIsLoading(true)
      try {
        const results = await geocodeSearch(text)
        setSuggestions(results)
        setShowDropdown(results.length > 0)
      } finally {
        setIsLoading(false)
      }
    }, 500)
  }, [])

  const handleSelect = (suggestion: GeocodeSuggestion) => {
    // Use first part of display_name as short label
    const label = suggestion.display_name.split(',').slice(0, 2).join(',').trim()
    onChange({ lat: suggestion.lat, lng: suggestion.lng, label })
    setQuery(label)
    setShowDropdown(false)
    setSuggestions([])
  }

  const handleClear = () => {
    onChange(null)
    setQuery('')
    setSuggestions([])
    setShowDropdown(false)
  }

  return (
    <div ref={containerRef} className="relative">
      <label className="block text-sm font-medium text-gray-700 mb-1">
        Near <span className="text-gray-400 font-normal">(optional)</span>
      </label>
      <div className="relative">
        <input
          type="text"
          value={value ? value.label : query}
          onChange={(e) => {
            if (value) onChange(null)
            handleSearch(e.target.value)
          }}
          placeholder="e.g. Children's Hospital of Philadelphia"
          className="w-full border border-gray-300 rounded-lg px-3 py-2 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent"
        />
        {isLoading && (
          <div className="absolute right-8 top-1/2 -translate-y-1/2">
            <svg className="h-4 w-4 animate-spin text-gray-400" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          </div>
        )}
        {(value || query) && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            aria-label="Clear location"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>
      {showDropdown && suggestions.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
          {suggestions.map((s, i) => (
            <li key={i}>
              <button
                type="button"
                onClick={() => handleSelect(s)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 border-b border-gray-100 last:border-0"
              >
                {s.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

**Step 2: Verify it builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 3: Commit**

```bash
git add frontend/components/NearLocationInput.tsx
git commit -m "feat(proximity): add NearLocationInput component with Nominatim autocomplete"
```

---

### Task 6: RadiusSlider Component

**Files:**
- Create: `frontend/components/RadiusSlider.tsx`

**Step 1: Create the component**

```tsx
// frontend/components/RadiusSlider.tsx
'use client'

import Link from 'next/link'

interface RadiusSliderProps {
  value: number
  onChange: (value: number) => void
  isPro: boolean
}

export default function RadiusSlider({ value, onChange, isPro }: RadiusSliderProps) {
  return (
    <div className="relative">
      <div className="flex items-center justify-between mb-1">
        <label className="text-sm font-medium text-gray-700">
          Max Distance
        </label>
        <span className="text-sm text-gray-500">
          Within {value} mi
        </span>
      </div>
      <div className="relative">
        <input
          type="range"
          min={0.5}
          max={10}
          step={0.5}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          disabled={!isPro}
          className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-[var(--color-primary)] disabled:opacity-50 disabled:cursor-not-allowed"
        />
        {!isPro && (
          <Link
            href="/pricing"
            className="absolute -top-1 right-0 inline-flex items-center gap-1 bg-amber-100 text-amber-700 text-xs font-medium px-2 py-0.5 rounded-full hover:bg-amber-200 transition-colors"
          >
            Pro
          </Link>
        )}
      </div>
    </div>
  )
}
```

**Step 2: Verify it builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 3: Commit**

```bash
git add frontend/components/RadiusSlider.tsx
git commit -m "feat(proximity): add RadiusSlider component with Pro gating"
```

---

### Task 7: Wire Components into SearchForm

**Files:**
- Modify: `frontend/components/SearchForm.tsx`
- Modify: `frontend/hooks/useComparison.ts`

**Step 1: Update SearchForm**

Add imports at top:

```tsx
import NearLocationInput from './NearLocationInput'
import RadiusSlider from './RadiusSlider'
import { useAuth } from '@/contexts/AuthContext'
```

Add state variables (after `otherPreferences` state):

```tsx
  const [nearLocation, setNearLocation] = useState<{ lat: number; lng: number; label: string } | null>(null)
  const [maxDistance, setMaxDistance] = useState(5)
  const { isPro } = useAuth()
```

In the form JSX, after the city `<select>` and before the budget input, add:

```tsx
        {/* Near location */}
        <NearLocationInput value={nearLocation} onChange={setNearLocation} />

        {/* Radius slider (shown only when location is set) */}
        {nearLocation && (
          <RadiusSlider value={maxDistance} onChange={setMaxDistance} isPro={isPro} />
        )}
```

In `handleSubmit`, update the `params` object:

```tsx
      const params: SearchParams = {
        city: city.trim(),
        budget,
        bedrooms,
        bathrooms,
        property_type: selectedPropertyTypes.join(', '),
        move_in_date: moveInDate,
        other_preferences: otherPreferences.trim() || undefined,
        near_lat: nearLocation?.lat,
        near_lng: nearLocation?.lng,
        near_label: nearLocation?.label,
        max_distance_miles: nearLocation && isPro ? maxDistance : undefined,
      };
```

Update `setSearchContext` call to include `near_label`:

```tsx
      setSearchContext({
        city: city.trim(),
        budget,
        bedrooms,
        bathrooms,
        property_type: selectedPropertyTypes.join(', '),
        move_in_date: moveInDate,
        other_preferences: otherPreferences.trim() || '',
        near_label: nearLocation?.label,
      });
```

**Step 2: Update useComparison.ts**

Add `near_label` to the `SearchContext` interface:

```typescript
interface SearchContext {
  city: string
  budget: number
  bedrooms: number
  bathrooms: number
  property_type: string
  move_in_date: string
  other_preferences: string
  near_label?: string
}
```

**Step 3: Verify it builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add frontend/components/SearchForm.tsx frontend/hooks/useComparison.ts
git commit -m "feat(proximity): wire NearLocationInput and RadiusSlider into SearchForm"
```

---

### Task 8: Distance Display on ApartmentCard

**Files:**
- Modify: `frontend/components/ApartmentCard.tsx`

**Step 1: Add distance display**

In the destructured props (around line 57-75), add:

```tsx
    const { ...existing props..., distance_miles } = apartment as ApartmentWithScore & { distance_miles?: number | null };
```

In the JSX, after the address line and before the rent/details section, add:

```tsx
        {distance_miles != null && (
          <p className="text-xs text-gray-500 mt-0.5 flex items-center gap-1">
            <svg className="h-3 w-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            {distance_miles} mi away
          </p>
        )}
```

**Step 2: Verify it builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 3: Commit**

```bash
git add frontend/components/ApartmentCard.tsx
git commit -m "feat(proximity): show distance on ApartmentCard when available"
```

---

### Task 9: Distance Row in Compare Page

**Files:**
- Modify: `frontend/app/compare/page.tsx`

**Step 1: Add Distance row to comparison table**

Find the comparison table section (where rows like Rent, Bedrooms, Bathrooms are rendered). After the existing rows, add a conditional Distance row:

```tsx
        {searchContext?.near_label && (
          <tr>
            <td className="px-4 py-3 font-medium text-gray-600 bg-gray-50">Distance</td>
            {apartments.map((apt) => (
              <td key={`dist-${apt.id}`} className="px-4 py-3 text-center">
                {(apt as Apartment & { distance_miles?: number | null }).distance_miles != null
                  ? `${(apt as Apartment & { distance_miles?: number | null }).distance_miles} mi`
                  : '—'}
              </td>
            ))}
          </tr>
        )}
```

**Step 2: Verify it builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 3: Commit**

```bash
git add frontend/app/compare/page.tsx
git commit -m "feat(proximity): add distance row to comparison table"
```

---

### Task 10: Full Integration Test + Final Verification

**Files:**
- All files from previous tasks

**Step 1: Run all backend tests**

Run: `cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v`
Expected: All tests PASS (including new proximity tests)

**Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors

**Step 3: Run frontend lint**

Run: `cd frontend && npm run lint`
Expected: No lint errors

**Step 4: Run E2E tests (if available)**

Run: `cd frontend && npx playwright test`
Expected: Existing tests still pass

**Step 5: Final commit with any fixes**

If any fixes were needed, commit them:

```bash
git add -A
git commit -m "fix(proximity): address test/build issues from integration"
```

**Step 6: Update CLAUDE.md**

Add proximity search to the Key Flow: Search section and the API Endpoints table. Mention `near_lat`, `near_lng`, `near_label`, `max_distance_miles` as optional search params.

```bash
git add CLAUDE.md
git commit -m "docs: add proximity search to CLAUDE.md"
```
