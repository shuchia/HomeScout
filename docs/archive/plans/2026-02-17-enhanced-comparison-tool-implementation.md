# Enhanced Comparison Tool Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire up the compare page's Score button to perform a Claude-powered head-to-head apartment analysis with category breakdowns, winner selection, and search context integration.

**Architecture:** The backend adds a new Claude service method (`compare_apartments_with_analysis`) called from the existing `/api/apartments/compare` endpoint when preferences are provided. The frontend extends the Zustand comparison store with search context, pre-fills the compare page preferences input, and renders a winner summary card and category scores grid after scoring.

**Tech Stack:** FastAPI + Pydantic (backend), Next.js + React + Zustand + Tailwind CSS (frontend), Claude API (Anthropic SDK), pytest + httpx (backend tests), Playwright (E2E tests)

---

### Task 1: Add Backend Pydantic Models

**Files:**
- Modify: `backend/app/schemas.py:138-167`

**Step 1: Add the new models to schemas.py**

Add these models after the `ApartmentWithScore` class (before `SearchResponse`):

```python
class SearchContext(BaseModel):
    """Search criteria context for comparison scoring."""
    city: str
    budget: int
    bedrooms: int
    bathrooms: int
    property_type: str
    move_in_date: str


class CategoryScore(BaseModel):
    """Score and note for a single comparison category."""
    score: int = Field(..., ge=0, le=100)
    note: str


class ApartmentComparisonScore(BaseModel):
    """Detailed comparison scoring for one apartment."""
    apartment_id: str
    overall_score: int = Field(..., ge=0, le=100)
    reasoning: str
    highlights: List[str]
    category_scores: dict[str, CategoryScore]


class ComparisonWinner(BaseModel):
    """The winning apartment and why."""
    apartment_id: str
    reason: str


class ComparisonAnalysis(BaseModel):
    """Full comparison analysis returned by Claude."""
    winner: ComparisonWinner
    categories: List[str]
    apartment_scores: List[ApartmentComparisonScore]
```

**Step 2: Update CompareRequest to accept search_context**

Replace the existing `CompareRequest`:

```python
class CompareRequest(BaseModel):
    """Request model for apartment comparison."""
    apartment_ids: List[str] = Field(..., max_length=3)
    preferences: Optional[str] = Field(None, description="User preferences for scoring")
    search_context: Optional[SearchContext] = Field(None, description="Original search criteria")
```

**Step 3: Update CompareResponse to include comparison_analysis**

Replace the existing `CompareResponse`:

```python
class CompareResponse(BaseModel):
    """Response model for apartment comparison."""
    apartments: List[Apartment]
    comparison_fields: List[str]
    comparison_analysis: Optional[ComparisonAnalysis] = None
```

**Step 4: Run existing tests to verify nothing is broken**

Run: `cd backend && python -m pytest tests/test_apartments_router.py -v`
Expected: All 8 tests PASS (the new fields are optional, so existing tests still work)

**Step 5: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat: add Pydantic models for comparison analysis"
```

---

### Task 2: Add Backend Comparison Tests

**Files:**
- Modify: `backend/tests/test_apartments_router.py`

**Step 1: Write the failing test for compare with preferences**

Add to the bottom of `test_apartments_router.py`:

```python
@pytest.mark.asyncio
async def test_compare_apartments_with_preferences():
    """Test comparison with preferences triggers analysis."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/apartments/compare",
            json={
                "apartment_ids": ["apt-001", "apt-002"],
                "preferences": "parking, quiet neighborhood",
                "search_context": {
                    "city": "Bryn Mawr, PA",
                    "budget": 2000,
                    "bedrooms": 1,
                    "bathrooms": 1,
                    "property_type": "Apartment",
                    "move_in_date": "2026-03-01"
                }
            }
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data["apartments"]) == 2
    assert "comparison_analysis" in data
    analysis = data["comparison_analysis"]
    assert "winner" in analysis
    assert analysis["winner"]["apartment_id"] in ["apt-001", "apt-002"]
    assert "reason" in analysis["winner"]
    assert "categories" in analysis
    assert len(analysis["categories"]) >= 3  # At least Value, Space, Amenities
    assert "apartment_scores" in analysis
    assert len(analysis["apartment_scores"]) == 2
    for score in analysis["apartment_scores"]:
        assert "overall_score" in score
        assert 0 <= score["overall_score"] <= 100
        assert "category_scores" in score
        for cat in analysis["categories"]:
            assert cat in score["category_scores"]


@pytest.mark.asyncio
async def test_compare_apartments_without_preferences_no_analysis():
    """Test comparison without preferences returns no analysis."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/apartments/compare",
            json={"apartment_ids": ["apt-001", "apt-002"]}
        )
    assert response.status_code == 200
    data = response.json()
    assert data.get("comparison_analysis") is None
