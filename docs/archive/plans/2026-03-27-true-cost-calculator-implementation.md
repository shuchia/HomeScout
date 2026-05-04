# True Cost Calculator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a True Cost Calculator that shows renters the real monthly cost of each listing — base rent + utilities + insurance + parking + pet rent + fees — so they can compare apartments on actual cost, not advertised rent.

**Architecture:** Precompute true cost at ingestion time using scraped fee data from Apify + static regional estimates for gaps. Store breakdown on the apartment model. Serve via existing endpoints with tier gating (free sees headline number, Pro sees full breakdown). Feed true cost data into Claude AI scoring/comparison prompts.

**Tech Stack:** Python/FastAPI (backend), Next.js/TypeScript (frontend), PostgreSQL + Alembic (DB), Celery (recompute task)

---

### Task 1: Static Cost Estimates Lookup Table

**Files:**
- Create: `backend/app/data/cost_estimates.json`

**Step 1: Create the lookup table**

Create `backend/app/data/cost_estimates.json` with this structure. Data is keyed by 3-digit zip prefix, then bedroom count. Values are monthly dollars. Include a `"default"` fallback entry.

```json
{
  "_meta": {
    "source": "EIA RECS 2022 + BLS CPI averages",
    "last_updated": "2026-03-27",
    "notes": "Estimates are monthly averages by zip prefix and bedroom count"
  },
  "default": {
    "0": {"electric": 70, "gas": 35, "water": 30, "internet": 60, "renters_insurance": 15, "laundry": 50},
    "1": {"electric": 85, "gas": 40, "water": 35, "internet": 60, "renters_insurance": 18, "laundry": 50},
    "2": {"electric": 100, "gas": 50, "water": 40, "internet": 60, "renters_insurance": 22, "laundry": 50},
    "3": {"electric": 120, "gas": 55, "water": 45, "internet": 60, "renters_insurance": 25, "laundry": 50},
    "4": {"electric": 140, "gas": 60, "water": 50, "internet": 60, "renters_insurance": 28, "laundry": 50}
  },
  "191": {
    "_region": "Philadelphia, PA",
    "0": {"electric": 75, "gas": 40, "water": 35, "internet": 60, "renters_insurance": 16, "laundry": 55},
    "1": {"electric": 90, "gas": 50, "water": 40, "internet": 60, "renters_insurance": 19, "laundry": 55},
    "2": {"electric": 110, "gas": 60, "water": 45, "internet": 60, "renters_insurance": 23, "laundry": 55},
    "3": {"electric": 130, "gas": 70, "water": 50, "internet": 60, "renters_insurance": 27, "laundry": 55},
    "4": {"electric": 150, "gas": 80, "water": 55, "internet": 60, "renters_insurance": 30, "laundry": 55}
  },
  "190": {
    "_region": "Bryn Mawr / Main Line, PA",
    "0": {"electric": 80, "gas": 45, "water": 35, "internet": 65, "renters_insurance": 17, "laundry": 55},
    "1": {"electric": 95, "gas": 55, "water": 40, "internet": 65, "renters_insurance": 20, "laundry": 55},
    "2": {"electric": 115, "gas": 65, "water": 45, "internet": 65, "renters_insurance": 24, "laundry": 55},
    "3": {"electric": 135, "gas": 75, "water": 50, "internet": 65, "renters_insurance": 28, "laundry": 55},
    "4": {"electric": 155, "gas": 85, "water": 55, "internet": 65, "renters_insurance": 32, "laundry": 55}
  },
  "152": {
    "_region": "Pittsburgh, PA",
    "0": {"electric": 65, "gas": 35, "water": 30, "internet": 55, "renters_insurance": 14, "laundry": 45},
    "1": {"electric": 80, "gas": 45, "water": 35, "internet": 55, "renters_insurance": 17, "laundry": 45},
    "2": {"electric": 95, "gas": 55, "water": 40, "internet": 55, "renters_insurance": 20, "laundry": 45},
    "3": {"electric": 115, "gas": 65, "water": 45, "internet": 55, "renters_insurance": 24, "laundry": 45},
    "4": {"electric": 135, "gas": 75, "water": 50, "internet": 55, "renters_insurance": 27, "laundry": 45}
  },
  "021": {
    "_region": "Boston, MA",
    "0": {"electric": 85, "gas": 50, "water": 35, "internet": 65, "renters_insurance": 18, "laundry": 60},
    "1": {"electric": 100, "gas": 60, "water": 40, "internet": 65, "renters_insurance": 22, "laundry": 60},
    "2": {"electric": 120, "gas": 70, "water": 50, "internet": 65, "renters_insurance": 26, "laundry": 60},
    "3": {"electric": 145, "gas": 85, "water": 55, "internet": 65, "renters_insurance": 30, "laundry": 60},
    "4": {"electric": 165, "gas": 95, "water": 60, "internet": 65, "renters_insurance": 34, "laundry": 60}
  },
  "100": {
    "_region": "New York City, NY",
    "0": {"electric": 90, "gas": 50, "water": 40, "internet": 70, "renters_insurance": 20, "laundry": 70},
    "1": {"electric": 110, "gas": 60, "water": 45, "internet": 70, "renters_insurance": 25, "laundry": 70},
    "2": {"electric": 130, "gas": 75, "water": 55, "internet": 70, "renters_insurance": 30, "laundry": 70},
    "3": {"electric": 155, "gas": 90, "water": 60, "internet": 70, "renters_insurance": 35, "laundry": 70},
    "4": {"electric": 180, "gas": 100, "water": 70, "internet": 70, "renters_insurance": 40, "laundry": 70}
  },
  "200": {
    "_region": "Washington, DC",
    "0": {"electric": 80, "gas": 45, "water": 35, "internet": 65, "renters_insurance": 17, "laundry": 55},
    "1": {"electric": 95, "gas": 55, "water": 40, "internet": 65, "renters_insurance": 21, "laundry": 55},
    "2": {"electric": 115, "gas": 65, "water": 50, "internet": 65, "renters_insurance": 25, "laundry": 55},
    "3": {"electric": 140, "gas": 80, "water": 55, "internet": 65, "renters_insurance": 29, "laundry": 55},
    "4": {"electric": 160, "gas": 90, "water": 60, "internet": 65, "renters_insurance": 33, "laundry": 55}
  },
  "212": {
    "_region": "Baltimore, MD",
    "0": {"electric": 75, "gas": 40, "water": 35, "internet": 55, "renters_insurance": 16, "laundry": 50},
    "1": {"electric": 90, "gas": 50, "water": 40, "internet": 55, "renters_insurance": 19, "laundry": 50},
    "2": {"electric": 110, "gas": 60, "water": 45, "internet": 55, "renters_insurance": 23, "laundry": 50},
    "3": {"electric": 130, "gas": 70, "water": 50, "internet": 55, "renters_insurance": 27, "laundry": 50},
    "4": {"electric": 150, "gas": 80, "water": 55, "internet": 55, "renters_insurance": 30, "laundry": 50}
  },
  "070": {
    "_region": "Newark / Jersey City, NJ",
    "0": {"electric": 80, "gas": 45, "water": 35, "internet": 65, "renters_insurance": 17, "laundry": 60},
    "1": {"electric": 95, "gas": 55, "water": 40, "internet": 65, "renters_insurance": 21, "laundry": 60},
    "2": {"electric": 115, "gas": 65, "water": 50, "internet": 65, "renters_insurance": 25, "laundry": 60},
    "3": {"electric": 140, "gas": 80, "water": 55, "internet": 65, "renters_insurance": 29, "laundry": 60},
    "4": {"electric": 160, "gas": 90, "water": 60, "internet": 65, "renters_insurance": 33, "laundry": 60}
  }
}
```

**Step 2: Commit**

```bash
git add backend/app/data/cost_estimates.json
git commit -m "feat(true-cost): add static utility cost estimates lookup table"
```

---

### Task 2: Cost Estimator Service

**Files:**
- Create: `backend/app/services/cost_estimator.py`
- Test: `backend/tests/test_cost_estimator.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_cost_estimator.py`:

