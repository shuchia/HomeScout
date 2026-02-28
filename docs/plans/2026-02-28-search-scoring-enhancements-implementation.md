# Search Scoring Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace unranked free-tier search with heuristic-scored results, pre-rank candidates before sending to Claude for Pro users, cache Claude scores, and send richer data to Claude.

**Architecture:** Unified pipeline — heuristic scoring runs on every search, Claude AI layers on top for Pro users. `ScoringService` handles heuristic math, `apartment_service.py` orchestrates the pipeline, Redis caches Claude responses.

**Tech Stack:** Python 3.12, FastAPI, Redis, PostgreSQL (SQLAlchemy), PyJWT, Anthropic SDK, Next.js/React/TypeScript

---

### Task 1: Create ScoringService with budget fit scoring

**Files:**
- Create: `backend/app/services/scoring_service.py`
- Create: `backend/tests/test_scoring_service.py`

**Step 1: Write the failing tests**

```python
"""Tests for ScoringService heuristic scoring."""
import pytest
from app.services.scoring_service import ScoringService


class TestBudgetFitScore:
    """Budget fit component: 30% weight, 0-100 scale."""

    def test_rent_at_budget_returns_100(self):
        score = ScoringService.budget_fit_score(rent=2000, budget=2000)
        assert score == 100

    def test_rent_under_budget_returns_100(self):
        score = ScoringService.budget_fit_score(rent=1500, budget=2000)
        assert score == 100

    def test_rent_5_percent_over_returns_50(self):
        # 5% over $2000 = $2100. Linear decay: 100 -> 0 across 0-10%
        score = ScoringService.budget_fit_score(rent=2100, budget=2000)
        assert score == 50

    def test_rent_10_percent_over_returns_0(self):
        score = ScoringService.budget_fit_score(rent=2200, budget=2000)
        assert score == 0

    def test_rent_over_10_percent_returns_0(self):
        score = ScoringService.budget_fit_score(rent=2500, budget=2000)
        assert score == 0

    def test_rent_1_percent_over(self):
        # 1% over = rent 2020, budget 2000. Score should be ~90
        score = ScoringService.budget_fit_score(rent=2020, budget=2000)
        assert 85 <= score <= 95
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_scoring_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.scoring_service'`

**Step 3: Write minimal implementation**

```python
"""Heuristic scoring engine for apartment search results.

Computes a 0-100 score for each apartment against search criteria
using weighted components: budget fit, freshness, data quality,
amenity match, and space fit. No AI calls — pure math.
"""


class ScoringService:
    """Stateless heuristic scoring for apartments."""

    @staticmethod
    def budget_fit_score(rent: int, budget: int) -> int:
        """Score how well rent fits the budget (0-100).

        100 if rent <= budget. Linear decay from 100 to 0
        across the 0-10% overshoot range. 0 if >10% over.
        """
        if budget <= 0:
            return 0
        if rent <= budget:
            return 100
        overshoot = (rent - budget) / budget  # 0.0 to 1.0
        if overshoot >= 0.10:
            return 0
        # Linear: 100 at 0% over, 0 at 10% over
        return int(100 * (1 - overshoot / 0.10))
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_scoring_service.py -v`
Expected: All 6 PASS

**Step 5: Commit**

```bash
git add backend/app/services/scoring_service.py backend/tests/test_scoring_service.py
git commit -m "feat: add ScoringService with budget fit scoring"
```

---

### Task 2: Add freshness and data quality scoring

**Files:**
- Modify: `backend/app/services/scoring_service.py`
- Modify: `backend/tests/test_scoring_service.py`

**Step 1: Write the failing tests**

Add to `test_scoring_service.py`:

```python
from datetime import datetime, timedelta


class TestFreshnessScore:
    """Freshness component: 20% weight, 0-100 scale."""

    def test_high_confidence_recent_returns_high(self):
        last_seen = datetime.utcnow() - timedelta(hours=6)
        score = ScoringService.freshness_score(
            freshness_confidence=90, last_seen_at=last_seen.isoformat()
        )
        assert score >= 85

    def test_low_confidence_old_returns_low(self):
        last_seen = datetime.utcnow() - timedelta(days=14)
        score = ScoringService.freshness_score(
            freshness_confidence=40, last_seen_at=last_seen.isoformat()
        )
        assert score <= 40

    def test_missing_data_returns_50(self):
        score = ScoringService.freshness_score(
            freshness_confidence=None, last_seen_at=None
        )
        assert score == 50


class TestDataQualityScore:
    """Data quality component: 15% weight, uses DB field directly."""

    def test_returns_db_score(self):
        score = ScoringService.data_quality_score(quality=85)
        assert score == 85

    def test_none_returns_50(self):
        score = ScoringService.data_quality_score(quality=None)
        assert score == 50

    def test_clamps_to_100(self):
        score = ScoringService.data_quality_score(quality=120)
        assert score == 100
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_scoring_service.py -v`
Expected: FAIL — `AttributeError: type object 'ScoringService' has no attribute 'freshness_score'`