```

**Step 2: Run to verify the preference test fails**

Run: `cd backend && python -m pytest tests/test_apartments_router.py::test_compare_apartments_with_preferences -v`
Expected: FAIL — `comparison_analysis` is not in response (endpoint doesn't call Claude yet)

**Step 3: Commit**

```bash
git add backend/tests/test_apartments_router.py
git commit -m "test: add comparison analysis endpoint tests"
```

---

### Task 3: Add Claude Comparison Method

**Files:**
- Modify: `backend/app/services/claude_service.py`

**Step 1: Add `compare_apartments_with_analysis()` method**

Add this method to the `ClaudeService` class after `score_apartments()`:

```python
def compare_apartments_with_analysis(
    self,
    apartments: List[Dict],
    preferences: str,
    search_context: Optional[Dict] = None,
) -> Dict:
    """
    Deep head-to-head comparison of 2-3 apartments.

    Returns dict with winner, categories, and per-apartment scores.
    """
    # Slim apartment data (same approach as score_apartments)
    slim_apartments = []
    for apt in apartments:
        slim_apt = {
            "id": apt["id"],
            "address": apt.get("address", ""),
            "rent": apt.get("rent", 0),
            "bedrooms": apt.get("bedrooms", 0),
            "bathrooms": apt.get("bathrooms", 0),
            "sqft": apt.get("sqft", 0),
            "property_type": apt.get("property_type", ""),
            "available_date": apt.get("available_date", ""),
            "neighborhood": apt.get("neighborhood", ""),
            "description": (apt.get("description", "") or "")[:300],
            "amenities": (apt.get("amenities", []) or [])[:15],
        }
        slim_apartments.append(slim_apt)

    apartments_json = json.dumps(slim_apartments, indent=2)

    # Build search context section
    context_section = ""
    if search_context:
        context_section = f"""## Original Search Criteria
City: {search_context.get('city', 'N/A')} | Budget: ${search_context.get('budget', 'N/A')}/mo | Bedrooms: {search_context.get('bedrooms', 'N/A')} | Bathrooms: {search_context.get('bathrooms', 'N/A')} | Type: {search_context.get('property_type', 'N/A')} | Move-in: {search_context.get('move_in_date', 'N/A')}

"""

    user_prompt = f"""{context_section}## What Matters Most to This User
{preferences}

## Apartments to Compare
{apartments_json}

Compare these apartments across categories. Always include Value, Space & Layout, and Amenities as standard categories. Add 1-3 custom categories based on what matters most to this user. Score each apartment 0-100 per category. Pick an overall winner.

Return a JSON object with this exact structure:
{{
  "winner": {{
    "apartment_id": "the-winning-id",
    "reason": "1-2 sentence explanation of why this apartment wins overall"
  }},
  "categories": ["Value", "Space & Layout", "Amenities", ...custom categories],
  "apartment_scores": [
    {{
      "apartment_id": "id",
      "overall_score": 85,
      "reasoning": "1-2 sentence overall assessment",
      "highlights": ["highlight 1", "highlight 2"],
      "category_scores": {{
        "Value": {{"score": 80, "note": "brief note"}},
        "Space & Layout": {{"score": 75, "note": "brief note"}},
        ...one entry per category
      }}
    }}
  ]
}}

Return valid JSON only, no additional text."""

    system_prompt = """You are an expert apartment comparison analyst for HomeScout. Compare apartments head-to-head across multiple categories, considering the user's stated preferences and search criteria. Be specific and practical in your analysis. Scores should reflect genuine differences — don't give similar scores unless apartments are truly comparable in that category."""

    try:
        message = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        response_text = message.content[0].text
        result = self._parse_comparison_response(response_text)
        return result

    except Exception as e:
        print(f"Error calling Claude API for comparison: {str(e)}")
        raise
```

**Step 2: Add the comparison response parser**

Add this method after `_parse_json_response()`:

```python
def _parse_comparison_response(self, response_text: str) -> Dict:
    """Parse the comparison analysis JSON from Claude's response."""
    # Strip markdown code blocks if present
    if "```json" in response_text:
        json_start = response_text.find("```json") + 7
        json_end = response_text.find("```", json_start)
        response_text = response_text[json_start:json_end].strip()
    elif "```" in response_text:
        json_start = response_text.find("```") + 3
        json_end = response_text.find("```", json_start)
        response_text = response_text[json_start:json_end].strip()

    result = json.loads(response_text)

    # Validate required top-level fields
    for field in ["winner", "categories", "apartment_scores"]:
        if field not in result:
            raise ValueError(f"Missing required field: {field}")

    return result