```python
"""Tests for the cost estimator service."""
import pytest
from app.services.cost_estimator import CostEstimator


class TestCostEstimator:
    """Test the CostEstimator service."""

    def setup_method(self):
        self.estimator = CostEstimator()

    def test_lookup_known_zip(self):
        """Zip prefix 152 (Pittsburgh) should return Pittsburgh-specific estimates."""
        result = self.estimator.get_estimates(zip_code="15213", bedrooms=1)
        assert result["electric"] == 80
        assert result["gas"] == 45
        assert result["renters_insurance"] == 17

    def test_lookup_unknown_zip_falls_back_to_default(self):
        """Unknown zip prefix should fall back to default estimates."""
        result = self.estimator.get_estimates(zip_code="99999", bedrooms=1)
        assert result["electric"] == 85  # default 1BR

    def test_missing_zip_falls_back_to_default(self):
        """None zip code should fall back to default."""
        result = self.estimator.get_estimates(zip_code=None, bedrooms=2)
        assert result["electric"] == 100  # default 2BR

    def test_bedroom_count_caps_at_4(self):
        """Bedrooms > 4 should use the 4BR estimates."""
        result = self.estimator.get_estimates(zip_code="15213", bedrooms=6)
        assert result["electric"] == 135  # Pittsburgh 4BR

    def test_compute_true_cost_basic(self):
        """Compute true cost with no scraped fees and nothing included."""
        breakdown = self.estimator.compute_true_cost(
            rent=1500,
            zip_code="15213",
            bedrooms=1,
            amenities=[],
            scraped_fees={},
        )
        assert breakdown["base_rent"] == 1500
        assert breakdown["true_cost_monthly"] > 1500
        assert breakdown["est_electric"] == 80
        assert breakdown["est_laundry"] == 45  # Pittsburgh 1BR laundry

    def test_utilities_included_zeroes_estimates(self):
        """When amenities indicate utilities included, those estimates should be 0."""
        breakdown = self.estimator.compute_true_cost(
            rent=1500,
            zip_code="15213",
            bedrooms=1,
            amenities=["Heat Included", "Water Included"],
            scraped_fees={},
        )
        assert breakdown["est_gas"] == 0  # heat = gas, included
        assert breakdown["est_water"] == 0  # water included
        assert breakdown["est_electric"] == 80  # NOT included

    def test_in_unit_laundry_zeroes_laundry(self):
        """In-unit washer/dryer should zero out laundry estimate."""
        breakdown = self.estimator.compute_true_cost(
            rent=1500,
            zip_code="15213",
            bedrooms=1,
            amenities=["In-Unit Washer/Dryer"],
            scraped_fees={},
        )
        assert breakdown["est_laundry"] == 0

    def test_scraped_fees_included(self):
        """Scraped pet rent and parking should appear in breakdown and total."""
        breakdown = self.estimator.compute_true_cost(
            rent=1500,
            zip_code="15213",
            bedrooms=1,
            amenities=[],
            scraped_fees={"pet_rent": 50, "parking_fee": 150, "amenity_fee": 40},
        )
        assert breakdown["pet_rent"] == 50
        assert breakdown["parking_fee"] == 150
        assert breakdown["amenity_fee"] == 40
        assert breakdown["true_cost_monthly"] == (
            1500 + 50 + 150 + 40
            + breakdown["est_electric"] + breakdown["est_gas"]
            + breakdown["est_water"] + breakdown["est_internet"]
            + breakdown["est_renters_insurance"] + breakdown["est_laundry"]
        )

    def test_move_in_cost(self):
        """Move-in cost should include application fee + deposit + first month."""
        breakdown = self.estimator.compute_true_cost(
            rent=1500,
            zip_code="15213",
            bedrooms=1,
            amenities=[],
            scraped_fees={"application_fee": 50, "security_deposit": 1500},
        )
        assert breakdown["application_fee"] == 50
        assert breakdown["security_deposit"] == 1500
        assert breakdown["true_cost_move_in"] == (
            50 + 1500 + breakdown["true_cost_monthly"]
        )

    def test_sources_tracking(self):
        """Sources dict should correctly categorize scraped vs estimated vs included."""
        breakdown = self.estimator.compute_true_cost(
            rent=1500,
            zip_code="15213",
            bedrooms=1,
            amenities=["Water Included"],
            scraped_fees={"pet_rent": 50},
        )
        assert "pet_rent" in breakdown["sources"]["scraped"]
        assert "est_electric" in breakdown["sources"]["estimated"]
        assert "water" in breakdown["sources"]["included"]

    def test_all_utilities_included(self):
        """When all utilities included, all utility estimates should be 0."""
        breakdown = self.estimator.compute_true_cost(
            rent=2000,
            zip_code="15213",
            bedrooms=2,
            amenities=["Utilities Included"],
            scraped_fees={},
        )
        assert breakdown["est_electric"] == 0
        assert breakdown["est_gas"] == 0
        assert breakdown["est_water"] == 0
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_cost_estimator.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.cost_estimator'`

**Step 3: Implement the cost estimator**

Create `backend/app/services/cost_estimator.py`:

```python
"""
Service for estimating true monthly cost of apartment listings.

Combines scraped fee data with regional utility/insurance estimates
to compute a realistic total monthly cost.
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Amenity strings that indicate utilities are included
_HEAT_INCLUDED = {"heat included", "heating included", "gas included"}
_WATER_INCLUDED = {"water included", "water/sewer included"}
_ELECTRIC_INCLUDED = {"electric included", "electricity included"}
_ALL_UTILITIES = {"utilities included", "all utilities included"}
_IN_UNIT_LAUNDRY = {
    "in-unit washer/dryer",
    "in-unit laundry",
    "washer/dryer in unit",
    "washer/dryer",
    "washer & dryer",
    "washer and dryer",
    "w/d in unit",
}


class CostEstimator:
    """Estimates true monthly apartment cost using scraped fees + regional averages."""

    def __init__(self):
        data_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "cost_estimates.json"
        )
        with open(data_path) as f:
            self._data = json.load(f)
        self._default = self._data["default"]

    def get_estimates(
        self, zip_code: Optional[str], bedrooms: int
    ) -> Dict[str, int]:
        """Look up regional cost estimates by zip prefix and bedroom count.

        Fallback chain: 3-digit zip prefix -> default -> raise.
        Bedroom count capped at 4.
        """
        bed_key = str(min(bedrooms, 4))

        if zip_code and len(zip_code) >= 3:
            prefix = zip_code[:3]
            region = self._data.get(prefix)
            if region and bed_key in region:
                return dict(region[bed_key])

        return dict(self._default[bed_key])

    def compute_true_cost(
        self,
        rent: int,
        zip_code: Optional[str],
        bedrooms: int,
        amenities: List[str],
        scraped_fees: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compute full cost breakdown for a listing.

        Args:
            rent: Base monthly rent.
            zip_code: Listing zip code (for regional estimates).
            bedrooms: Bedroom count.
            amenities: List of amenity strings from the listing.
            scraped_fees: Dict of fees extracted from scraping. Keys:
                pet_rent, parking_fee, amenity_fee (monthly),
                application_fee, security_deposit (one-time).

        Returns:
            Dict with all cost line items, totals, and source tracking.
        """
        estimates = self.get_estimates(zip_code, bedrooms)
        amenity_set = {a.lower().strip() for a in amenities}

        # Determine which utilities are included
        all_included = bool(amenity_set & _ALL_UTILITIES)
        heat_included = all_included or bool(amenity_set & _HEAT_INCLUDED)
        water_included = all_included or bool(amenity_set & _WATER_INCLUDED)
        electric_included = all_included or bool(amenity_set & _ELECTRIC_INCLUDED)
        has_in_unit_laundry = bool(amenity_set & _IN_UNIT_LAUNDRY)

        # Build estimates (zero out included utilities)
        est_electric = 0 if electric_included else estimates["electric"]
        est_gas = 0 if heat_included else estimates["gas"]
        est_water = 0 if water_included else estimates["water"]
        est_internet = estimates["internet"]
        est_renters_insurance = estimates["renters_insurance"]
        est_laundry = 0 if has_in_unit_laundry else estimates["laundry"]

        # Scraped monthly fees (default to 0 if not scraped)
        pet_rent = scraped_fees.get("pet_rent") or 0
        parking_fee = scraped_fees.get("parking_fee") or 0
        amenity_fee = scraped_fees.get("amenity_fee") or 0

        # One-time fees
        application_fee = scraped_fees.get("application_fee") or 0
        security_deposit = scraped_fees.get("security_deposit") or 0

        # Compute totals
        monthly_extras = (
            pet_rent + parking_fee + amenity_fee
            + est_electric + est_gas + est_water
            + est_internet + est_renters_insurance + est_laundry
        )
        true_cost_monthly = rent + monthly_extras
        true_cost_move_in = application_fee + security_deposit + true_cost_monthly

        # Track data sources for transparency
        scraped_sources = [
            k for k in ("pet_rent", "parking_fee", "amenity_fee")
            if scraped_fees.get(k)
        ]
        estimated_sources = [
            name for name, val in [
                ("est_electric", est_electric),
                ("est_gas", est_gas),
                ("est_water", est_water),
                ("est_internet", est_internet),
                ("est_renters_insurance", est_renters_insurance),
                ("est_laundry", est_laundry),
            ]
            if val > 0
        ]
        included_sources = []
        if electric_included:
            included_sources.append("electric")
        if heat_included:
            included_sources.append("heat")
        if water_included:
            included_sources.append("water")
        if has_in_unit_laundry:
            included_sources.append("laundry")

        return {
            "base_rent": rent,
            "pet_rent": pet_rent,
            "parking_fee": parking_fee,
            "amenity_fee": amenity_fee,
            "est_electric": est_electric,
            "est_gas": est_gas,
            "est_water": est_water,
            "est_internet": est_internet,
            "est_renters_insurance": est_renters_insurance,
            "est_laundry": est_laundry,
            "application_fee": application_fee,
            "security_deposit": security_deposit,
            "true_cost_monthly": true_cost_monthly,
            "true_cost_move_in": true_cost_move_in,
            "sources": {
                "scraped": scraped_sources,
                "estimated": estimated_sources,
                "included": included_sources,
            },
        }
```

**Step 4: Run tests to verify they pass**

```bash
cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_cost_estimator.py -v
```

Expected: All 11 tests PASS.

**Step 5: Commit**

```bash
git add backend/app/services/cost_estimator.py backend/tests/test_cost_estimator.py
git commit -m "feat(true-cost): add cost estimator service with regional lookup tables"
```

---

### Task 3: Database Migration — Add True Cost Columns

**Files:**
- Create: `backend/alembic/versions/<auto>_add_true_cost_columns.py` (via autogenerate)
- Modify: `backend/app/models/apartment.py:16-89`

**Step 1: Add columns to ApartmentModel**

In `backend/app/models/apartment.py`, add after the `images_cached` column (line 53):

```python
    # True cost fields (scraped fees)
    pet_rent = Column(Integer, nullable=True)
    parking_fee = Column(Integer, nullable=True)
    amenity_fee = Column(Integer, nullable=True)
    application_fee = Column(Integer, nullable=True)
    security_deposit = Column(Integer, nullable=True)

    # True cost fields (estimated)
    est_electric = Column(Integer, nullable=True)
    est_gas = Column(Integer, nullable=True)
    est_water = Column(Integer, nullable=True)
    est_internet = Column(Integer, nullable=True)
    est_renters_insurance = Column(Integer, nullable=True)
    est_laundry = Column(Integer, nullable=True)

    # True cost flags and totals
    utilities_included = Column(JSONB, nullable=True)  # {"heat": true, "water": true, ...}
    true_cost_monthly = Column(Integer, nullable=True)
    true_cost_move_in = Column(Integer, nullable=True)
```