**Step 3: Write minimal implementation**

Add to `scoring_service.py`:

```python
from datetime import datetime, timedelta
from typing import Optional


# Add these methods to ScoringService class:

    @staticmethod
    def freshness_score(
        freshness_confidence: Optional[int],
        last_seen_at: Optional[str],
    ) -> int:
        """Score listing freshness (0-100).

        Blends the DB freshness_confidence (70% weight) with
        recency of last_seen_at (30% weight).
        """
        # Confidence component (70%)
        conf = freshness_confidence if freshness_confidence is not None else 50
        conf = max(0, min(100, conf))

        # Recency component (30%)
        if last_seen_at:
            try:
                last_seen = datetime.fromisoformat(last_seen_at.replace("Z", "+00:00"))
                age_days = (datetime.utcnow() - last_seen.replace(tzinfo=None)).total_seconds() / 86400
                # 100 if seen today, decays to 0 over 30 days
                recency = max(0, int(100 * (1 - age_days / 30)))
            except (ValueError, TypeError):
                recency = 50
        else:
            recency = 50

        return int(conf * 0.7 + recency * 0.3)

    @staticmethod
    def data_quality_score(quality: Optional[int]) -> int:
        """Score based on DB data_quality_score (0-100). Returns 50 if missing."""
        if quality is None:
            return 50
        return max(0, min(100, quality))
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_scoring_service.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/services/scoring_service.py backend/tests/test_scoring_service.py
git commit -m "feat: add freshness and data quality scoring components"
```

---

### Task 3: Add amenity keyword extraction and matching

**Files:**
- Modify: `backend/app/services/scoring_service.py`
- Modify: `backend/tests/test_scoring_service.py`

**Step 1: Write the failing tests**

Add to `test_scoring_service.py`:

```python
class TestAmenityMatchScore:
    """Amenity match component: 20% weight."""

    def test_all_preferences_matched(self):
        score = ScoringService.amenity_match_score(
            other_preferences="I need parking and a gym",
            amenities=["Covered Parking", "Fitness Center", "Pool"],
        )
        assert score == 100  # 2/2 categories matched

    def test_partial_match(self):
        score = ScoringService.amenity_match_score(
            other_preferences="pet-friendly with parking and gym",
            amenities=["Fitness Center"],
        )
        # 1/3 matched = 33
        assert 30 <= score <= 35

    def test_no_match(self):
        score = ScoringService.amenity_match_score(
            other_preferences="I need a pool",
            amenities=["Parking", "Gym"],
        )
        assert score == 0

    def test_no_preferences_returns_100(self):
        """No preferences = everything matches."""
        score = ScoringService.amenity_match_score(
            other_preferences=None,
            amenities=["Parking"],
        )
        assert score == 100

    def test_empty_preferences_returns_100(self):
        score = ScoringService.amenity_match_score(
            other_preferences="",
            amenities=["Parking"],
        )
        assert score == 100

    def test_case_insensitive(self):
        score = ScoringService.amenity_match_score(
            other_preferences="PET FRIENDLY",
            amenities=["pet-friendly"],
        )
        assert score == 100


class TestExtractPreferenceCategories:
    """Keyword extraction from free-text preferences."""

    def test_extracts_multiple_categories(self):
        categories = ScoringService.extract_preference_categories(
            "I need parking and a gym, must be pet-friendly"
        )
        assert "parking" in categories
        assert "gym" in categories
        assert "pet" in categories

    def test_returns_empty_for_none(self):
        categories = ScoringService.extract_preference_categories(None)
        assert categories == set()

    def test_returns_empty_for_no_match(self):
        categories = ScoringService.extract_preference_categories(
            "I want a nice apartment"
        )
        assert categories == set()
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_scoring_service.py::TestAmenityMatchScore -v`
Expected: FAIL — `AttributeError`

**Step 3: Write minimal implementation**

Add to `scoring_service.py`:

```python
from typing import List, Set

# Module-level constant
PREFERENCE_KEYWORDS: dict[str, list[str]] = {
    "pet": ["pet-friendly", "pet friendly", "dogs allowed", "cats allowed", "pet"],
    "parking": ["parking", "garage", "covered parking", "ev charging"],
    "laundry": ["washer", "dryer", "in-unit laundry", "laundry"],
    "gym": ["gym", "fitness center", "fitness"],
    "pool": ["pool", "swimming"],
    "transit": ["transit", "metro", "subway", "bus", "train station"],
    "outdoor": ["balcony", "patio", "rooftop", "terrace", "yard"],
    "security": ["doorman", "concierge", "gated", "security"],
    "storage": ["storage", "closet space"],
    "utilities": ["utilities included", "wifi included", "water included"],
}

# Add these methods to ScoringService class:

    @staticmethod
    def extract_preference_categories(other_preferences: Optional[str]) -> Set[str]:
        """Extract amenity categories from free-text preferences."""
        if not other_preferences:
            return set()
        text = other_preferences.lower()
        matched = set()
        for category, keywords in PREFERENCE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                matched.add(category)
        return matched

    @staticmethod
    def amenity_match_score(
        other_preferences: Optional[str],
        amenities: List[str],
    ) -> int:
        """Score how well listing amenities match user preferences (0-100).

        Extracts categories from other_preferences, checks each against
        the listing's amenities list. Returns 100 if no preferences given.
        """
        requested = ScoringService.extract_preference_categories(other_preferences)
        if not requested:
            return 100  # No preferences = everything matches

        amenities_lower = " ".join(a.lower() for a in amenities)
        matched = 0
        for category in requested:
            keywords = PREFERENCE_KEYWORDS[category]
            if any(kw in amenities_lower for kw in keywords):
                matched += 1

        return int(matched / len(requested) * 100)
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_scoring_service.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/services/scoring_service.py backend/tests/test_scoring_service.py
git commit -m "feat: add amenity keyword extraction and matching"
```

---

### Task 4: Add space fit scoring and overall score computation

**Files:**
- Modify: `backend/app/services/scoring_service.py`
- Modify: `backend/tests/test_scoring_service.py`

**Step 1: Write the failing tests**

Add to `test_scoring_service.py`:

```python
class TestSpaceFitScore:
    """Space fit component: 15% weight."""

    def test_exact_bedroom_match_with_sqft(self):
        score = ScoringService.space_fit_score(
            bedrooms=2, requested_bedrooms=2,
            bathrooms=2, requested_bathrooms=1,
            sqft=1200,
        )
        assert score >= 80

    def test_no_sqft_still_scores(self):
        score = ScoringService.space_fit_score(
            bedrooms=2, requested_bedrooms=2,
            bathrooms=1, requested_bathrooms=1,
            sqft=None,
        )
        assert 50 <= score <= 80

    def test_extra_bathrooms_bonus(self):
        base = ScoringService.space_fit_score(
            bedrooms=2, requested_bedrooms=2,
            bathrooms=1, requested_bathrooms=1,
            sqft=None,
        )
        bonus = ScoringService.space_fit_score(
            bedrooms=2, requested_bedrooms=2,
            bathrooms=2, requested_bathrooms=1,
            sqft=None,
        )
        assert bonus > base


class TestOverallScore:
    """Weighted overall score combining all components."""

    def test_perfect_apartment_scores_high(self):
        score = ScoringService.compute_heuristic_score(
            rent=1800, budget=2000,
            freshness_confidence=95, last_seen_at=datetime.utcnow().isoformat(),
            data_quality=90,
            other_preferences="gym and parking",
            amenities=["Fitness Center", "Covered Parking"],
            bedrooms=2, requested_bedrooms=2,
            bathrooms=2, requested_bathrooms=1,
            sqft=1200,
        )
        assert score >= 85

    def test_over_budget_poor_quality_scores_low(self):
        score = ScoringService.compute_heuristic_score(
            rent=2180, budget=2000,
            freshness_confidence=45, last_seen_at=None,
            data_quality=30,
            other_preferences="pool and pet-friendly",
            amenities=[],
            bedrooms=2, requested_bedrooms=2,
            bathrooms=1, requested_bathrooms=1,
            sqft=None,
        )
        assert score <= 40

    def test_score_to_label_excellent(self):
        assert ScoringService.score_to_label(92) == "Excellent Match"

    def test_score_to_label_great(self):
        assert ScoringService.score_to_label(80) == "Great Match"

    def test_score_to_label_good(self):
        assert ScoringService.score_to_label(65) == "Good Match"

    def test_score_to_label_fair(self):
        assert ScoringService.score_to_label(45) == "Fair Match"

    def test_score_to_label_none_for_low(self):
        assert ScoringService.score_to_label(30) is None
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_scoring_service.py::TestSpaceFitScore -v`
Expected: FAIL — `AttributeError`

**Step 3: Write minimal implementation**

Add to `scoring_service.py`:

```python
# Add these methods to ScoringService class:

    @staticmethod
    def space_fit_score(
        bedrooms: int,
        requested_bedrooms: int,
        bathrooms: float,
        requested_bathrooms: float,
        sqft: Optional[int],
    ) -> int:
        """Score space fit (0-100).

        Bedroom match (40%), bathroom overshoot bonus (30%),
        sqft bonus (30% — 50 baseline if unavailable).
        """
        # Bedroom: 100 if exact, 60 if ±1
        if bedrooms == requested_bedrooms:
            bed_score = 100
        elif abs(bedrooms - requested_bedrooms) == 1:
            bed_score = 60
        else:
            bed_score = 20

        # Bathroom: 100 if exact, +10 per extra, cap 100
        if bathrooms >= requested_bathrooms:
            extra = bathrooms - requested_bathrooms
            bath_score = min(100, 80 + int(extra * 10))
        else:
            bath_score = 40

        # Sqft: baseline 50 if unknown, scale by size
        if sqft and sqft > 0:
            # Rough heuristic: 800+ sqft for 1br, +400 per extra br
            expected = 800 + max(0, requested_bedrooms - 1) * 400
            ratio = sqft / expected
            sqft_score = min(100, int(ratio * 80))
        else:
            sqft_score = 50

        return int(bed_score * 0.4 + bath_score * 0.3 + sqft_score * 0.3)

    @staticmethod
    def compute_heuristic_score(
        rent: int,
        budget: int,
        freshness_confidence: Optional[int],
        last_seen_at: Optional[str],
        data_quality: Optional[int],
        other_preferences: Optional[str],
        amenities: List[str],
        bedrooms: int,
        requested_bedrooms: int,
        bathrooms: float,
        requested_bathrooms: float,
        sqft: Optional[int],
    ) -> int:
        """Compute weighted overall heuristic score (0-100).

        Weights: budget 30%, freshness 20%, quality 15%,
        amenity 20%, space 15%.
        """
        budget_s = ScoringService.budget_fit_score(rent, budget)
        fresh_s = ScoringService.freshness_score(freshness_confidence, last_seen_at)
        quality_s = ScoringService.data_quality_score(data_quality)
        amenity_s = ScoringService.amenity_match_score(other_preferences, amenities)
        space_s = ScoringService.space_fit_score(
            bedrooms, requested_bedrooms, bathrooms, requested_bathrooms, sqft
        )

        total = (
            budget_s * 0.30
            + fresh_s * 0.20
            + quality_s * 0.15
            + amenity_s * 0.20
            + space_s * 0.15
        )
        return int(total)

    @staticmethod
    def score_to_label(score: int) -> Optional[str]:
        """Map heuristic score to qualitative label for free users."""
        if score >= 90:
            return "Excellent Match"
        if score >= 75:
            return "Great Match"
        if score >= 60:
            return "Good Match"
        if score >= 40:
            return "Fair Match"
        return None
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_scoring_service.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/services/scoring_service.py backend/tests/test_scoring_service.py
git commit -m "feat: add space fit scoring, overall score, and label mapping"
```

---

### Task 5: Relax budget filter in apartment_service.py

**Files:**
- Modify: `backend/app/services/apartment_service.py:48-107` (database search)
- Modify: `backend/app/services/apartment_service.py:109-162` (JSON search)
- Modify: `backend/tests/test_scoring_service.py`

**Step 1: Write the failing test**

Add a new test file `backend/tests/test_budget_filter.py`:

```python
"""Tests for soft budget filter (10% buffer)."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.apartment_service import ApartmentService


class TestSoftBudgetJsonFilter:
    """JSON mode: budget filter should include up to 10% over."""

    def test_at_budget_included(self):
        svc = ApartmentService.__new__(ApartmentService)
        svc._use_database = False
        svc._apartments_data = [
            {"id": "1", "address": "Philadelphia, PA", "rent": 2000,
             "bedrooms": 2, "bathrooms": 1, "property_type": "Apartment",
             "available_date": "2026-03-01"},
        ]
        result = svc._search_json("Philadelphia", 2000, 2, 1, "Apartment", "2026-04-01")
        assert len(result) == 1

    def test_5_percent_over_included(self):
        svc = ApartmentService.__new__(ApartmentService)
        svc._use_database = False
        svc._apartments_data = [
            {"id": "1", "address": "Philadelphia, PA", "rent": 2100,
             "bedrooms": 2, "bathrooms": 1, "property_type": "Apartment",
             "available_date": "2026-03-01"},
        ]
        result = svc._search_json("Philadelphia", 2000, 2, 1, "Apartment", "2026-04-01")
        assert len(result) == 1

    def test_over_10_percent_excluded(self):
        svc = ApartmentService.__new__(ApartmentService)
        svc._use_database = False
        svc._apartments_data = [
            {"id": "1", "address": "Philadelphia, PA", "rent": 2201,
             "bedrooms": 2, "bathrooms": 1, "property_type": "Apartment",
             "available_date": "2026-03-01"},
        ]
        result = svc._search_json("Philadelphia", 2000, 2, 1, "Apartment", "2026-04-01")
        assert len(result) == 0
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_budget_filter.py -v`
Expected: `test_5_percent_over_included` FAILS (current filter is strict `rent > budget`)