```

**Step 3: Commit**

```bash
git add backend/app/services/claude_service.py
git commit -m "feat: add Claude comparison analysis method"
```

---

### Task 4: Wire Up the Compare Endpoint

**Files:**
- Modify: `backend/app/routers/apartments.py:208-239`

**Step 1: Update the compare endpoint to call Claude when preferences are provided**

Replace the `compare_apartments` function:

```python
@router.post("/compare", response_model=CompareResponse)
async def compare_apartments(request: CompareRequest) -> CompareResponse:
    """
    Compare up to 3 apartments with optional preference scoring.
    When preferences are provided, Claude performs a deep head-to-head analysis.
    """
    comparison_fields = [
        "rent", "bedrooms", "bathrooms", "sqft",
        "property_type", "amenities", "available_date", "neighborhood"
    ]

    if not request.apartment_ids:
        return CompareResponse(apartments=[], comparison_fields=comparison_fields)

    # Fetch apartments
    apartments_data = _get_apartments_data()
    apt_map = {apt.get("id"): apt for apt in apartments_data}

    apartments = []
    for aid in request.apartment_ids:
        if aid in apt_map:
            apartments.append(apt_map[aid])

    # If preferences provided, run Claude comparison analysis
    comparison_analysis = None
    if request.preferences and request.preferences.strip() and len(apartments) >= 2:
        import asyncio
        from app.services.claude_service import ClaudeService

        claude = ClaudeService()
        search_ctx = request.search_context.model_dump() if request.search_context else None

        try:
            raw_analysis = await asyncio.to_thread(
                claude.compare_apartments_with_analysis,
                apartments=apartments,
                preferences=request.preferences,
                search_context=search_ctx,
            )
            # Import and construct the Pydantic model
            from app.schemas import ComparisonAnalysis
            comparison_analysis = ComparisonAnalysis(**raw_analysis)
        except Exception as e:
            logger.error(f"Claude comparison analysis failed: {e}")
            # Return apartments without analysis on failure

    return CompareResponse(
        apartments=apartments,
        comparison_fields=comparison_fields,
        comparison_analysis=comparison_analysis,
    )
```

**Step 2: Run the tests**

Run: `cd backend && python -m pytest tests/test_apartments_router.py -v`
Expected: All tests PASS including `test_compare_apartments_with_preferences` (requires ANTHROPIC_API_KEY set)

Note: If the API key is not available in CI, the test may need to be marked with `@pytest.mark.skipif` — but for local development it should pass.

**Step 3: Commit**

```bash
git add backend/app/routers/apartments.py
git commit -m "feat: wire compare endpoint to Claude analysis"
```

---

### Task 5: Add Frontend TypeScript Types

**Files:**
- Modify: `frontend/types/apartment.ts`

**Step 1: Add the comparison analysis interfaces**

Append to `types/apartment.ts`:

```typescript
/**
 * Search context passed from search page to compare page
 */
export interface SearchContext {
  city: string;
  budget: number;
  bedrooms: number;
  bathrooms: number;
  property_type: string;
  move_in_date: string;
}

/**
 * Score and note for a single comparison category
 */
export interface CategoryScore {
  score: number;
  note: string;
}

/**
 * Detailed comparison scoring for one apartment
 */
export interface ApartmentComparisonScore {
  apartment_id: string;
  overall_score: number;
  reasoning: string;
  highlights: string[];
  category_scores: Record<string, CategoryScore>;
}

/**
 * The winning apartment and why
 */
export interface ComparisonWinner {
  apartment_id: string;
  reason: string;
}

/**
 * Full comparison analysis returned by Claude
 */
export interface ComparisonAnalysis {
  winner: ComparisonWinner;
  categories: string[];
  apartment_scores: ApartmentComparisonScore[];
}
```

**Step 2: Commit**

```bash
git add frontend/types/apartment.ts
git commit -m "feat: add TypeScript interfaces for comparison analysis"
```

---

### Task 6: Update Frontend API Client

**Files:**
- Modify: `frontend/lib/api.ts:168-221`

**Step 1: Update the CompareResponse interface**

Replace the existing `CompareResponse` interface in `api.ts`:

```typescript
/**
 * Response from the compare API endpoint
 */
export interface CompareResponse {
  apartments: ApartmentWithScore[];
  comparison_fields: string[];
  comparison_analysis?: ComparisonAnalysis;
}
```

Add `ComparisonAnalysis` and `SearchContext` to the import from `types/apartment`:

```typescript
import { SearchParams, SearchResponse, HealthResponse, Apartment, ApartmentWithScore, SearchContext, ComparisonAnalysis } from '@/types/apartment';
```

**Step 2: Update the compareApartments function signature**

Replace the existing `compareApartments` function:

```typescript
/**
 * Compare apartments side-by-side with optional AI scoring
 * Calls POST /api/apartments/compare endpoint
 */