**Step 2: Update `to_dict()` to include true cost fields**

In the same file, update the `to_dict()` method to include:

```python
    def to_dict(self) -> dict:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "address": self.address,
            "rent": self.rent,
            "bedrooms": self.bedrooms,
            "bathrooms": int(self.bathrooms) if self.bathrooms == int(self.bathrooms) else self.bathrooms,
            "sqft": self.sqft or 0,
            "property_type": self.property_type,
            "available_date": self.available_date or "",
            "amenities": self.amenities or [],
            "neighborhood": self.neighborhood or "",
            "description": self.description or "",
            "images": self.images_cached if self.images_cached else (self.images or []),
            # Additional fields for detailed view
            "city": self.city,
            "state": self.state,
            "zip_code": self.zip_code,
            "source": self.source,
            "source_url": self.source_url,
            "data_quality_score": self.data_quality_score,
            "freshness_confidence": self.freshness_confidence,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "times_seen": self.times_seen,
            # True cost fields
            "true_cost_monthly": self.true_cost_monthly,
            "true_cost_move_in": self.true_cost_move_in,
            "pet_rent": self.pet_rent,
            "parking_fee": self.parking_fee,
            "amenity_fee": self.amenity_fee,
            "application_fee": self.application_fee,
            "security_deposit": self.security_deposit,
            "est_electric": self.est_electric,
            "est_gas": self.est_gas,
            "est_water": self.est_water,
            "est_internet": self.est_internet,
            "est_renters_insurance": self.est_renters_insurance,
            "est_laundry": self.est_laundry,
            "utilities_included": self.utilities_included,
        }
```

**Step 3: Generate and run the Alembic migration**

```bash
cd backend && source .venv/bin/activate && alembic revision --autogenerate -m "add true cost columns"
```

Review the generated migration, then:

```bash
alembic upgrade head
```

**Step 4: Commit**

```bash
git add backend/app/models/apartment.py backend/alembic/versions/*add_true_cost*
git commit -m "feat(true-cost): add true cost columns to ApartmentModel + migration"
```

---

### Task 4: Extract Fees from Apify Raw Data

**Files:**
- Modify: `backend/app/services/scrapers/apify_service.py:439-525`
- Modify: `backend/app/services/scrapers/base_scraper.py:22-56`

**Step 1: Add fee fields to ScrapedListing dataclass**

In `backend/app/services/scrapers/base_scraper.py`, add after `source_url` (line 50):

```python
    # Fee fields (extracted from listing)
    pet_rent: Optional[int] = None
    parking_fee: Optional[int] = None
    amenity_fee: Optional[int] = None
    application_fee: Optional[int] = None
    security_deposit: Optional[int] = None
```

Update the `to_dict()` method in the same file to include these fields.

**Step 2: Extract fees in `_normalize_apartments_com_listing()`**

In `backend/app/services/scrapers/apify_service.py`, add fee extraction before the `return ScrapedListing(...)` call (around line 503). Apartments.com raw data typically has fees in a `fees` or `oneTimeFees`/`monthlyFees` structure:

```python
        # Extract fee data from raw listing
        pet_rent = None
        parking_fee = None
        amenity_fee = None
        application_fee = None
        security_deposit = None

        # Try structured fee fields
        monthly_fees = raw.get("monthlyFees") or raw.get("fees", {}).get("monthly", [])
        one_time_fees = raw.get("oneTimeFees") or raw.get("fees", {}).get("oneTime", [])

        if isinstance(monthly_fees, list):
            for fee in monthly_fees:
                if isinstance(fee, dict):
                    name = (fee.get("name") or fee.get("label") or "").lower()
                    amount = self._parse_fee_amount(fee.get("amount") or fee.get("value"))
                    if amount and ("pet" in name or "dog" in name or "cat" in name):
                        pet_rent = amount
                    elif amount and "parking" in name:
                        parking_fee = amount
                    elif amount and ("amenity" in name or "community" in name or "trash" in name):
                        amenity_fee = (amenity_fee or 0) + amount

        if isinstance(one_time_fees, list):
            for fee in one_time_fees:
                if isinstance(fee, dict):
                    name = (fee.get("name") or fee.get("label") or "").lower()
                    amount = self._parse_fee_amount(fee.get("amount") or fee.get("value"))
                    if amount and ("application" in name or "admin" in name):
                        application_fee = amount
                    elif amount and ("deposit" in name or "security" in name):
                        security_deposit = amount

        # Also check petPolicy for pet rent
        pet_policy = raw.get("petPolicy") or raw.get("pets") or {}
        if isinstance(pet_policy, dict) and not pet_rent:
            pet_fee = self._parse_fee_amount(
                pet_policy.get("monthlyPetRent") or pet_policy.get("rent")
            )
            if pet_fee:
                pet_rent = pet_fee
```

Add these fields to the `ScrapedListing(...)` constructor call:

```python
        return ScrapedListing(
            # ... existing fields ...
            pet_rent=pet_rent,
            parking_fee=parking_fee,
            amenity_fee=amenity_fee,
            application_fee=application_fee,
            security_deposit=security_deposit,
        )
```

**Step 3: Add `_parse_fee_amount` helper method**

Add to the `ApifyService` class:

```python
    @staticmethod
    def _parse_fee_amount(value: Any) -> Optional[int]:
        """Parse a fee amount from various formats (int, float, string like '$50')."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return int(value) if value > 0 else None
        if isinstance(value, str):
            import re
            match = re.search(r"[\d,]+(?:\.\d+)?", value.replace(",", ""))
            if match:
                parsed = int(float(match.group()))
                return parsed if parsed > 0 else None
        return None
```

**Step 4: Commit**

```bash
git add backend/app/services/scrapers/base_scraper.py backend/app/services/scrapers/apify_service.py
git commit -m "feat(true-cost): extract fee data from Apify apartments.com listings"
```

---

### Task 5: Integrate Cost Estimator into Normalization Pipeline

**Files:**
- Modify: `backend/app/services/normalization/normalizer.py:75-161`

**Step 1: Add true cost computation to the normalization pipeline**

In `backend/app/services/normalization/normalizer.py`, add an import at the top:

```python
from app.services.cost_estimator import CostEstimator
```

Add the estimator to `__init__`:

```python
    def __init__(self):
        self.address_standardizer = AddressStandardizer()
        self.cost_estimator = CostEstimator()
```

Add a new step after Step 9 (clean description) and before Step 10 (calculate quality score) in the `normalize()` method:

```python
        # Step 10: Compute true cost breakdown
        scraped_fees = {
            "pet_rent": data.get("pet_rent"),
            "parking_fee": data.get("parking_fee"),
            "amenity_fee": data.get("amenity_fee"),
            "application_fee": data.get("application_fee"),
            "security_deposit": data.get("security_deposit"),
        }
        try:
            cost_breakdown = self.cost_estimator.compute_true_cost(
                rent=data["rent"],
                zip_code=data.get("zip_code"),
                bedrooms=data["bedrooms"],
                amenities=data.get("amenities", []),
                scraped_fees=scraped_fees,
            )
            data["true_cost_monthly"] = cost_breakdown["true_cost_monthly"]
            data["true_cost_move_in"] = cost_breakdown["true_cost_move_in"]
            data["est_electric"] = cost_breakdown["est_electric"]
            data["est_gas"] = cost_breakdown["est_gas"]
            data["est_water"] = cost_breakdown["est_water"]
            data["est_internet"] = cost_breakdown["est_internet"]
            data["est_renters_insurance"] = cost_breakdown["est_renters_insurance"]
            data["est_laundry"] = cost_breakdown["est_laundry"]
            data["utilities_included"] = {
                "heat": cost_breakdown["est_gas"] == 0 and not scraped_fees.get("est_gas"),
                "water": cost_breakdown["est_water"] == 0 and not scraped_fees.get("est_water"),
                "electric": cost_breakdown["est_electric"] == 0 and not scraped_fees.get("est_electric"),
            }
        except Exception as e:
            logger.warning(f"Failed to compute true cost: {e}")
            # Non-fatal — listing proceeds without true cost data
```

Renumber the quality score step to Step 11.

**Step 2: Run existing tests to ensure no regressions**

```bash
cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v -k "not test_apartments_router"
```

**Step 3: Commit**

```bash
git add backend/app/services/normalization/normalizer.py
git commit -m "feat(true-cost): integrate cost estimator into normalization pipeline"
```

---

### Task 6: Backend Schema & Tier Gating

**Files:**
- Modify: `backend/app/schemas.py:30-62`
- Modify: `backend/app/routers/apartments.py`
- Modify: `backend/app/main.py:149-260`
- Test: `backend/tests/test_true_cost_gating.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_true_cost_gating.py`:

```python
"""Tests for true cost tier gating in API responses."""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestTrueCostGating:
    """Verify cost_breakdown is gated by tier."""

    def _make_apartment(self, **overrides):
        base = {
            "id": "test-001",
            "address": "123 Test St, Pittsburgh, PA 15213",
            "rent": 1500,
            "bedrooms": 1,
            "bathrooms": 1,
            "sqft": 700,
            "property_type": "Apartment",
            "available_date": "2026-04-01",
            "amenities": [],
            "neighborhood": "Oakland",
            "description": "Test apartment",
            "images": [],
            "true_cost_monthly": 1800,
            "true_cost_move_in": 3600,
            "pet_rent": 50,
            "parking_fee": 100,
            "amenity_fee": 0,
            "application_fee": 50,
            "security_deposit": 1500,
            "est_electric": 80,
            "est_gas": 45,
            "est_water": 35,
            "est_internet": 55,
            "est_renters_insurance": 17,
            "est_laundry": 45,
            "utilities_included": {"heat": False, "water": False, "electric": False},
        }
        base.update(overrides)
        return base

    @patch("app.main.apartment_service.search_apartments", new_callable=AsyncMock)
    def test_free_user_gets_true_cost_totals_no_breakdown(self, mock_search):
        """Free users see true_cost_monthly but not cost_breakdown."""
        mock_search.return_value = [self._make_apartment()]

        with patch("app.auth.get_optional_user") as mock_user, \
             patch("app.services.tier_service.TierService.get_user_tier", new_callable=AsyncMock, return_value="free"), \
             patch("app.services.tier_service.TierService.check_search_limit", new_callable=AsyncMock, return_value=(True, 2)), \
             patch("app.services.tier_service.TierService.increment_search_count", new_callable=AsyncMock):
            from app.auth import UserContext
            mock_user.return_value = UserContext(user_id="user-1", email="test@test.com")

            response = client.post("/api/search", json={
                "city": "Pittsburgh",
                "budget": 2000,
                "bedrooms": 1,
                "bathrooms": 1,
                "property_type": "Apartment",
                "move_in_date": "2026-04-01",
            })

            assert response.status_code == 200
            apt = response.json()["apartments"][0]
            assert apt["true_cost_monthly"] == 1800
            assert apt.get("cost_breakdown") is None

    @patch("app.routers.apartments._get_apartments_data")
    def test_anonymous_gets_true_cost_totals(self, mock_data):
        """Anonymous users see true_cost_monthly on apartment detail."""
        mock_data.return_value = [self._make_apartment()]

        response = client.get("/api/apartments/test-001")
        assert response.status_code == 200
        data = response.json()
        assert data["true_cost_monthly"] == 1800
        assert data.get("cost_breakdown") is None
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_true_cost_gating.py -v
```

**Step 3: Add `CostBreakdown` schema to `schemas.py`**

Add after the `Apartment` class in `backend/app/schemas.py`:

```python
class CostSources(BaseModel):
    """Tracks which costs are scraped vs estimated vs included."""
    scraped: List[str] = Field(default_factory=list)
    estimated: List[str] = Field(default_factory=list)
    included: List[str] = Field(default_factory=list)


class CostBreakdown(BaseModel):
    """Full cost breakdown for Pro users."""
    base_rent: int
    pet_rent: int = 0
    parking_fee: int = 0
    amenity_fee: int = 0
    est_electric: int = 0
    est_gas: int = 0
    est_water: int = 0
    est_internet: int = 0
    est_renters_insurance: int = 0
    est_laundry: int = 0
    application_fee: int = 0
    security_deposit: int = 0
    sources: CostSources = Field(default_factory=CostSources)
```

Update the `Apartment` schema to include true cost headline fields:

```python
class Apartment(BaseModel):
    """Model for apartment listing"""
    id: str
    address: str
    rent: int
    bedrooms: int
    bathrooms: int
    sqft: int
    property_type: str
    available_date: str
    amenities: List[str]
    neighborhood: str
    description: str
    images: List[str]
    # True cost headline fields (available to all tiers)
    true_cost_monthly: Optional[int] = None
    true_cost_move_in: Optional[int] = None
    # Full breakdown (Pro only — populated by API layer)
    cost_breakdown: Optional[CostBreakdown] = None
```

**Step 4: Add tier-gated `cost_breakdown` population to API responses**

Create a helper function in `backend/app/routers/apartments.py`:

```python
from app.services.cost_estimator import CostEstimator

_cost_estimator = CostEstimator()


def _add_cost_breakdown(apartment: dict, include_breakdown: bool) -> dict:
    """Add true cost fields to apartment dict. Full breakdown only if include_breakdown=True."""
    # Ensure headline fields are present
    if apartment.get("true_cost_monthly") is None and apartment.get("rent"):
        # Compute on the fly for JSON mode or backfill
        breakdown = _cost_estimator.compute_true_cost(
            rent=apartment["rent"],
            zip_code=apartment.get("zip_code"),
            bedrooms=apartment.get("bedrooms", 1),
            amenities=apartment.get("amenities", []),
            scraped_fees={
                "pet_rent": apartment.get("pet_rent"),
                "parking_fee": apartment.get("parking_fee"),
                "amenity_fee": apartment.get("amenity_fee"),
                "application_fee": apartment.get("application_fee"),
                "security_deposit": apartment.get("security_deposit"),
            },
        )
        apartment["true_cost_monthly"] = breakdown["true_cost_monthly"]
        apartment["true_cost_move_in"] = breakdown["true_cost_move_in"]

        if include_breakdown:
            apartment["cost_breakdown"] = breakdown
    elif include_breakdown and apartment.get("true_cost_monthly"):
        # Build breakdown from stored fields
        apartment["cost_breakdown"] = {
            "base_rent": apartment["rent"],
            "pet_rent": apartment.get("pet_rent") or 0,
            "parking_fee": apartment.get("parking_fee") or 0,
            "amenity_fee": apartment.get("amenity_fee") or 0,
            "est_electric": apartment.get("est_electric") or 0,
            "est_gas": apartment.get("est_gas") or 0,
            "est_water": apartment.get("est_water") or 0,
            "est_internet": apartment.get("est_internet") or 0,
            "est_renters_insurance": apartment.get("est_renters_insurance") or 0,
            "est_laundry": apartment.get("est_laundry") or 0,
            "application_fee": apartment.get("application_fee") or 0,
            "security_deposit": apartment.get("security_deposit") or 0,
            "sources": _build_sources(apartment),
        }

    return apartment


def _build_sources(apartment: dict) -> dict:
    scraped = [k for k in ("pet_rent", "parking_fee", "amenity_fee") if apartment.get(k)]
    estimated = [
        f"est_{k}" for k in ("electric", "gas", "water", "internet", "renters_insurance", "laundry")
        if apartment.get(f"est_{k}")
    ]
    included_map = apartment.get("utilities_included") or {}
    included = [k for k, v in included_map.items() if v]
    return {"scraped": scraped, "estimated": estimated, "included": included}
```

Apply `_add_cost_breakdown` in the compare endpoint and apartment detail/batch/list endpoints by calling it on each apartment dict before returning. The `include_breakdown` flag should be `True` only when `tier == "pro"`.

Similarly, in `backend/app/main.py`, apply it in the search endpoint for each apartment in the response.

**Step 5: Run tests**

```bash
cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_true_cost_gating.py tests/test_cost_estimator.py -v
```

**Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/apartments.py backend/app/main.py backend/tests/test_true_cost_gating.py
git commit -m "feat(true-cost): add CostBreakdown schema and tier-gated API responses"
```

---

### Task 7: Claude AI Integration

**Files:**
- Modify: `backend/app/services/claude_service.py:20-37` (`prepare_apartment_for_scoring`)
- Modify: `backend/app/services/claude_service.py:110-134` (system prompt)

**Step 1: Update `prepare_apartment_for_scoring` to include true cost data**

In `backend/app/services/claude_service.py`, update the method:

```python
    @staticmethod
    def prepare_apartment_for_scoring(apt: dict) -> dict:
        """Prepare apartment data for Claude scoring. No truncation."""
        data = {
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
        # Include true cost data if available
        if apt.get("true_cost_monthly"):
            data["true_cost_monthly"] = apt["true_cost_monthly"]
            data["true_cost_move_in"] = apt.get("true_cost_move_in")
            data["cost_details"] = {
                "pet_rent": apt.get("pet_rent") or 0,
                "parking_fee": apt.get("parking_fee") or 0,
                "amenity_fee": apt.get("amenity_fee") or 0,
                "est_utilities": (
                    (apt.get("est_electric") or 0)
                    + (apt.get("est_gas") or 0)
                    + (apt.get("est_water") or 0)
                ),
                "est_internet": apt.get("est_internet") or 0,
                "est_renters_insurance": apt.get("est_renters_insurance") or 0,
                "est_laundry": apt.get("est_laundry") or 0,
            }
        return data
```

**Step 2: Update the scoring system prompt**

In the `score_apartments` method, add to the system prompt's analysis criteria:

```
7. True monthly cost (if available): Consider the estimated true cost including utilities, fees, and insurance — not just the advertised rent. When true_cost_monthly is provided, use it for budget fit analysis instead of just rent. Highlight cases where advertised rent is significantly lower than true cost.
```

**Step 3: Update the comparison system prompt**

In `compare_apartments_with_analysis`, update the system prompt:

```
You are an expert apartment comparison analyst for Snugd. Compare apartments head-to-head across multiple categories, considering the user's stated preferences and search criteria. When true_cost_monthly data is available, use it for value comparisons — the advertised rent is often not the real price. Highlight cost differences that aren't obvious from rent alone. Be specific and practical in your analysis. Scores should reflect genuine differences — don't give similar scores unless apartments are truly comparable in that category.
```

**Step 4: Run existing Claude-related tests**

```bash
cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_claude_data.py -v
```

**Step 5: Commit**

```bash
git add backend/app/services/claude_service.py
git commit -m "feat(true-cost): feed true cost data into Claude scoring and comparison prompts"
```

---

### Task 8: Celery Recompute Task

**Files:**
- Create: `backend/app/tasks/true_cost_tasks.py`
- Modify: `backend/app/celery_app.py`

**Step 1: Create the recompute task**

Create `backend/app/tasks/true_cost_tasks.py`:

```python
"""Celery tasks for recomputing true cost estimates."""
import logging
from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="recompute_true_costs", bind=True)
def recompute_true_costs(self):
    """Recompute true cost estimates for all active listings.

    Run this after updating cost_estimates.json or changing the
    estimation logic. Processes listings in batches.
    """
    import asyncio
    from sqlalchemy import select, update
    from app.database import get_session_context
    from app.models.apartment import ApartmentModel
    from app.services.cost_estimator import CostEstimator

    estimator = CostEstimator()
    batch_size = 100
    updated = 0

    async def _recompute():
        nonlocal updated
        async with get_session_context() as session:
            # Get all active listings
            stmt = (
                select(ApartmentModel)
                .where(ApartmentModel.is_active == 1)
                .order_by(ApartmentModel.id)
            )
            result = await session.execute(stmt)
            apartments = result.scalars().all()

            for apt in apartments:
                scraped_fees = {
                    "pet_rent": apt.pet_rent,
                    "parking_fee": apt.parking_fee,
                    "amenity_fee": apt.amenity_fee,
                    "application_fee": apt.application_fee,
                    "security_deposit": apt.security_deposit,
                }
                breakdown = estimator.compute_true_cost(
                    rent=apt.rent,
                    zip_code=apt.zip_code,
                    bedrooms=apt.bedrooms,
                    amenities=apt.amenities or [],
                    scraped_fees=scraped_fees,
                )
                apt.true_cost_monthly = breakdown["true_cost_monthly"]
                apt.true_cost_move_in = breakdown["true_cost_move_in"]
                apt.est_electric = breakdown["est_electric"]
                apt.est_gas = breakdown["est_gas"]
                apt.est_water = breakdown["est_water"]
                apt.est_internet = breakdown["est_internet"]
                apt.est_renters_insurance = breakdown["est_renters_insurance"]
                apt.est_laundry = breakdown["est_laundry"]
                apt.utilities_included = {
                    "heat": breakdown["est_gas"] == 0,
                    "water": breakdown["est_water"] == 0,
                    "electric": breakdown["est_electric"] == 0,
                }
                updated += 1

            await session.commit()

    asyncio.get_event_loop().run_until_complete(_recompute())
    logger.info(f"Recomputed true costs for {updated} listings")
    return {"updated": updated}