**Step 3: Modify the budget filter**

In `backend/app/services/apartment_service.py`, change both search methods:

**Database search** (line 79): Change `ApartmentModel.rent <= budget` to:
```python
ApartmentModel.rent <= int(budget * 1.10),
```

**JSON search** (lines 135-137): Change:
```python
# Old:
if apt["rent"] > budget:
    continue
# New:
if apt["rent"] > int(budget * 1.10):
    continue
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_budget_filter.py -v`
Expected: All 3 PASS

**Step 5: Commit**

```bash
git add backend/app/services/apartment_service.py backend/tests/test_budget_filter.py
git commit -m "feat: relax budget filter to include apartments up to 10% over"
```

---

### Task 6: Integrate heuristic scoring into apartment_service pipeline

**Files:**
- Modify: `backend/app/services/apartment_service.py:164-281`

**Step 1: Write the failing test**

Add to `backend/tests/test_scoring_service.py`:

```python
class TestScoreApartmentsList:
    """Integration: ScoringService.score_apartments_list scores and sorts."""

    def test_scores_and_sorts_descending(self):
        apartments = [
            {"id": "cheap", "rent": 1500, "bedrooms": 2, "bathrooms": 1,
             "sqft": 1000, "amenities": ["Gym"], "freshness_confidence": 90,
             "last_seen_at": datetime.utcnow().isoformat(), "data_quality_score": 80},
            {"id": "expensive", "rent": 2150, "bedrooms": 2, "bathrooms": 1,
             "sqft": 800, "amenities": [], "freshness_confidence": 50,
             "last_seen_at": None, "data_quality_score": 40},
        ]
        scored = ScoringService.score_apartments_list(
            apartments=apartments,
            budget=2000, bedrooms=2, bathrooms=1,
            other_preferences="gym",
        )
        assert scored[0]["id"] == "cheap"
        assert scored[0]["heuristic_score"] > scored[1]["heuristic_score"]
        assert "match_label" in scored[0]
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_scoring_service.py::TestScoreApartmentsList -v`
Expected: FAIL — `AttributeError: 'ScoringService' has no attribute 'score_apartments_list'`

**Step 3: Write implementation**

Add to `ScoringService` in `scoring_service.py`:

```python
    @staticmethod
    def score_apartments_list(
        apartments: List[dict],
        budget: int,
        bedrooms: int,
        bathrooms: float,
        other_preferences: Optional[str] = None,
    ) -> List[dict]:
        """Score a list of apartments and return sorted (highest first).

        Adds 'heuristic_score' and 'match_label' to each apartment dict.
        """
        scored = []
        for apt in apartments:
            h_score = ScoringService.compute_heuristic_score(
                rent=apt.get("rent", 0),
                budget=budget,
                freshness_confidence=apt.get("freshness_confidence"),
                last_seen_at=apt.get("last_seen_at"),
                data_quality=apt.get("data_quality_score"),
                other_preferences=other_preferences,
                amenities=apt.get("amenities", []),
                bedrooms=apt.get("bedrooms", 0),
                requested_bedrooms=bedrooms,
                bathrooms=apt.get("bathrooms", 0),
                requested_bathrooms=bathrooms,
                sqft=apt.get("sqft"),
            )
            apt_with_score = {
                **apt,
                "heuristic_score": h_score,
                "match_label": ScoringService.score_to_label(h_score),
            }
            scored.append(apt_with_score)

        scored.sort(key=lambda x: x["heuristic_score"], reverse=True)
        return scored
```

Then update `apartment_service.py` to use the unified pipeline. Modify `get_top_apartments` (line 199+):