export async function compareApartments(
  apartmentIds: string[],
  preferences?: string,
  searchContext?: SearchContext
): Promise<CompareResponse> {
  try {
    const response = await fetch(`${API_URL}/api/apartments/compare`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        apartment_ids: apartmentIds,
        preferences: preferences || null,
        search_context: searchContext || null,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || 'Failed to compare apartments',
        response.status,
        JSON.stringify(errorData)
      );
    }

    return response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      'Unable to connect to the server',
      undefined,
      error instanceof Error ? error.message : 'Unknown error'
    );
  }
}
```

**Step 3: Commit**

```bash
git add frontend/lib/api.ts frontend/types/apartment.ts
git commit -m "feat: update API client for comparison analysis"
```

---

### Task 7: Extend Zustand Comparison Store with Search Context

**Files:**
- Modify: `frontend/hooks/useComparison.ts`

**Step 1: Add searchContext to the store**

Replace the full content of `useComparison.ts`:

```typescript
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

interface SearchContext {
  city: string
  budget: number
  bedrooms: number
  bathrooms: number
  property_type: string
  move_in_date: string
  other_preferences: string
}

interface ComparisonStore {
  apartmentIds: string[]
  searchContext: SearchContext | null
  addToCompare: (id: string) => void
  removeFromCompare: (id: string) => void
  clearComparison: () => void
  isInComparison: (id: string) => boolean
  setSearchContext: (ctx: SearchContext) => void
}

const useComparisonStore = create(
  persist<ComparisonStore>(
    (set, get) => ({
      apartmentIds: [],
      searchContext: null,

      addToCompare: (id) => {
        const current = get().apartmentIds
        if (current.length < 3 && !current.includes(id)) {
          set({ apartmentIds: [...current, id] })
        }
      },

      removeFromCompare: (id) => {
        set({ apartmentIds: get().apartmentIds.filter(i => i !== id) })
      },

      clearComparison: () => set({ apartmentIds: [], searchContext: null }),

      isInComparison: (id) => get().apartmentIds.includes(id),

      setSearchContext: (ctx) => set({ searchContext: ctx }),
    }),
    {
      name: 'homescout-comparison',
      storage: createJSONStorage(() => localStorage),
    }
  )
)

export { useComparisonStore as useComparison }
```

**Step 2: Commit**

```bash
git add frontend/hooks/useComparison.ts
git commit -m "feat: add searchContext to comparison store"
```

---

### Task 8: Save Search Context from SearchForm

**Files:**
- Modify: `frontend/components/SearchForm.tsx:59-99`

**Step 1: Import and use the comparison store**

Add import at the top of `SearchForm.tsx`:

```typescript
import { useComparison } from '@/hooks/useComparison';
```

**Step 2: Call setSearchContext on successful search**

Inside the `SearchForm` component, add:

```typescript
const { setSearchContext } = useComparison();
```

Then in `handleSubmit`, after the successful `searchApartments` call (after `onResults(response.apartments)`), add:

```typescript
// Save search context for comparison page
setSearchContext({
  city: city.trim(),
  budget,
  bedrooms,
  bathrooms,
  property_type: selectedPropertyTypes.join(', '),
  move_in_date: moveInDate,
  other_preferences: otherPreferences.trim(),
});
```

**Step 3: Commit**

```bash
git add frontend/components/SearchForm.tsx
git commit -m "feat: save search context on search submission"
```

---

### Task 9: Rebuild Compare Page with Analysis UI

**Files:**
- Modify: `frontend/app/compare/page.tsx` (full rewrite)

This is the largest task. The compare page needs:
- Auth gate (sign-in required)
- Preferences pre-fill from search context
- Score button that sends preferences + search context to backend
- Winner summary card (appears after scoring)
- Category scores grid (appears after scoring)
- Enhanced comparison table with overall score row

**Step 1: Replace the full compare page**

Replace the entire content of `frontend/app/compare/page.tsx`:

```tsx
'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Image from 'next/image'
import { useComparison } from '@/hooks/useComparison'
import { useAuth } from '@/contexts/AuthContext'
import { compareApartments, ApiError, CompareResponse } from '@/lib/api'
import { Apartment, ComparisonAnalysis, SearchContext } from '@/types/apartment'