```

**Step 2: Register the task import in celery_app.py**

In `backend/app/celery_app.py`, ensure `app.tasks.true_cost_tasks` is included in the `include` list for task autodiscovery.

**Step 3: Commit**

```bash
git add backend/app/tasks/true_cost_tasks.py backend/app/celery_app.py
git commit -m "feat(true-cost): add Celery task for recomputing true cost estimates"
```

---

### Task 9: Frontend Types & API Client

**Files:**
- Modify: `frontend/types/apartment.ts:24-40`
- Modify: `frontend/lib/api.ts`

**Step 1: Update TypeScript types**

In `frontend/types/apartment.ts`, add after the `Apartment` interface:

```typescript
/**
 * Source tracking for cost estimates
 */
export interface CostSources {
  scraped: string[];
  estimated: string[];
  included: string[];
}

/**
 * Full cost breakdown (Pro users only)
 */
export interface CostBreakdown {
  base_rent: number;
  pet_rent: number;
  parking_fee: number;
  amenity_fee: number;
  est_electric: number;
  est_gas: number;
  est_water: number;
  est_internet: number;
  est_renters_insurance: number;
  est_laundry: number;
  application_fee: number;
  security_deposit: number;
  sources: CostSources;
}
```

Update the `Apartment` interface to include:

```typescript
export interface Apartment {
  // ... existing fields ...
  true_cost_monthly?: number | null;
  true_cost_move_in?: number | null;
  cost_breakdown?: CostBreakdown | null;
}
```

**Step 2: Commit**

```bash
git add frontend/types/apartment.ts frontend/lib/api.ts
git commit -m "feat(true-cost): add frontend TypeScript types for cost breakdown"
```

---

### Task 10: ApartmentCard True Cost Display

**Files:**
- Modify: `frontend/components/ApartmentCard.tsx`
- Create: `frontend/components/CostBreakdownPanel.tsx`

**Step 1: Create CostBreakdownPanel component**

Create `frontend/components/CostBreakdownPanel.tsx`:

```tsx
'use client';

import { CostBreakdown } from '@/types/apartment';

interface CostBreakdownPanelProps {
  breakdown: CostBreakdown;
}

const formatCost = (amount: number): string => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(amount);
};

interface LineItemProps {
  label: string;
  amount: number;
  source: 'scraped' | 'estimated' | 'included';
}

function LineItem({ label, amount, source }: LineItemProps) {
  if (source === 'included') {
    return (
      <div className="flex justify-between items-center text-sm py-1">
        <span className="text-gray-600">{label}</span>
        <span className="text-green-600 font-medium">Included</span>
      </div>
    );
  }
  if (amount === 0) return null;
  return (
    <div className="flex justify-between items-center text-sm py-1">
      <span className="text-gray-600 flex items-center gap-1.5">
        {label}
        <span
          className={`inline-block w-1.5 h-1.5 rounded-full ${
            source === 'scraped' ? 'bg-blue-500' : 'bg-gray-400'
          }`}
          title={source === 'scraped' ? 'From listing' : 'Regional estimate'}
        />
      </span>
      <span className="text-gray-900">{formatCost(amount)}</span>
    </div>
  );
}