```python
async def get_top_apartments(
    self,
    city: str,
    budget: int,
    bedrooms: int,
    bathrooms: int,
    property_type: str,
    move_in_date: str,
    other_preferences: str = None,
    top_n: int = 10
) -> Tuple[List[Dict], int]:
    from app.services.scoring_service import ScoringService

    # Step 1: Filter (with soft budget)
    filtered_apartments = await self.search_apartments(
        city=city, budget=budget, bedrooms=bedrooms,
        bathrooms=bathrooms, property_type=property_type,
        move_in_date=move_in_date,
    )

    if not filtered_apartments:
        return [], 0

    # Step 2: Heuristic score and sort ALL filtered results
    scored = ScoringService.score_apartments_list(
        apartments=filtered_apartments,
        budget=budget, bedrooms=bedrooms, bathrooms=bathrooms,
        other_preferences=other_preferences,
    )

    total_count = len(scored)

    # Step 3: Send top 20 (by heuristic) to Claude for AI re-scoring
    max_to_score = top_n * 2
    apartments_to_score = scored[:max_to_score]

    scores = await asyncio.to_thread(
        self.claude_service.score_apartments,
        city=city, budget=budget, bedrooms=bedrooms,
        bathrooms=bathrooms, property_type=property_type,
        move_in_date=move_in_date,
        other_preferences=other_preferences or "None specified",
        apartments=apartments_to_score,
    )

    # Step 4: Merge Claude scores
    scored_apartments = []
    score_map = {score["apartment_id"]: score for score in scores}
    for apt in apartments_to_score:
        apt_id = apt["id"]
        if apt_id in score_map:
            score_data = score_map[apt_id]
            scored_apt = {
                **apt,
                "match_score": score_data["match_score"],
                "reasoning": score_data["reasoning"],
                "highlights": score_data["highlights"],
            }
            scored_apartments.append(scored_apt)

    scored_apartments.sort(key=lambda x: x["match_score"], reverse=True)
    return scored_apartments[:top_n], total_count
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_scoring_service.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/services/scoring_service.py backend/app/services/apartment_service.py backend/tests/test_scoring_service.py
git commit -m "feat: integrate heuristic scoring into apartment search pipeline"
```

---

### Task 7: Update search endpoint for unified pipeline

**Files:**
- Modify: `backend/app/main.py:136-238`
- Modify: `backend/app/schemas.py`

**Step 1: Update schemas**

In `backend/app/schemas.py`, the `ApartmentWithScore` model currently requires `match_score` as `int`. Change it to accept `Optional[int]` and add new fields:

```python
class ApartmentWithScore(Apartment):
    """Model combining apartment data with its match score"""
    match_score: Optional[int] = Field(None, ge=0, le=100)
    reasoning: Optional[str] = None
    highlights: List[str] = Field(default_factory=list)
    heuristic_score: Optional[int] = Field(None, ge=0, le=100)
    match_label: Optional[str] = None
```

**Step 2: Update the search endpoint**

In `backend/app/main.py`, replace the free/anonymous branch (lines 187-206) with heuristic scoring:

```python
        else:
            # Free / anonymous: heuristic score and rank
            from app.services.scoring_service import ScoringService

            filtered = await apartment_service.search_apartments(
                city=request.city,
                budget=request.budget,
                bedrooms=request.bedrooms,
                bathrooms=request.bathrooms,
                property_type=request.property_type,
                move_in_date=request.move_in_date,
            )
            scored = ScoringService.score_apartments_list(
                apartments=filtered,
                budget=request.budget,
                bedrooms=request.bedrooms,
                bathrooms=request.bathrooms,
                other_preferences=request.other_preferences,
            )
            total_count = len(scored)
            apartments_out = [
                {
                    **apt,
                    "match_score": None,
                    "reasoning": None,
                    "highlights": [],
                }
                for apt in scored[:10]
            ]
```

**Step 3: Run existing tests to verify no regressions**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add backend/app/main.py backend/app/schemas.py
git commit -m "feat: unified search endpoint with heuristic scoring for free users"
```

---

### Task 8: Remove data truncation in claude_service.py

**Files:**
- Modify: `backend/app/services/claude_service.py:47-66`

**Step 1: Write the failing test**

Create `backend/tests/test_claude_data.py`:

```python
"""Tests for Claude service data preparation."""
import pytest
from app.services.claude_service import ClaudeService