const formatRent = (rent: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(rent)

const formatSqft = (sqft: number): string =>
  new Intl.NumberFormat('en-US').format(sqft)

const getScoreColor = (score: number): string => {
  if (score >= 85) return 'bg-green-500'
  if (score >= 70) return 'bg-blue-500'
  if (score >= 50) return 'bg-yellow-500'
  return 'bg-gray-500'
}

const getScoreTextColor = (score: number): string => {
  if (score >= 85) return 'text-green-700'
  if (score >= 70) return 'text-blue-700'
  if (score >= 50) return 'text-yellow-700'
  return 'text-gray-700'
}

export default function ComparePage() {
  const router = useRouter()
  const { user, loading: authLoading, signInWithGoogle } = useAuth()
  const { apartmentIds, removeFromCompare, clearComparison, searchContext } = useComparison()

  const [apartments, setApartments] = useState<Apartment[]>([])
  const [loading, setLoading] = useState(true)
  const [scoring, setScoring] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [preferences, setPreferences] = useState('')
  const [analysis, setAnalysis] = useState<ComparisonAnalysis | null>(null)

  // Pre-fill preferences from search context
  useEffect(() => {
    if (searchContext?.other_preferences) {
      setPreferences(searchContext.other_preferences)
    }
  }, [searchContext])

  // Load apartments when page loads or IDs change
  useEffect(() => {
    async function loadApartments() {
      if (apartmentIds.length < 2) {
        setLoading(false)
        return
      }

      setLoading(true)
      setError(null)

      try {
        const response = await compareApartments(apartmentIds)
        setApartments(response.apartments)
      } catch (err) {
        if (err instanceof ApiError) {
          setError(err.message)
        } else {
          setError('Failed to load apartments')
        }
      } finally {
        setLoading(false)
      }
    }

    loadApartments()
  }, [apartmentIds])

  // Handle scoring with preferences
  const handleScore = async () => {
    if (!preferences.trim()) return

    setScoring(true)
    setError(null)

    try {
      // Build search context for API (without other_preferences which is sent separately)
      const apiSearchContext: SearchContext | undefined = searchContext
        ? {
            city: searchContext.city,
            budget: searchContext.budget,
            bedrooms: searchContext.bedrooms,
            bathrooms: searchContext.bathrooms,
            property_type: searchContext.property_type,
            move_in_date: searchContext.move_in_date,
          }
        : undefined

      const response = await compareApartments(apartmentIds, preferences, apiSearchContext)
      setApartments(response.apartments)
      setAnalysis(response.comparison_analysis || null)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message)
      } else {
        setError('Failed to score apartments')
      }
    } finally {
      setScoring(false)
    }
  }

  const lowestRent = apartments.length > 0 ? Math.min(...apartments.map(a => a.rent)) : 0

  // Auth loading state
  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-pulse text-center">
          <div className="h-8 w-48 bg-gray-200 rounded mb-4 mx-auto"></div>
          <div className="h-4 w-32 bg-gray-200 rounded mx-auto"></div>
        </div>
      </div>
    )
  }

  // Auth gate — must be signed in
  if (!user) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col">
        <header className="bg-white shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
            <div className="flex items-center gap-4">
              <Link href="/" className="text-gray-600 hover:text-gray-900">
                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
              </Link>
              <h1 className="text-2xl font-bold text-gray-900">Compare Apartments</h1>
            </div>
          </div>
        </header>
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center p-8">
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Sign in to compare apartments</h2>
            <p className="text-gray-600 mb-6">Create an account to use the comparison tool.</p>
            <button
              onClick={signInWithGoogle}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
            >
              Sign In with Google
            </button>
          </div>
        </main>
      </div>
    )
  }

  // Not enough apartments selected
  if (apartmentIds.length < 2 && !loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col">
        <header className="bg-white shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
            <div className="flex items-center gap-4">
              <Link href="/" className="text-gray-600 hover:text-gray-900">
                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
              </Link>
              <h1 className="text-2xl font-bold text-gray-900">Compare Apartments</h1>
            </div>
          </div>
        </header>
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center p-8">
            <svg className="h-16 w-16 text-gray-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Select at least 2 apartments to compare</h2>
            <p className="text-gray-600 mb-6">Go back to search results and add apartments using the Compare button.</p>
            <Link href="/" className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors">
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              Search Apartments
            </Link>
          </div>
        </main>
      </div>
    )
  }

  // Find winner apartment for highlighting
  const winnerAptId = analysis?.winner?.apartment_id
  const winnerApt = apartments.find(a => a.id === winnerAptId)

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link href="/" className="text-gray-600 hover:text-gray-900">
                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
              </Link>
              <h1 className="text-2xl font-bold text-gray-900">Compare Apartments</h1>
            </div>
            <button
              onClick={() => { clearComparison(); router.push('/') }}
              className="text-gray-600 hover:text-gray-900 text-sm"
            >
              Clear All
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* AI Scoring Section */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <svg className="h-5 w-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            Get AI Comparison
          </h2>
          <p className="text-gray-600 mb-4">
            Tell us what matters most to you and Claude AI will do a deep head-to-head analysis.
          </p>
          <div className="flex gap-4">
            <input
              type="text"
              value={preferences}
              onChange={(e) => setPreferences(e.target.value)}
              placeholder="e.g., parking, quiet for WFH, near transit"
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              onKeyDown={(e) => { if (e.key === 'Enter' && preferences.trim()) handleScore() }}
            />
            <button
              onClick={handleScore}
              disabled={scoring || !preferences.trim()}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {scoring ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                  Analyzing...
                </>
              ) : (
                <>
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  Score
                </>
              )}
            </button>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <div className="flex items-center gap-2">
              <svg className="h-5 w-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-red-700">{error}</p>
            </div>
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mb-4"></div>
            <p className="text-gray-600">Loading apartments...</p>
          </div>
        )}

        {/* Winner Summary Card — appears after scoring */}
        {analysis && winnerApt && (
          <div className="bg-white rounded-lg shadow-md p-6 mb-8 border-2 border-green-400">
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-green-600 font-bold text-lg">Winner</span>
                  <svg className="h-6 w-6 text-green-500" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                  </svg>
                </div>
                <h3 className="text-xl font-semibold text-gray-900">{winnerApt.address}</h3>
                <p className="text-gray-600 mt-1">{analysis.winner.reason}</p>
              </div>
            </div>
            {/* Overall scores side by side */}
            <div className="flex gap-4 mt-4">
              {analysis.apartment_scores.map((score) => {
                const apt = apartments.find(a => a.id === score.apartment_id)
                const isWinner = score.apartment_id === winnerAptId
                return (
                  <div
                    key={score.apartment_id}
                    className={`flex-1 p-3 rounded-lg ${isWinner ? 'bg-green-50 border border-green-200' : 'bg-gray-50'}`}
                  >
                    <p className="text-sm text-gray-600 truncate">{apt?.address || score.apartment_id}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`text-2xl font-bold ${isWinner ? 'text-green-600' : 'text-gray-700'}`}>
                        {score.overall_score}
                      </span>
                      <span className="text-sm text-gray-500">/100</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Category Scores Grid — appears after scoring */}
        {analysis && (
          <div className="bg-white rounded-lg shadow-md p-6 mb-8">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Category Breakdown</h3>
            <div className="space-y-4">
              {analysis.categories.map((category) => {
                // Find highest score in this category
                const scores = analysis.apartment_scores.map(s => s.category_scores[category]?.score || 0)
                const maxScore = Math.max(...scores)

                return (
                  <div key={category} className="border-b border-gray-100 pb-4 last:border-0">
                    <h4 className="text-sm font-medium text-gray-900 mb-2">{category}</h4>
                    <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${apartments.length}, 1fr)` }}>
                      {analysis.apartment_scores.map((aptScore) => {
                        const catScore = aptScore.category_scores[category]
                        const isHighest = catScore && catScore.score === maxScore && scores.filter(s => s === maxScore).length === 1
                        return (
                          <div
                            key={aptScore.apartment_id}
                            className={`p-3 rounded-lg ${isHighest ? 'bg-green-50 border border-green-200' : 'bg-gray-50'}`}
                          >
                            <div className="flex items-center gap-2">
                              <span className={`inline-block px-2 py-0.5 rounded-full text-white text-sm font-bold ${getScoreColor(catScore?.score || 0)}`}>
                                {catScore?.score || 0}
                              </span>
                              {isHighest && (
                                <svg className="h-4 w-4 text-green-500" fill="currentColor" viewBox="0 0 24 24">
                                  <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                                </svg>
                              )}
                            </div>
                            <p className="text-xs text-gray-600 mt-1">{catScore?.note || ''}</p>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Comparison Table */}
        {!loading && apartments.length > 0 && (
          <div className="bg-white rounded-lg shadow-md overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="bg-gray-50 px-6 py-4 text-left text-sm font-semibold text-gray-900 w-40">Property</th>
                    {apartments.map((apt) => (
                      <th key={apt.id} className="px-6 py-4 text-center border-l border-gray-200">
                        <div className="relative">
                          <button
                            onClick={() => removeFromCompare(apt.id)}
                            className="absolute -top-2 right-0 text-gray-400 hover:text-red-500"
                            title="Remove from comparison"
                          >
                            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                          {apt.images && apt.images.length > 0 && (
                            <div className="relative w-full h-32 mb-3">
                              <Image src={apt.images[0]} alt={apt.address} fill className="object-cover rounded-lg" sizes="(max-width: 768px) 100vw, 33vw" />
                            </div>
                          )}
                          <h3 className="font-semibold text-gray-900 text-sm">
                            {apt.id === winnerAptId && <span className="text-green-500 mr-1">&#9733;</span>}
                            {apt.address}
                          </h3>
                          <p className="text-xs text-gray-500">{apt.neighborhood}</p>
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {/* Overall Score Row (from analysis) */}
                  {analysis && (
                    <tr>
                      <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">Overall Score</td>
                      {apartments.map((apt) => {
                        const aptScore = analysis.apartment_scores.find(s => s.apartment_id === apt.id)
                        const isWinner = apt.id === winnerAptId
                        return (
                          <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200">
                            <span className={`inline-block px-3 py-1 rounded-full text-white text-sm font-bold ${getScoreColor(aptScore?.overall_score || 0)} ${isWinner ? 'ring-2 ring-offset-2 ring-green-400' : ''}`}>
                              {aptScore?.overall_score || 0}%
                            </span>
                          </td>
                        )
                      })}
                    </tr>
                  )}

                  {/* Rent Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">Rent</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className={`px-6 py-4 text-center border-l border-gray-200 ${apt.rent === lowestRent ? 'bg-green-50' : ''}`}>
                        <span className={`text-lg font-bold ${apt.rent === lowestRent ? 'text-green-600' : 'text-gray-900'}`}>{formatRent(apt.rent)}</span>
                        <span className="text-sm text-gray-500">/mo</span>
                        {apt.rent === lowestRent && <span className="block text-xs text-green-600 font-medium mt-1">Lowest</span>}
                      </td>
                    ))}
                  </tr>

                  {/* Bedrooms Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">Bedrooms</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200 text-gray-700">
                        {apt.bedrooms === 0 ? 'Studio' : `${apt.bedrooms} bed`}
                      </td>
                    ))}
                  </tr>

                  {/* Bathrooms Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">Bathrooms</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200 text-gray-700">{apt.bathrooms} bath</td>
                    ))}
                  </tr>

                  {/* Square Footage Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">Size</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200 text-gray-700">{formatSqft(apt.sqft)} sqft</td>
                    ))}
                  </tr>

                  {/* Property Type Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">Type</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200 text-gray-700">{apt.property_type}</td>
                    ))}
                  </tr>

                  {/* Available Date Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">Available</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200 text-gray-700">
                        {new Date(apt.available_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                      </td>
                    ))}
                  </tr>

                  {/* Amenities Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900 align-top">Amenities</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 border-l border-gray-200">
                        <div className="flex flex-wrap gap-1 justify-center">
                          {apt.amenities.map((amenity) => (
                            <span key={amenity} className="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded-full">{amenity}</span>
                          ))}
                        </div>
                      </td>
                    ))}
                  </tr>

                  {/* AI Reasoning Row (from analysis) */}
                  {analysis && (
                    <tr>
                      <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900 align-top">AI Analysis</td>
                      {apartments.map((apt) => {
                        const aptScore = analysis.apartment_scores.find(s => s.apartment_id === apt.id)
                        return (
                          <td key={apt.id} className="px-6 py-4 border-l border-gray-200">
                            {aptScore && (
                              <>
                                <p className="text-sm text-gray-700 italic mb-3">&quot;{aptScore.reasoning}&quot;</p>
                                {aptScore.highlights.length > 0 && (
                                  <ul className="space-y-1">
                                    {aptScore.highlights.map((highlight, index) => (
                                      <li key={index} className="flex items-start gap-2 text-sm text-gray-600">
                                        <svg className="h-4 w-4 text-green-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                        </svg>
                                        {highlight}
                                      </li>
                                    ))}
                                  </ul>
                                )}
                              </>
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  )}

                  {/* View Listing Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">Actions</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200">
                        <a
                          href={`/apartment/${apt.id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
                        >
                          View Details
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                          </svg>
                        </a>
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="bg-white border-t mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <p className="text-center text-sm text-gray-500">Powered by Claude AI &middot; Built with Next.js and FastAPI</p>
        </div>
      </footer>
    </div>
  )
}
```

**Step 2: Build the frontend to check for type errors**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no type errors

**Step 3: Commit**

```bash
git add frontend/app/compare/page.tsx
git commit -m "feat: rebuild compare page with analysis UI and auth gate"
```

---

### Task 10: Add Auth Gate to Search Page

**Files:**
- Modify: `frontend/app/page.tsx`

**Step 1: Add auth gate to the home page**

Import `useAuth` and wrap the page content with an auth check. The search form and results should only render for signed-in users.

At the top, add the import:

```typescript
import { useAuth } from '@/contexts/AuthContext';
```

Inside the `Home` component, add auth state:

```typescript
const { user, loading: authLoading, signInWithGoogle } = useAuth();
```

Before the main return, add auth loading and auth gate checks:

```typescript
if (authLoading) {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="animate-pulse text-center">
        <div className="h-8 w-48 bg-gray-200 rounded mb-4 mx-auto"></div>
        <div className="h-4 w-32 bg-gray-200 rounded mx-auto"></div>
      </div>
    </div>
  );
}

if (!user) {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="text-center p-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-4">Find Your Perfect Apartment</h2>
        <p className="text-lg text-gray-600 max-w-2xl mx-auto mb-8">
          Sign in to search apartments with AI-powered matching.
        </p>
        <button
          onClick={signInWithGoogle}
          className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
        >
          Sign In with Google
        </button>
      </div>
    </div>
  );
}
```

**Step 2: Build frontend to verify**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat: add auth gate to search page"
```

---

### Task 11: Run E2E Tests and Fix Failures

**Files:**
- Possibly modify: `frontend/e2e/homescout.spec.ts`

The E2E tests mock API routes and don't use real auth, so the auth gate on the home page may break some tests. This task is about identifying and fixing any E2E test failures caused by our changes.

**Step 1: Run all E2E tests**

Run: `cd frontend && npx playwright test`

**Step 2: Fix any failures**

The mocked tests should still work because they intercept at the API level and don't test auth. However, if the auth gate blocks rendering of the search form in tests, we may need to mock the auth context or adjust the test setup.

Common fix: The E2E tests that route-intercept `/api/search` may need the page to render the SearchForm. Since the auth check uses `useAuth()` which depends on Supabase, and the tests run against a real browser, we may need to either:
- Skip the auth gate when `NEXT_PUBLIC_SUPABASE_URL` is not set (tests don't configure Supabase)
- Or mock the Supabase auth in Playwright tests

Evaluate after running and fix accordingly.

**Step 3: Run tests again after fix**

Run: `cd frontend && npx playwright test`
Expected: All tests pass

**Step 4: Commit if changes were needed**

```bash
git add frontend/
git commit -m "fix: adjust E2E tests for auth gate"
```

---

### Task 12: Manual Integration Test

**Step 1: Start backend**

Run: `cd backend && source .venv/bin/activate && .venv/bin/python -m uvicorn app.main:app --port 8000`

**Step 2: Test the compare endpoint with curl**

```bash
curl -X POST http://localhost:8000/api/apartments/compare \
  -H "Content-Type: application/json" \
  -d '{
    "apartment_ids": ["apt-001", "apt-002"],
    "preferences": "parking, quiet for WFH",
    "search_context": {
      "city": "Bryn Mawr, PA",
      "budget": 2000,
      "bedrooms": 1,
      "bathrooms": 1,
      "property_type": "Apartment",
      "move_in_date": "2026-03-01"
    }
  }'
```

Expected: JSON response with `apartments`, `comparison_fields`, and `comparison_analysis` containing `winner`, `categories`, and `apartment_scores`.

**Step 3: Test without preferences (existing behavior preserved)**

```bash
curl -X POST http://localhost:8000/api/apartments/compare \
  -H "Content-Type: application/json" \
  -d '{"apartment_ids": ["apt-001", "apt-002"]}'
```

Expected: Response with `apartments` and `comparison_fields` only, `comparison_analysis` should be null.

**Step 4: Start frontend and test UI flow**

Run: `cd frontend && npm run dev`

1. Sign in with Google
2. Search for apartments in Bryn Mawr
3. Add 2 apartments to comparison
4. Navigate to compare page
5. Verify preferences input is pre-filled with search preferences
6. Click Score
7. Verify winner card appears with green border
8. Verify category breakdown grid appears
9. Verify comparison table has Overall Score row
10. Verify winner has star indicator in table header

**Step 5: Final commit if any fixes needed**

---

### Summary of Files Changed

| File | Action | Description |
|------|--------|-------------|
| `backend/app/schemas.py` | Modify | Add 5 new Pydantic models, update CompareRequest/Response |
| `backend/app/services/claude_service.py` | Modify | Add `compare_apartments_with_analysis()` method |
| `backend/app/routers/apartments.py` | Modify | Wire compare endpoint to Claude when preferences given |
| `backend/tests/test_apartments_router.py` | Modify | Add 2 tests for compare with/without preferences |
| `frontend/types/apartment.ts` | Modify | Add 5 TypeScript interfaces |
| `frontend/lib/api.ts` | Modify | Update CompareResponse, compareApartments signature |
| `frontend/hooks/useComparison.ts` | Modify | Add searchContext to Zustand store |
| `frontend/components/SearchForm.tsx` | Modify | Save search context on submission |
| `frontend/app/compare/page.tsx` | Modify | Full rewrite with analysis UI + auth gate |
| `frontend/app/page.tsx` | Modify | Add auth gate |
| `frontend/e2e/homescout.spec.ts` | Possibly modify | Fix E2E tests for auth gate |