export default function CostBreakdownPanel({ breakdown }: CostBreakdownPanelProps) {
  const { sources } = breakdown;
  const monthlyTotal =
    breakdown.base_rent +
    breakdown.pet_rent +
    breakdown.parking_fee +
    breakdown.amenity_fee +
    breakdown.est_electric +
    breakdown.est_gas +
    breakdown.est_water +
    breakdown.est_internet +
    breakdown.est_renters_insurance +
    breakdown.est_laundry;

  const moveInTotal =
    breakdown.application_fee + breakdown.security_deposit + monthlyTotal;

  const isIncluded = (utility: string) => sources.included.includes(utility);

  return (
    <div className="space-y-3 pt-2">
      {/* Monthly Costs */}
      <div className="space-y-0.5">
        <LineItem label="Base Rent" amount={breakdown.base_rent} source="scraped" />
        {breakdown.pet_rent > 0 && (
          <LineItem label="Pet Rent" amount={breakdown.pet_rent} source="scraped" />
        )}
        {breakdown.parking_fee > 0 && (
          <LineItem label="Parking" amount={breakdown.parking_fee} source="scraped" />
        )}
        {breakdown.amenity_fee > 0 && (
          <LineItem label="Amenity Fee" amount={breakdown.amenity_fee} source="scraped" />
        )}

        <div className="border-t border-gray-100 my-1" />

        {isIncluded("electric") ? (
          <LineItem label="Electric" amount={0} source="included" />
        ) : (
          <LineItem label="Electric" amount={breakdown.est_electric} source="estimated" />
        )}
        {isIncluded("heat") ? (
          <LineItem label="Heat/Gas" amount={0} source="included" />
        ) : (
          <LineItem label="Heat/Gas" amount={breakdown.est_gas} source="estimated" />
        )}
        {isIncluded("water") ? (
          <LineItem label="Water" amount={0} source="included" />
        ) : (
          <LineItem label="Water" amount={breakdown.est_water} source="estimated" />
        )}
        <LineItem label="Internet" amount={breakdown.est_internet} source="estimated" />
        <LineItem label="Renter's Insurance" amount={breakdown.est_renters_insurance} source="estimated" />
        {isIncluded("laundry") ? (
          <LineItem label="Laundry" amount={0} source="included" />
        ) : (
          <LineItem label="Laundry" amount={breakdown.est_laundry} source="estimated" />
        )}
      </div>

      {/* Monthly Total */}
      <div className="flex justify-between items-center border-t border-gray-200 pt-2">
        <span className="font-semibold text-gray-900 text-sm">Est. Monthly Total</span>
        <span className="font-bold text-gray-900">{formatCost(monthlyTotal)}</span>
      </div>

      {/* Move-in Costs (if any one-time fees exist) */}
      {(breakdown.application_fee > 0 || breakdown.security_deposit > 0) && (
        <div className="space-y-0.5 pt-2">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Move-in Costs</p>
          {breakdown.application_fee > 0 && (
            <LineItem label="Application Fee" amount={breakdown.application_fee} source="scraped" />
          )}
          {breakdown.security_deposit > 0 && (
            <LineItem label="Security Deposit" amount={breakdown.security_deposit} source="scraped" />
          )}
          <LineItem label="First Month" amount={monthlyTotal} source="estimated" />
          <div className="flex justify-between items-center border-t border-gray-200 pt-2">
            <span className="font-semibold text-gray-900 text-sm">Est. Move-in Total</span>
            <span className="font-bold text-gray-900">{formatCost(moveInTotal)}</span>
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="flex gap-4 text-xs text-gray-400 pt-1">
        <span className="flex items-center gap-1">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500" />
          From listing
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-gray-400" />
          Regional estimate
        </span>
      </div>
    </div>
  );
}
```

**Step 2: Update ApartmentCard to show true cost**

In `frontend/components/ApartmentCard.tsx`, add the true cost display between the rent section and the address section (after line 118, before line 121). Add a `useState` for the breakdown toggle:

```tsx
import { useState } from 'react';
import CostBreakdownPanel from './CostBreakdownPanel';
import { UpgradePrompt } from './UpgradePrompt';
```

Add state:

```tsx
const [showBreakdown, setShowBreakdown] = useState(false);
```

Add below the rent/property_type div (after line 118):

```tsx
        {/* True Cost Estimate */}
        {apartment.true_cost_monthly != null && apartment.true_cost_monthly > rent && (
          <div className="space-y-1">
            <button
              onClick={() => setShowBreakdown(!showBreakdown)}
              className="text-left w-full group"
            >
              <p className="text-sm text-gray-500">
                Est. True Cost:{' '}
                <span className="font-semibold text-gray-700">
                  {formatRent(apartment.true_cost_monthly)}/mo
                </span>
              </p>
              <p className="text-xs text-amber-600 group-hover:text-amber-700 transition">
                +{formatRent(apartment.true_cost_monthly - rent)}/mo in fees & utilities
                <span className="ml-1">{showBreakdown ? '\u25B2' : '\u25BC'}</span>
              </p>
            </button>

            {showBreakdown && (
              apartment.cost_breakdown ? (
                <CostBreakdownPanel breakdown={apartment.cost_breakdown} />
              ) : (
                <UpgradePrompt
                  mode="inline"
                  message="See full cost breakdown"
                />
              )
            )}
          </div>
        )}
```

**Step 3: Run frontend lint**

```bash
cd frontend && npm run lint
```

**Step 4: Commit**

```bash
git add frontend/components/CostBreakdownPanel.tsx frontend/components/ApartmentCard.tsx
git commit -m "feat(true-cost): add true cost display to ApartmentCard with Pro breakdown"
```

---

### Task 11: Compare Page True Cost Row

**Files:**
- Modify: `frontend/app/compare/page.tsx`

**Step 1: Add True Cost row to comparison table**

In the compare page, find the comparison table that renders rows for rent, beds, baths, etc. Add a new row after rent:

```tsx
{/* True Cost Row */}
<tr>
  <td className="px-4 py-3 text-sm font-medium text-gray-900 bg-gray-50">
    Est. True Cost
  </td>
  {apartments.map((apt) => (
    <td key={apt.id} className="px-4 py-3 text-sm text-gray-700">
      {apt.true_cost_monthly ? (
        <div>
          <span className="font-semibold">{formatRent(apt.true_cost_monthly)}/mo</span>
          {apt.true_cost_monthly > apt.rent && (
            <span className="block text-xs text-amber-600">
              +{formatRent(apt.true_cost_monthly - apt.rent)} over rent
            </span>
          )}
        </div>
      ) : (
        <span className="text-gray-400">—</span>
      )}
    </td>
  ))}
</tr>
```

**Step 2: Run frontend lint**

```bash
cd frontend && npm run lint
```

**Step 3: Commit**

```bash
git add frontend/app/compare/page.tsx
git commit -m "feat(true-cost): add true cost row to comparison table"
```

---

### Task 12: Backfill Existing Listings

**Files:**
- No new files — uses the Celery task from Task 8

**Step 1: Run the recompute task to backfill existing DB listings**

```bash
cd backend && source .venv/bin/activate && python -c "
from app.tasks.true_cost_tasks import recompute_true_costs
result = recompute_true_costs()
print(result)
"
```

**Step 2: Verify backfill worked**

```bash
curl "http://localhost:8000/api/apartments/list?limit=3" | python -m json.tool | grep true_cost
```

Expected: `true_cost_monthly` fields populated for all returned listings.

**Step 3: Commit** (no code changes — just verify)

---

### Task 13: Update CLAUDE.md Documentation

**Files:**
- Modify: `/Users/shuchiagarwal/Documents/HomeScout/CLAUDE.md`

**Step 1: Update the architecture section, key files, and feature descriptions**

Add to the Architecture section under Key Flow: Search:
- "Each apartment includes precomputed `true_cost_monthly` (rent + utilities + fees). Free users see the headline number; Pro users get full `cost_breakdown`."

Add to Key Files:
- `backend/app/services/cost_estimator.py` - True cost estimation from scraped fees + regional averages
- `backend/app/data/cost_estimates.json` - Regional utility cost lookup tables by zip prefix
- `backend/app/tasks/true_cost_tasks.py` - Celery task for recomputing true costs
- `frontend/components/CostBreakdownPanel.tsx` - Pro-only detailed cost breakdown display

Update the Tier Model table to include True Cost row.

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with true cost calculator feature"
```

---

### Task 14: Run Full Test Suite

**Step 1: Run all backend tests**

```bash
cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v -k "not test_apartments_router"
```

Expected: All tests pass, including new `test_cost_estimator.py` and `test_true_cost_gating.py`.

**Step 2: Run frontend lint**

```bash
cd frontend && npm run lint
```

**Step 3: Run frontend build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds with no type errors.

**Step 4: Fix any issues found, commit fixes**

```bash
git add -A && git commit -m "fix: address test/lint issues from true cost calculator"
```

---

# Phase 2: Fee Extraction Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix silent fee data loss in the Apify scraper so `true_cost_monthly` is accurate. Three bugs: nested fees format ignored, common fees have no matching pattern, unmatched fees silently dropped.

**Architecture:** Fix the scraper's fee parsing to handle both flat and nested Apify formats, widen matching patterns, add `other_monthly_fees` catch-all across the full stack (ScrapedListing → DB → CostEstimator → API → frontend), and resolve estimate vs scraped conflicts for insurance and internet.

**Tech Stack:** Python/FastAPI, PostgreSQL, Next.js/TypeScript

---

### Task 8: Parse nested `fees[]` list format from epctex Apify actor

**Files:**
- Modify: `backend/app/services/scrapers/apify_service.py:510-554`
- Test: `backend/tests/test_apify_type_safety.py`

**Step 1: Write failing tests for nested fees format**

Add to `backend/tests/test_apify_type_safety.py`:

```python
def test_fees_as_nested_list_extracts_application_fee(scraper):
    """The epctex actor returns fees as a list of {title, policies} objects."""
    raw = {**_base(), "fees": [
        {
            "title": "Fees",
            "policies": [{
                "header": "Other Fees",
                "values": [
                    {"key": "Application Fee", "value": "$50"},
                    {"key": "Admin Fee", "value": "$150"},
                ]
            }]
        }
    ]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
    assert result.application_fee == 50


def test_fees_as_nested_list_extracts_monthly_fees(scraper):
    """Nested format should extract pet rent and parking."""
    raw = {**_base(), "fees": [
        {
            "title": "Pet Policies (Pets Negotiable)",
            "policies": [{
                "header": "Dogs Allowed",
                "values": [
                    {"key": "Monthly Pet Rent", "value": "$35"},
                ]
            }]
        },
        {
            "title": "Parking",
            "policies": [{
                "header": "Covered Parking",
                "values": [
                    {"key": "Assigned Parking", "value": "$115/mo"},
                ]
            }]
        }
    ]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
    assert result.pet_rent == 35
    assert result.parking_fee == 115


def test_fees_as_nested_list_extracts_deposit(scraper):
    """Nested format should extract security deposit."""
    raw = {**_base(), "fees": [
        {
            "title": "Fees",
            "policies": [{
                "header": "Deposits",
                "values": [
                    {"key": "Security Deposit", "value": "$1,500"},
                ]
            }]
        }
    ]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
    assert result.security_deposit == 1500


def test_fees_nested_list_with_included_utilities(scraper):
    """Nested format should detect included utilities and add to amenities."""
    raw = {**_base(), "fees": [
        {
            "title": "Details",
            "policies": [{
                "header": "Utilities Included",
                "values": [
                    {"key": "Water", "value": ""},
                    {"key": "Trash Removal", "value": ""},
                    {"key": "Sewer", "value": ""},
                ]
            }]
        }
    ]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
    assert "Water Included" in result.amenities
    assert "Trash Removal Included" in result.amenities
```

**Step 2: Run tests to verify they fail**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_apify_type_safety.py -v -k "nested_list"
```
Expected: FAIL — nested list fees are silently reset to `{}`.

**Step 3: Add `_extract_fees_from_nested_list` method to `ApifyService`**

Add this new method to `ApifyService` class in `backend/app/services/scrapers/apify_service.py` (before `_normalize_apartments_com_listing`):

```python
def _extract_fees_from_nested_list(self, fees_list: list) -> tuple:
    """Parse the epctex nested fees format.

    Input: [{title, policies: [{header, values: [{key, value}]}]}]
    Returns: (monthly_fees, one_time_fees, included_utilities)
        monthly/one_time are [{name, amount}] dicts for the existing matching loop.
        included_utilities is a list of utility name strings.
    """
    monthly_fees = []
    one_time_fees = []
    included_utilities = []

    ONE_TIME_KEYS = {"deposit", "security", "application", "admin", "one time", "one-time", "move-in"}

    for section in fees_list:
        if not isinstance(section, dict):
            continue
        title = (section.get("title") or "").lower()
        policies = section.get("policies") or []
        if not isinstance(policies, list):
            continue

        for policy in policies:
            if not isinstance(policy, dict):
                continue
            header = (policy.get("header") or "").lower()
            values = policy.get("values") or []
            if not isinstance(values, list):
                continue

            # Detect "Utilities Included" sections
            if "utilities included" in header or ("included" in header and "fee" not in header):
                for v in values:
                    if isinstance(v, dict) and v.get("key"):
                        included_utilities.append(v["key"])
                continue

            for v in values:
                if not isinstance(v, dict):
                    continue
                key = (v.get("key") or "").lower()
                value = v.get("value") or ""
                amount = self._parse_fee_amount(value)
                name = f"{header} {key}".strip()
                fee_entry = {"name": name, "amount": value}

                # Classify: pet section
                if "pet" in title or "pet" in header:
                    if "monthly" in key or "rent" in key:
                        monthly_fees.append(fee_entry)
                    elif any(k in key for k in ONE_TIME_KEYS):
                        one_time_fees.append(fee_entry)
                    elif amount and amount < 100:
                        monthly_fees.append(fee_entry)
                    elif amount:
                        one_time_fees.append(fee_entry)
                # Classify: parking section
                elif "parking" in title or "parking" in header:
                    monthly_fees.append(fee_entry)
                # Classify: by key content
                elif any(k in key for k in ONE_TIME_KEYS) or any(k in header for k in ONE_TIME_KEYS):
                    one_time_fees.append(fee_entry)
                elif amount:
                    # Heuristic: >= $200 likely one-time
                    if amount >= 200:
                        one_time_fees.append(fee_entry)
                    else:
                        monthly_fees.append(fee_entry)

    return monthly_fees, one_time_fees, included_utilities
```

**Step 4: Update fee extraction block to handle both formats**

Replace lines 517-522 in `_normalize_apartments_com_listing`:

```python
        # Extract fee data from raw listing
        pet_rent = None
        parking_fee = None
        amenity_fee = None
        application_fee = None
        security_deposit = None

        # Parse fees — handle both flat and nested formats
        fees_raw = raw.get("fees")
        monthly_fees = raw.get("monthlyFees") or []
        one_time_fees = raw.get("oneTimeFees") or []
        included_utilities = []

        if isinstance(fees_raw, dict):
            # Flat dict format: {monthly: [...], oneTime: [...]}
            monthly_fees = monthly_fees or fees_raw.get("monthly", [])
            one_time_fees = one_time_fees or fees_raw.get("oneTime", [])
        elif isinstance(fees_raw, list) and fees_raw:
            # Nested list format from epctex actor
            nested_monthly, nested_one_time, included_utilities = self._extract_fees_from_nested_list(fees_raw)
            monthly_fees = monthly_fees or nested_monthly
            one_time_fees = one_time_fees or nested_one_time
```

After the petPolicy block (after line 553), add:

```python
        # Add included utilities to amenities so CostEstimator detects them
        for util_name in included_utilities:
            amenity_str = f"{util_name} Included"
            if amenity_str.lower() not in {a.lower() for a in amenities}:
                amenities.append(amenity_str)
```

**Step 5: Run tests to verify they pass**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_apify_type_safety.py -v -k "nested_list"
```
Expected: PASS

**Step 6: Run full test suite for regressions**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
```
Expected: All existing tests still pass.

**Step 7: Commit**

```bash
git add backend/app/services/scrapers/apify_service.py backend/tests/test_apify_type_safety.py
git commit -m "fix(scraper): parse nested fees list format from epctex Apify actor

The epctex apartments-scraper-api returns fees as a list of
{title, policies} objects, not a flat dict. The old code silently
reset this to {} and lost all fee data. Now handles both formats
and detects included utilities from nested sections."
```

---

### Task 9: Add `other_monthly_fees` catch-all field across the stack

**Files:**
- Modify: `backend/app/services/scrapers/base_scraper.py:52-57`
- Modify: `backend/app/models/apartment.py:57-75`
- Modify: `backend/app/schemas.py:44-58`
- Modify: `backend/app/services/cost_estimator.py`
- Modify: `backend/app/services/normalization/normalizer.py:155-161`
- Modify: `backend/app/routers/apartments.py:38-80`
- Modify: `backend/app/tasks/true_cost_tasks.py`
- Test: `backend/tests/test_cost_estimator.py`

**Step 1: Write failing tests**

Add to `backend/tests/test_cost_estimator.py` inside `TestCostEstimator`:

```python
    def test_other_monthly_fees_included_in_total(self):
        """other_monthly_fees should be added to true_cost_monthly."""
        breakdown = self.estimator.compute_true_cost(
            rent=1500,
            zip_code="15213",
            bedrooms=1,
            amenities=[],
            scraped_fees={"other_monthly_fees": 27},
        )
        assert breakdown["other_monthly_fees"] == 27
        assert breakdown["true_cost_monthly"] == (
            1500 + 27
            + breakdown["est_electric"] + breakdown["est_gas"]
            + breakdown["est_water"] + breakdown["est_internet"]
            + breakdown["est_renters_insurance"] + breakdown["est_laundry"]
        )

    def test_other_monthly_fees_in_sources(self):
        """other_monthly_fees should appear in scraped sources."""
        breakdown = self.estimator.compute_true_cost(
            rent=1500,
            zip_code="15213",
            bedrooms=1,
            amenities=[],
            scraped_fees={"other_monthly_fees": 20},
        )
        assert "other_monthly_fees" in breakdown["sources"]["scraped"]

    def test_other_monthly_fees_defaults_to_zero(self):
        """Missing other_monthly_fees should default to 0."""
        breakdown = self.estimator.compute_true_cost(
            rent=1500,
            zip_code="15213",
            bedrooms=1,
            amenities=[],
            scraped_fees={},
        )
        assert breakdown["other_monthly_fees"] == 0
```

**Step 2: Run tests to verify they fail**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_cost_estimator.py -v -k "other_monthly"
```
Expected: FAIL — `other_monthly_fees` key doesn't exist.

**Step 3: Add field to ScrapedListing**

In `backend/app/services/scrapers/base_scraper.py`, after line 57 (`security_deposit`), add:

```python
    other_monthly_fees: Optional[int] = None  # Catch-all for unmatched monthly fees
```

In `to_dict()` (line 95), add:

```python
            "other_monthly_fees": self.other_monthly_fees,
```

**Step 4: Add column to ApartmentModel**

In `backend/app/models/apartment.py`, after line 62 (`security_deposit`), add:

```python
    other_monthly_fees = Column(Integer, nullable=True)  # Catch-all for unmatched monthly fees
```

In `to_dict()`, after the `security_deposit` line (line 149), add:

```python
            "other_monthly_fees": self.other_monthly_fees,
```

In `to_summary_dict()`, after the `security_deposit` line (line 196), add:

```python
            "other_monthly_fees": self.other_monthly_fees,
```

**Step 5: Add field to CostEstimator**

In `backend/app/services/cost_estimator.py`:

After line 102 (`amenity_fee`), add:
```python
        other_monthly_fees = scraped_fees.get("other_monthly_fees") or 0
```

Update the `monthly_extras` sum (line 109-113) to include it:
```python
        monthly_extras = (
            pet_rent + parking_fee + amenity_fee + other_monthly_fees
            + est_electric + est_gas + est_water
            + est_internet + est_renters_insurance + est_laundry
        )
```

Update `scraped_sources` (line 118-121):
```python
        scraped_sources = [
            k for k in ("pet_rent", "parking_fee", "amenity_fee", "other_monthly_fees")
            if scraped_fees.get(k)
        ]
```

Add to return dict (after `"amenity_fee": amenity_fee,` around line 148):
```python
            "other_monthly_fees": other_monthly_fees,
```

**Step 6: Add field to Pydantic schema**

In `backend/app/schemas.py`, in `CostBreakdown` class, after `amenity_fee` (line 49):

```python
    other_monthly_fees: int = 0
```

**Step 7: Update normalizer**

In `backend/app/services/normalization/normalizer.py`, add to the `scraped_fees` dict (after line 159):

```python
            "other_monthly_fees": data.get("other_monthly_fees"),
```

**Step 8: Update apartments router**

In `backend/app/routers/apartments.py`:

In `_add_cost_breakdown()`, add to the `scraped_fees` dict (after line 51):
```python
                "other_monthly_fees": apartment.get("other_monthly_fees"),
```

In the `cost_breakdown` reconstruction (after line 63), add:
```python
            "other_monthly_fees": apartment.get("other_monthly_fees") or 0,
```

In `_build_sources()` (line 78), update:
```python
    scraped = [k for k in ("pet_rent", "parking_fee", "amenity_fee", "other_monthly_fees") if apartment.get(k)]
```

**Step 9: Update true_cost_tasks.py**

In `backend/app/tasks/true_cost_tasks.py`, add to `scraped_fees` dict (after line 41):
```python
                    "other_monthly_fees": apt.other_monthly_fees,
```

**Step 10: Run tests to verify they pass**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_cost_estimator.py -v
```
Expected: All pass including the 3 new ones.

**Step 11: Run full backend test suite**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
```
Expected: All pass.

**Step 12: Commit**

```bash
git add backend/
git commit -m "feat(cost): add other_monthly_fees catch-all field across the stack

Fees that don't match pet/parking/amenity categories now accumulate
in other_monthly_fees instead of being silently dropped. Field added
to ScrapedListing, ApartmentModel, CostEstimator, schemas, normalizer,
router, and recompute task."
```

---

### Task 10: Widen fee matching patterns and populate catch-all in scraper

**Files:**
- Modify: `backend/app/services/scrapers/apify_service.py:524-534`
- Test: `backend/tests/test_apify_type_safety.py`

**Step 1: Write failing tests**

Add to `backend/tests/test_apify_type_safety.py`:

```python
def test_utility_admin_fee_captured(scraper):
    """Utility billing admin fee should go to other_monthly_fees."""
    raw = {**_base(), "monthlyFees": [
        {"name": "Utility Billing Admin Fee", "amount": "$6.44"},
    ]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
    assert result.other_monthly_fees == 6


def test_pest_control_fee_captured(scraper):
    """Pest control fee should go to other_monthly_fees."""
    raw = {**_base(), "monthlyFees": [
        {"name": "Pest Control", "amount": "$5"},
    ]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
    assert result.other_monthly_fees == 5


def test_sewer_fee_captured(scraper):
    """Sewer fee should go to other_monthly_fees."""
    raw = {**_base(), "monthlyFees": [
        {"name": "Sewer", "amount": "$15"},
    ]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
    assert result.other_monthly_fees == 15


def test_mandatory_insurance_goes_to_amenity_fee(scraper):
    """Mandatory property insurance should be captured in amenity_fee."""
    raw = {**_base(), "monthlyFees": [
        {"name": "Renters Insurance Program", "amount": "$14.50"},
    ]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
    assert result.amenity_fee == 14
    # Should also inject amenity for CostEstimator to zero out the estimate
    assert any("insurance" in a.lower() for a in result.amenities)


def test_multiple_unmatched_fees_accumulate(scraper):
    """Multiple unmatched fees should accumulate in other_monthly_fees."""
    raw = {**_base(), "monthlyFees": [
        {"name": "Utility Billing Admin", "amount": "$6"},
        {"name": "Pest Control", "amount": "$5"},
        {"name": "Sewer", "amount": "$15"},
    ]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
    assert result.other_monthly_fees == 26


def test_garage_parking_captured(scraper):
    """Garage fee should match parking pattern."""
    raw = {**_base(), "monthlyFees": [
        {"name": "Garage Parking", "amount": "$115"},
    ]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
    assert result.parking_fee == 115


def test_valet_trash_captured(scraper):
    """Valet trash fee should match amenity pattern."""
    raw = {**_base(), "monthlyFees": [
        {"name": "Valet Trash", "amount": "$20"},
    ]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
    assert result.amenity_fee == 20
```

**Step 2: Run tests to verify they fail**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_apify_type_safety.py -v -k "utility_admin or pest_control or sewer or mandatory_insurance or unmatched or garage or valet"
```
Expected: FAIL

**Step 3: Widen fee matching and add catch-all**

Replace the monthly fee matching block in `apify_service.py` (lines 524-534):

```python
        other_monthly = 0

        if isinstance(monthly_fees, list):
            for fee in monthly_fees:
                if isinstance(fee, dict):
                    name = (fee.get("name") or fee.get("label") or "").lower()
                    amount = self._parse_fee_amount(fee.get("amount") or fee.get("value"))
                    if not amount:
                        continue
                    if "pet" in name or "dog" in name or "cat" in name:
                        pet_rent = amount
                    elif "parking" in name or "garage" in name:
                        parking_fee = amount
                    elif "amenity" in name or "community" in name or "trash" in name or "valet" in name:
                        amenity_fee = (amenity_fee or 0) + amount
                    elif "insurance" in name:
                        # Mandatory property insurance — add to amenity_fee and flag it
                        amenity_fee = (amenity_fee or 0) + amount
                        amenities.append("Renters Insurance Required")
                    else:
                        # Catch-all: utility admin, pest control, sewer, etc.
                        other_monthly += amount
                        logger.debug(f"Unmatched monthly fee captured: '{name}' = ${amount}")
```

After the petPolicy block and the included_utilities injection, set the field on the ScrapedListing construction (around line 635-641). Add `other_monthly_fees=other_monthly or None` to the ScrapedListing constructor call.

**Step 4: Run tests to verify they pass**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_apify_type_safety.py -v -k "utility_admin or pest_control or sewer or mandatory_insurance or unmatched or garage or valet"
```
Expected: PASS

**Step 5: Run full test suite**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
```
Expected: All pass.

**Step 6: Commit**

```bash
git add backend/app/services/scrapers/apify_service.py backend/tests/test_apify_type_safety.py
git commit -m "fix(scraper): widen fee patterns and capture unmatched fees

Added garage, valet, insurance matching. Mandatory property insurance
injected as amenity for estimate conflict resolution. Unmatched monthly
fees accumulate in other_monthly_fees. Logged at DEBUG level."
```

---

### Task 11: Resolve estimated vs scraped insurance and internet conflicts

**Files:**
- Modify: `backend/app/services/cost_estimator.py`
- Test: `backend/tests/test_cost_estimator.py`

**Step 1: Write failing tests**

Add to `backend/tests/test_cost_estimator.py` inside `TestCostEstimator`:

```python
    def test_scraped_insurance_zeroes_estimate(self):
        """When amenities indicate mandatory insurance, est_renters_insurance should be 0."""
        breakdown = self.estimator.compute_true_cost(
            rent=1500,
            zip_code="15213",
            bedrooms=1,
            amenities=["Renters Insurance Required"],
            scraped_fees={"amenity_fee": 14},
        )
        assert breakdown["est_renters_insurance"] == 0
        assert "renters_insurance" in breakdown["sources"]["included"]

    def test_internet_included_zeroes_estimate(self):
        """When amenities say internet included, est_internet should be 0."""
        breakdown = self.estimator.compute_true_cost(
            rent=1500,
            zip_code="15213",
            bedrooms=1,
            amenities=["Internet Included"],
            scraped_fees={},
        )
        assert breakdown["est_internet"] == 0
        assert "internet" in breakdown["sources"]["included"]

    def test_wifi_included_zeroes_estimate(self):
        """WiFi Included should also zero est_internet."""
        breakdown = self.estimator.compute_true_cost(
            rent=1500,
            zip_code="15213",
            bedrooms=1,
            amenities=["WiFi Included"],
            scraped_fees={},
        )
        assert breakdown["est_internet"] == 0
```

**Step 2: Run tests to verify they fail**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_cost_estimator.py -v -k "scraped_insurance or internet_included or wifi_included"
```
Expected: FAIL

**Step 3: Add detection constants and update logic**

In `backend/app/services/cost_estimator.py`, add after line 27 (after `_IN_UNIT_LAUNDRY`):

```python
_INSURANCE_REQUIRED = {"renters insurance required", "renters insurance program", "insurance required"}
_INTERNET_INCLUDED = {"internet included", "wifi included", "wi-fi included", "high-speed internet included"}
```

In `compute_true_cost()`, after line 89 (`has_in_unit_laundry`), add:

```python
        insurance_required = bool(amenity_set & _INSURANCE_REQUIRED)
        internet_included = all_included or bool(amenity_set & _INTERNET_INCLUDED)
```

Update line 95-96:

```python
        est_internet = 0 if internet_included else estimates["internet"]
        est_renters_insurance = 0 if insurance_required else estimates["renters_insurance"]
```

Add to `included_sources` block (after the laundry check around line 141):

```python
        if insurance_required:
            included_sources.append("renters_insurance")
        if internet_included:
            included_sources.append("internet")
```

**Step 4: Run tests to verify they pass**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_cost_estimator.py -v
```
Expected: All pass.

**Step 5: Run full test suite**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
```
Expected: All pass.

**Step 6: Commit**

```bash
git add backend/app/services/cost_estimator.py backend/tests/test_cost_estimator.py
git commit -m "fix(cost): resolve estimated vs scraped insurance and internet conflicts

When property mandates renters insurance (captured in amenity_fee),
est_renters_insurance is zeroed to prevent double-counting.
When Internet/WiFi is included in amenities, est_internet is zeroed.
Both tracked in sources.included for transparency."
```

---

### Task 12: Update frontend for `other_monthly_fees` and new included sources

**Files:**
- Modify: `frontend/types/apartment.ts`
- Modify: `frontend/components/CostBreakdownPanel.tsx`

**Step 1: Add field to TypeScript interface**

In `frontend/types/apartment.ts`, in the `CostBreakdown` interface, after `amenity_fee`:

```typescript
  other_monthly_fees: number;
```

**Step 2: Update CostBreakdownPanel**

In `frontend/components/CostBreakdownPanel.tsx`:

Add `other_monthly_fees` to `monthlyTotal` calculation (after `amenity_fee`, line 55):

```typescript
  const monthlyTotal =
    breakdown.base_rent +
    breakdown.pet_rent +
    breakdown.parking_fee +
    breakdown.amenity_fee +
    (breakdown.other_monthly_fees || 0) +
    breakdown.est_electric +
    breakdown.est_gas +
    breakdown.est_water +
    breakdown.est_internet +
    breakdown.est_renters_insurance +
    breakdown.est_laundry;
```

Add line item after the amenity fee block (after line 80):

```tsx
        {(breakdown.other_monthly_fees || 0) > 0 && (
          <LineItem label="Other Fees" amount={breakdown.other_monthly_fees} source="scraped" />
        )}
```

Update the utilities section to handle new included sources. After the internet line (line 99), handle internet included:

```tsx
        {isIncluded('internet') ? (
          <LineItem label="Internet" amount={0} source="included" />
        ) : (
          <LineItem label="Internet" amount={breakdown.est_internet} source="estimated" />
        )}
        {isIncluded('renters_insurance') ? (
          <LineItem label="Renter&apos;s Insurance" amount={0} source="included" />
        ) : (
          <LineItem label="Renter&apos;s Insurance" amount={breakdown.est_renters_insurance} source="estimated" />
        )}
```

(This replaces the current lines 99-100 which don't handle internet/insurance included.)

**Step 3: Verify frontend builds**

```bash
cd frontend && npm run build
```
Expected: Build succeeds with no type errors.

**Step 4: Commit**

```bash
git add frontend/types/apartment.ts frontend/components/CostBreakdownPanel.tsx
git commit -m "feat(ui): show other_monthly_fees and handle internet/insurance included

CostBreakdownPanel now renders 'Other Fees' line item for catch-all
monthly fees. Internet and Renter's Insurance now show 'Included'
when detected from listing amenities."
```

---

### Task 13: Database migration and recompute

**Step 1: Add column to database**

Run in Supabase SQL Editor or via psql:

```sql
ALTER TABLE apartments ADD COLUMN IF NOT EXISTS other_monthly_fees INTEGER;
```

Or if using Alembic:

```bash
cd backend
alembic revision --autogenerate -m "add other_monthly_fees column"
alembic upgrade head
```

**Step 2: Trigger recompute of existing listings**

```bash
cd backend
source .venv/bin/activate
python -c "
from app.tasks.true_cost_tasks import recompute_true_costs
result = recompute_true_costs.delay()
print(f'Dispatched recompute task: {result.id}')
"
```

**Step 3: Verify**

```bash
curl "http://localhost:8000/api/apartments/list?limit=1" | python -m json.tool | grep -E "true_cost|other_monthly"
```

**Step 4: Commit migration**

```bash
git add backend/alembic/ || true
git commit -m "chore(db): add other_monthly_fees column to apartments"
```

---

### Task 14: Final integration verification

**Step 1: Run full backend test suite**

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
```
Expected: All tests pass.

**Step 2: Run frontend lint and build**

```bash
cd frontend && npm run lint && npm run build
```
Expected: No errors.

**Step 3: Manual end-to-end verification**

Trigger a scrape for Pittsburgh (which has student housing with nested fees):

```bash
curl -X POST http://localhost:8000/api/admin/data-collection/markets/pittsburgh/scrape
```

After completion, check a listing:

```bash
curl "http://localhost:8000/api/apartments/list?city=Pittsburgh&limit=3" | python -m json.tool
```

Verify:
- `other_monthly_fees` is non-null for listings with misc fees
- `true_cost_monthly` is higher than before (includes previously-dropped fees)
- `amenity_fee` includes mandatory insurance fees
- Nested fees format listings have fee data populated

**Step 4: Fix any issues, commit**

```bash
git add -A && git commit -m "fix: address issues from fee extraction integration testing"
```