class TestSlimApartmentData:
    """Verify Claude receives full data without truncation."""

    def test_full_description_sent(self):
        """Description should not be truncated."""
        long_desc = "A" * 1000
        apt = {
            "id": "test", "address": "123 Main St", "rent": 2000,
            "bedrooms": 2, "bathrooms": 1, "sqft": 900,
            "property_type": "Apartment", "available_date": "2026-03-01",
            "neighborhood": "Downtown", "description": long_desc,
            "amenities": list(range(25)),
            "data_quality_score": 85, "heuristic_score": 78,
        }
        slim = ClaudeService.prepare_apartment_for_scoring(apt)
        assert len(slim["description"]) == 1000

    def test_all_amenities_sent(self):
        """Amenities should not be capped."""
        amenities = [f"Amenity {i}" for i in range(25)]
        apt = {
            "id": "test", "address": "123 Main St", "rent": 2000,
            "bedrooms": 2, "bathrooms": 1, "sqft": 900,
            "property_type": "Apartment", "available_date": "2026-03-01",
            "neighborhood": "Downtown", "description": "Nice",
            "amenities": amenities,
            "data_quality_score": 85, "heuristic_score": 78,
        }
        slim = ClaudeService.prepare_apartment_for_scoring(apt)
        assert len(slim["amenities"]) == 25

    def test_heuristic_score_included(self):
        apt = {
            "id": "test", "address": "123 Main St", "rent": 2000,
            "bedrooms": 2, "bathrooms": 1, "sqft": 900,
            "property_type": "Apartment", "available_date": "2026-03-01",
            "neighborhood": "Downtown", "description": "Nice",
            "amenities": [], "data_quality_score": 85, "heuristic_score": 78,
        }
        slim = ClaudeService.prepare_apartment_for_scoring(apt)
        assert slim["heuristic_score"] == 78
        assert slim["data_quality_score"] == 85
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_claude_data.py -v`
Expected: FAIL — `AttributeError: 'ClaudeService' has no attribute 'prepare_apartment_for_scoring'`

**Step 3: Refactor claude_service.py**

Extract the apartment preparation into a static method and remove truncation. In `backend/app/services/claude_service.py`, replace lines 48-64:

```python
    @staticmethod
    def prepare_apartment_for_scoring(apt: dict) -> dict:
        """Prepare apartment data for Claude scoring. No truncation."""
        return {
            "id": apt["id"],
            "address": apt.get("address", ""),
            "rent": apt.get("rent", 0),
            "bedrooms": apt.get("bedrooms", 0),
            "bathrooms": apt.get("bathrooms", 0),
            "sqft": apt.get("sqft", 0),
            "property_type": apt.get("property_type", ""),
            "available_date": apt.get("available_date", ""),
            "neighborhood": apt.get("neighborhood", ""),
            "description": apt.get("description", "") or "",
            "amenities": apt.get("amenities", []) or [],
            "data_quality_score": apt.get("data_quality_score"),
            "heuristic_score": apt.get("heuristic_score"),
        }
```

Then update `score_apartments()` to use it:

```python
        slim_apartments = [
            self.prepare_apartment_for_scoring(apt) for apt in apartments
        ]
```

Also update `compare_apartments_with_analysis()` the same way (lines 210-225):

```python
        slim_apartments = [
            self.prepare_apartment_for_scoring(apt) for apt in apartments
        ]
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_claude_data.py tests/test_scoring_service.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/services/claude_service.py backend/tests/test_claude_data.py
git commit -m "feat: send full description and amenities to Claude, add heuristic_score"
```

---

### Task 9: Add Redis caching for Claude scores

**Files:**
- Modify: `backend/app/services/apartment_service.py`
- Create: `backend/tests/test_claude_cache.py`

**Step 1: Write the failing test**

```python
"""Tests for Claude score caching."""
import pytest
import json
import hashlib
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.apartment_service import ApartmentService


class TestClaudeScoreCache:
    def test_cache_key_deterministic(self):
        """Same inputs produce same cache key."""
        key1 = ApartmentService.build_score_cache_key(
            city="Philadelphia", budget=2000, bedrooms=2, bathrooms=1,
            property_type="Apartment", move_in_date="2026-03-01",
            other_preferences="gym", apartment_ids=["a", "b"],
        )
        key2 = ApartmentService.build_score_cache_key(
            city="Philadelphia", budget=2000, bedrooms=2, bathrooms=1,
            property_type="Apartment", move_in_date="2026-03-01",
            other_preferences="gym", apartment_ids=["a", "b"],
        )
        assert key1 == key2

    def test_cache_key_different_for_different_inputs(self):
        key1 = ApartmentService.build_score_cache_key(
            city="Philadelphia", budget=2000, bedrooms=2, bathrooms=1,
            property_type="Apartment", move_in_date="2026-03-01",
            other_preferences="gym", apartment_ids=["a", "b"],
        )
        key2 = ApartmentService.build_score_cache_key(
            city="Boston", budget=2000, bedrooms=2, bathrooms=1,
            property_type="Apartment", move_in_date="2026-03-01",
            other_preferences="gym", apartment_ids=["a", "b"],
        )
        assert key1 != key2

    def test_cache_key_sorted_apartment_ids(self):
        """Apartment ID order shouldn't matter."""
        key1 = ApartmentService.build_score_cache_key(
            city="Philadelphia", budget=2000, bedrooms=2, bathrooms=1,
            property_type="Apartment", move_in_date="2026-03-01",
            other_preferences="gym", apartment_ids=["b", "a"],
        )
        key2 = ApartmentService.build_score_cache_key(
            city="Philadelphia", budget=2000, bedrooms=2, bathrooms=1,
            property_type="Apartment", move_in_date="2026-03-01",
            other_preferences="gym", apartment_ids=["a", "b"],
        )
        assert key1 == key2
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_claude_cache.py -v`
Expected: FAIL — `AttributeError`

**Step 3: Write implementation**

Add to `apartment_service.py`:

```python
import hashlib
import redis
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SCORE_CACHE_TTL = 3600  # 1 hour

# At class level in ApartmentService.__init__:
        try:
            self._redis = redis.from_url(REDIS_URL)
        except Exception:
            self._redis = None

# Static method:
    @staticmethod
    def build_score_cache_key(
        city: str, budget: int, bedrooms: int, bathrooms: float,
        property_type: str, move_in_date: str,
        other_preferences: str, apartment_ids: list[str],
    ) -> str:
        """Build deterministic Redis key for Claude score cache."""
        raw = f"{city}|{budget}|{bedrooms}|{bathrooms}|{property_type}|{move_in_date}|{other_preferences}|{','.join(sorted(apartment_ids))}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"claude_score:{digest}"
```

Then update `get_top_apartments` to check cache before calling Claude:

```python
    # Check cache
    apt_ids = [a["id"] for a in apartments_to_score]
    cache_key = self.build_score_cache_key(
        city, budget, bedrooms, bathrooms, property_type,
        move_in_date, other_preferences or "", apt_ids,
    )
    cached = None
    if self._redis:
        try:
            cached = self._redis.get(cache_key)
        except Exception:
            pass

    if cached:
        scores = json.loads(cached)
    else:
        scores = await asyncio.to_thread(
            self.claude_service.score_apartments, ...
        )
        # Cache the result
        if self._redis:
            try:
                self._redis.setex(cache_key, SCORE_CACHE_TTL, json.dumps(scores))
            except Exception:
                pass
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_claude_cache.py tests/test_scoring_service.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/services/apartment_service.py backend/tests/test_claude_cache.py
git commit -m "feat: add Redis caching for Claude scoring results (1hr TTL)"
```

---

### Task 10: Update frontend types and ApartmentCard

**Files:**
- Modify: `frontend/types/apartment.ts:46-50`
- Modify: `frontend/components/ApartmentCard.tsx:72-84`

**Step 1: Update TypeScript types**

In `frontend/types/apartment.ts`, add fields to `ApartmentWithScore`:

```typescript
export interface ApartmentWithScore extends Apartment {
  match_score: number | null;
  reasoning: string | null;
  highlights: string[];
  heuristic_score?: number;
  match_label?: string | null;
}
```

**Step 2: Update ApartmentCard badge display**

In `frontend/components/ApartmentCard.tsx`, replace the match score badge (lines 72-84):

```tsx
        {/* Match Score Badge */}
        {match_score != null ? (
          <div
            className={`absolute top-3 right-3 ${getScoreColor(
              match_score
            )} text-white px-3 py-1 rounded-full font-bold text-sm shadow-md`}
          >
            {match_score}% Match
          </div>
        ) : apartment.match_label ? (
          <div className={`absolute top-3 right-3 ${getLabelColor(apartment.match_label)} px-3 py-1 rounded-full font-bold text-sm shadow-md`}>
            {apartment.match_label}
          </div>
        ) : (
          <div className="absolute top-3 right-3 bg-gray-300 text-gray-600 px-3 py-1 rounded-full font-bold text-sm shadow-md">
            Pro
          </div>
        )}
```

Add the `getLabelColor` helper function near the top of the file (after `getScoreColor`):

```tsx
const getLabelColor = (label: string): string => {
  switch (label) {
    case 'Excellent Match': return 'bg-green-500 text-white';
    case 'Great Match': return 'bg-blue-500 text-white';
    case 'Good Match': return 'bg-slate-500 text-white';
    case 'Fair Match': return 'bg-gray-400 text-gray-800';
    default: return 'bg-gray-300 text-gray-600';
  }
};
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 5: Commit**

```bash
git add frontend/types/apartment.ts frontend/components/ApartmentCard.tsx
git commit -m "feat: display qualitative match labels for free-tier search results"
```

---

### Task 11: Full integration test and final verification

**Files:**
- No new files

**Step 1: Run all backend tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All PASS

**Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 3: Manual smoke test**

Start backend and verify the search pipeline works:

```bash
# Start backend
cd backend && source .venv/bin/activate && .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# Test anonymous search — should return heuristic-scored results
curl -s -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"city": "Philadelphia", "budget": 2000, "bedrooms": 1, "bathrooms": 1, "property_type": "Apartment", "move_in_date": "2026-04-01", "other_preferences": "gym and parking"}' | python -m json.tool

# Verify response has match_label and heuristic_score fields
# Verify apartments are sorted by heuristic_score (highest first)
# Verify match_score is null (no Claude for anonymous)
```

**Step 4: Commit final state**

```bash
git add -A
git commit -m "chore: search scoring enhancements complete — all tests passing"
```
