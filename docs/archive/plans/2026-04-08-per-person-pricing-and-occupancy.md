# Per-Person Pricing & Occupancy Calculator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect per-person pricing in student housing listings and add an occupancy calculator so users can see their actual per-person monthly cost.

**Architecture:** Add `pricing_model` detection via description heuristics (individual lease, per person, beds==baths, student housing signals). Extend `CostBreakdownPanel` with an occupancy stepper that splits shared costs client-side. Keep epctex scraper as-is — per-person detection works from existing scraped data (confirmed with One on Centre Pittsburgh).

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Next.js/React, TypeScript

---

## Overview

7 tasks in execution order:
1. **DB migration** — Add `pricing_model` columns
2. **Detection service** — Heuristic per-person pricing detector
3. **Integrate into normalizer** — Wire detection into scrape pipeline
4. **API & frontend types** — Add `pricing_model` to schemas and TypeScript
5. **Per-person badge** — Show badge and "/person" label on cards
6. **Occupancy calculator** — Stepper + cost splitting in CostBreakdownPanel
7. **Claude AI prompts** — Per-person awareness in scoring and comparison

## Key Design Decisions

- **Heuristic detection, not explicit labels**: epctex doesn't capture apartments.com's new "Charged per unit/per person" labels. We detect via description text + structural patterns.
- **Client-side cost splitting**: The occupancy stepper recalculates costs in the browser — no API changes needed for different occupancy counts.
- **Conservative default**: Unknown listings default to `per_unit`. Only flag `per_person` when confidence >= 0.6.
- **Studios never per-person**: bedrooms==0 always returns `per_unit`.

## Per-Person Detection Signals (from One on Centre test data)

| Signal | Source | Confidence |
|--------|--------|------------|
| "per person", "per bed", "by the bed" in description | High (0.9) |
| "individual lease" in description | High (0.85) |
| "prices shown are base rent" in description | Medium (0.5) |
| "student housing" + beds==baths | Medium (0.4 + 0.25) |
| "off-campus" in description | Low (0.3) |
| beds == baths (2/2, 3/3, 4/4) alone | Supporting (0.25) |

## Cost Splitting Rules

```
Personal costs (NEVER divided):
  - pet_rent (your pet, your cost)
  - est_internet (one connection, everyone uses it)
  - est_renters_insurance (per-person policy)
  - parking_fee (per-space)

Shared costs (divided by occupancy):
  - base_rent (for per-unit listings only; per-person rent is already per-person)
  - est_electric, est_gas, est_water
  - amenity_fee, other_monthly_fees
  - est_laundry

One-time costs (divided by occupancy for per-unit):
  - application_fee (usually per-applicant — keep as-is)
  - admin_fee (per-unit — divide)
  - security_deposit (per-unit — divide)
```

---

## Task 1: Alembic Migration for pricing_model

**Files:**
- Create: `backend/alembic/versions/j5e6f7g8h9i0_add_pricing_model.py`
- Modify: `backend/app/models/apartment.py` (add columns after line 64)
- Modify: `backend/app/models/apartment.py` (add to `to_dict` and `to_summary_dict`)

**Step 1: Add columns to ApartmentModel**

After the `other_monthly_fees` column in `backend/app/models/apartment.py`:
```python
# Pricing model detection
pricing_model = Column(String(20), default="per_unit")  # "per_unit" or "per_person"
pricing_model_confidence = Column(Float, nullable=True)  # 0.0-1.0
```

**Step 2: Add to both serialization methods**

In `to_dict()` and `to_summary_dict()`, add:
```python
"pricing_model": self.pricing_model,
```

**Step 3: Add to ScrapedListing**

In `backend/app/services/scrapers/base_scraper.py`, after `other_monthly_fees`:
```python
pricing_model: Optional[str] = None  # "per_unit" or "per_person"
pricing_model_confidence: Optional[float] = None
```

Add to `to_dict()`:
```python
"pricing_model": self.pricing_model,
"pricing_model_confidence": self.pricing_model_confidence,
```

**Step 4: Add to `_save_listings`**

In `backend/app/tasks/scrape_tasks.py`, add to the ApartmentModel constructor:
```python
pricing_model=listing_data.get("pricing_model"),
pricing_model_confidence=listing_data.get("pricing_model_confidence"),
```

**Step 5: Create Alembic migration**

```python
"""add pricing_model columns

Revision ID: j5e6f7g8h9i0
Revises: i4d5e6f7g8h9
"""
def upgrade():
    op.add_column('apartments', sa.Column('pricing_model', sa.String(20), server_default='per_unit'))
    op.add_column('apartments', sa.Column('pricing_model_confidence', sa.Float(), nullable=True))

def downgrade():
    op.drop_column('apartments', 'pricing_model_confidence')
    op.drop_column('apartments', 'pricing_model')
```

**Step 6: Apply migration and run tests**

```bash
cd backend && alembic upgrade head
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
```

**Step 7: Commit**

```bash
git add backend/app/models/apartment.py backend/app/services/scrapers/base_scraper.py \
  backend/app/tasks/scrape_tasks.py backend/alembic/versions/j5e6f7g8h9i0_add_pricing_model.py
git commit -m "chore(db): add pricing_model and pricing_model_confidence columns"
```

---

## Task 2: Per-Person Pricing Detection Service

**Files:**
- Create: `backend/app/services/pricing_model_detector.py`
- Create: `backend/tests/test_pricing_model_detector.py`

**Step 1: Write failing tests**

```python
import pytest
from app.services.pricing_model_detector import detect_pricing_model


def test_individual_lease_high_confidence():
    result = detect_pricing_model(
        description="Brand new student housing with individual lease options",
        bedrooms=4, bathrooms=4, rent=1030, city="Pittsburgh",
    )
    assert result["pricing_model"] == "per_person"
    assert result["confidence"] >= 0.7


def test_per_person_in_description():
    result = detect_pricing_model(
        description="Rent is $1,030 per person per month",
        bedrooms=2, bathrooms=2, rent=1030, city="Pittsburgh",
    )
    assert result["pricing_model"] == "per_person"
    assert result["confidence"] >= 0.8


def test_by_the_bed():
    result = detect_pricing_model(
        description="Lease by the bed in our modern community",
        bedrooms=3, bathrooms=3, rent=800, city="Pittsburgh",
    )
    assert result["pricing_model"] == "per_person"


def test_one_on_centre_description():
    """Real description from One on Centre Pittsburgh (epctex data)."""
    result = detect_pricing_model(
        description="Modern amenities you would expect from a brand new off-campus student housing community. Prices shown are base rent. Additional fees apply.",
        bedrooms=2, bathrooms=2, rent=1500, city="Pittsburgh",
    )
    assert result["pricing_model"] == "per_person"


def test_beds_equal_baths_with_student():
    result = detect_pricing_model(
        description="Located near the university, student friendly community",
        bedrooms=4, bathrooms=4, rent=900, city="Pittsburgh",
    )
    assert result["pricing_model"] == "per_person"


def test_normal_apartment():
    result = detect_pricing_model(
        description="Beautiful 2BR apartment in downtown Philadelphia",
        bedrooms=2, bathrooms=1, rent=1800, city="Philadelphia",
    )
    assert result["pricing_model"] == "per_unit"
    assert result["confidence"] >= 0.9


def test_studio_never_per_person():
    result = detect_pricing_model(
        description="Student studio near campus with individual lease",
        bedrooms=0, bathrooms=1, rent=1200, city="Pittsburgh",
    )
    assert result["pricing_model"] == "per_unit"


def test_beds_not_equal_baths_no_description_signals():
    """beds != baths without description signals should be per_unit."""
    result = detect_pricing_model(
        description="Spacious 4 bedroom apartment near park",
        bedrooms=4, bathrooms=2, rent=600, city="New York",
    )
    assert result["pricing_model"] == "per_unit"


def test_student_alone_not_sufficient():
    """'student' keyword alone without other signals is not enough."""
    result = detect_pricing_model(
        description="Near student campus, great restaurants",
        bedrooms=2, bathrooms=1, rent=1500, city="Boston",
    )
    assert result["pricing_model"] == "per_unit"


def test_per_room_in_description():
    result = detect_pricing_model(
        description="Furnished rooms available, $900 per room",
        bedrooms=3, bathrooms=2, rent=900, city="Philadelphia",
    )
    assert result["pricing_model"] == "per_person"
```

**Step 2: Run tests — all should fail**

```bash
cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_pricing_model_detector.py -v
```

**Step 3: Implement detector**

Create `backend/app/services/pricing_model_detector.py`:

```python
"""Detect whether a listing uses per-person or per-unit pricing."""
import re
from typing import Dict, Any

# High confidence signals (any one is sufficient)
_HIGH_SIGNALS = [
    (r"per\s+person", 0.9),
    (r"per\s+bed\b", 0.9),
    (r"by\s+the\s+bed", 0.9),
    (r"individual\s+lease", 0.85),
    (r"per\s+room\b", 0.85),
]

# Medium signals (accumulated)
_MEDIUM_SIGNALS = [
    (r"\bstudent\s+housing\b", 0.4),
    (r"off[- ]campus", 0.3),
    (r"prices\s+shown\s+are\s+base\s+rent", 0.5),
]


def detect_pricing_model(
    description: str,
    bedrooms: int,
    bathrooms: float,
    rent: int,
    city: str,
) -> Dict[str, Any]:
    """Detect per-person vs per-unit pricing from listing data.

    Returns:
        {"pricing_model": "per_unit"|"per_person", "confidence": float}
    """
    # Studios are never per-person
    if bedrooms == 0:
        return {"pricing_model": "per_unit", "confidence": 0.95}

    desc_lower = (description or "").lower()
    score = 0.0

    # High-confidence description signals
    for pattern, weight in _HIGH_SIGNALS:
        if re.search(pattern, desc_lower):
            score = max(score, weight)

    # Medium signals (accumulate)
    for pattern, weight in _MEDIUM_SIGNALS:
        if re.search(pattern, desc_lower):
            score += weight

    # Beds == baths pattern (2/2, 3/3, 4/4) — common in student housing
    if bedrooms >= 2 and bedrooms == int(bathrooms):
        score += 0.25

    # Clamp to 1.0
    score = min(score, 1.0)

    if score >= 0.6:
        return {"pricing_model": "per_person", "confidence": round(score, 2)}
    else:
        return {"pricing_model": "per_unit", "confidence": round(1.0 - score, 2)}
```

**Step 4: Run tests — all should pass**

```bash
cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/test_pricing_model_detector.py -v
```

**Step 5: Run full test suite to verify no regressions**

```bash
cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
```

**Step 6: Commit**

```bash
git add backend/app/services/pricing_model_detector.py backend/tests/test_pricing_model_detector.py
git commit -m "feat(pricing): add per-person pricing detection heuristics"
```

---

## Task 3: Integrate Detection into Normalizer

**Files:**
- Modify: `backend/app/services/normalization/normalizer.py` (after line 186)

**Step 1: Add detection call after fee extraction**

After Step 10 (compute true cost) in `normalizer.py`, add:

```python
# Step 10b: Detect pricing model
from app.services.pricing_model_detector import detect_pricing_model
detection = detect_pricing_model(
    description=data.get("description") or "",
    bedrooms=data["bedrooms"],
    bathrooms=data["bathrooms"],
    rent=data["rent"],
    city=data.get("city") or "",
)
data["pricing_model"] = detection["pricing_model"]
data["pricing_model_confidence"] = detection["confidence"]
```

**Step 2: Run full test suite**

```bash
cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
```

**Step 3: Commit**

```bash
git add backend/app/services/normalization/normalizer.py
git commit -m "feat(pricing): integrate per-person detection into normalizer pipeline"
```

---

## Task 4: API Schemas & Frontend Types

**Files:**
- Modify: `backend/app/schemas.py` (Apartment model)
- Modify: `frontend/types/apartment.ts` (Apartment interface)

**Step 1: Add to backend schema**

In `backend/app/schemas.py`, in the Apartment model (after `cost_breakdown`):
```python
pricing_model: Optional[str] = None
```

**Step 2: Add to frontend types**

In `frontend/types/apartment.ts`, in the Apartment interface (after `cost_breakdown`):
```typescript
pricing_model?: 'per_unit' | 'per_person' | null;
```

**Step 3: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -v e2e/
```

**Step 4: Commit**

```bash
git add backend/app/schemas.py frontend/types/apartment.ts
git commit -m "feat(pricing): add pricing_model to API schema and frontend types"
```

---

## Task 5: Per-Person Badge on ApartmentCard

**Files:**
- Modify: `frontend/components/ApartmentCard.tsx`

**Step 1: Add per-person badge**

Around line 127 (before the true cost section), add:
```tsx
{apartment.pricing_model === 'per_person' && (
  <span className="inline-block bg-purple-100 text-purple-700 text-xs font-medium px-2 py-0.5 rounded">
    Per Person Pricing
  </span>
)}
```

**Step 2: Change rent label for per-person listings**

At the rent display (around line 138), make the "/mo" label conditional:
```tsx
{formatRent(apartment.true_cost_monthly)}
{apartment.pricing_model === 'per_person' ? '/person' : '/mo'}
```

Also update the delta text (around line 142):
```tsx
+{formatRent(apartment.true_cost_monthly - rent)}
{apartment.pricing_model === 'per_person' ? '/person' : '/mo'} in fees & utilities
```

**Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -v e2e/
```

**Step 4: Commit**

```bash
git add frontend/components/ApartmentCard.tsx
git commit -m "feat(ui): add per-person pricing badge and /person label on apartment cards"
```

---

## Task 6: Occupancy Calculator in CostBreakdownPanel

**Files:**
- Modify: `frontend/components/CostBreakdownPanel.tsx`
- Modify: `frontend/components/ApartmentCard.tsx` (pass new props)

**Step 1: Update component props**

```tsx
interface CostBreakdownPanelProps {
  breakdown: CostBreakdown;
  pricingModel?: 'per_unit' | 'per_person' | null;
  bedrooms?: number;
}
```

**Step 2: Add occupancy state**

At top of component:
```tsx
const isPerPerson = pricingModel === 'per_person';
const defaultOccupancy = isPerPerson ? (bedrooms || 1) : 1;
const [occupancy, setOccupancy] = useState(defaultOccupancy);
const showOccupancy = occupancy > 1 || isPerPerson;
```

**Step 3: Add stepper UI**

Replace the "Monthly Costs" header with:
```tsx
<div className="flex items-center justify-between">
  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Monthly Costs</p>
  <div className="flex items-center gap-2">
    <span className="text-xs text-gray-500">People:</span>
    <button
      onClick={() => setOccupancy(Math.max(1, occupancy - 1))}
      className="w-6 h-6 rounded-full border border-gray-300 text-gray-500 text-sm flex items-center justify-center hover:bg-gray-50"
    >
      -
    </button>
    <span className="text-sm font-medium w-4 text-center">{occupancy}</span>
    <button
      onClick={() => setOccupancy(Math.min(6, occupancy + 1))}
      className="w-6 h-6 rounded-full border border-gray-300 text-gray-500 text-sm flex items-center justify-center hover:bg-gray-50"
    >
      +
    </button>
  </div>
</div>
```

**Step 4: Add cost splitting logic**

```tsx
// Shared costs: divided by occupancy (but NOT for per-person rent)
const splitShared = (amount: number) =>
  occupancy > 1 ? Math.round(amount / occupancy) : amount;

// Per-person rent: already per-person, don't divide
const myRent = isPerPerson ? breakdown.base_rent : splitShared(breakdown.base_rent);
const myElectric = splitShared(breakdown.est_electric);
const myGas = splitShared(breakdown.est_gas);
const myWater = splitShared(breakdown.est_water);
const myAmenity = splitShared(breakdown.amenity_fee);
const myOtherMonthly = splitShared(breakdown.other_monthly_fees || 0);
const myLaundry = splitShared(breakdown.est_laundry);

// Personal costs: never divided
const myPetRent = breakdown.pet_rent;
const myParking = breakdown.parking_fee;
const myInternet = breakdown.est_internet;
const myInsurance = breakdown.est_renters_insurance;

const monthlyTotal = myRent + myPetRent + myParking + myAmenity + myOtherMonthly
  + myElectric + myGas + myWater + myInternet + myInsurance + myLaundry;

// Move-in: app fee is per-applicant (don't split), admin+deposit are per-unit (split)
const myAdminFee = splitShared(breakdown.admin_fee || 0);
const myDeposit = splitShared(breakdown.security_deposit);
const moveInTotal = breakdown.application_fee + myAdminFee + myDeposit + monthlyTotal;
```

**Step 5: Update line items to use split amounts**

Replace hardcoded breakdown amounts with the split variables. Add "/person" suffix when `showOccupancy`:
```tsx
const perPersonSuffix = showOccupancy ? ' /person' : '';

<LineItem label={`Base Rent${perPersonSuffix}`} amount={myRent} source="scraped" />
// ... etc for all line items using my* variables
```

**Step 6: Pass props from ApartmentCard**

In `ApartmentCard.tsx`, update the CostBreakdownPanel call:
```tsx
<CostBreakdownPanel
  breakdown={apartment.cost_breakdown}
  pricingModel={apartment.pricing_model}
  bedrooms={apartment.bedrooms}
/>
```

**Step 7: TypeScript check and commit**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -v e2e/
git add frontend/components/CostBreakdownPanel.tsx frontend/components/ApartmentCard.tsx
git commit -m "feat(ui): add occupancy calculator with cost splitting to CostBreakdownPanel"
```

---

## Task 7: Claude AI Prompt Updates

**Files:**
- Modify: `backend/app/services/claude_service.py`

**Step 1: Update search scoring prompt**

In the system prompt for `score_apartments()`, add this paragraph:
```
When a listing has pricing_model "per_person", the rent shown is per-occupant, not per-unit.
For budget comparison, compare the per-person cost against the user's budget.
Flag per-person pricing prominently in highlights: "Per-person pricing — $X is per bed, not for the whole unit."
```

**Step 2: Update comparison prompt**

In `compare_apartments_with_analysis()`, add:
```
When comparing per-person and per-unit listings, normalize to per-person cost for fair comparison.
A 3BR at $1,030/person (total $3,090/unit) should NOT appear cheaper than a 1BR at $1,500/unit.
```

**Step 3: Include pricing_model in apartment data sent to Claude**

Wherever apartment data is formatted for Claude prompts, add:
```python
if apt.get("pricing_model") == "per_person":
    apt_str += f"\n  PRICING: Per-person — ${apt['rent']}/person (est. ${apt['rent'] * apt.get('bedrooms', 1)}/unit total)"
```

**Step 4: Run tests and commit**

```bash
cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
git add backend/app/services/claude_service.py
git commit -m "feat(ai): update Claude prompts for per-person pricing awareness"
```

---

## Task 8: Update Backfill & Integration Test

**Files:**
- Modify: `backend/app/tasks/true_cost_tasks.py` (backfill_fees_task)
- Modify: `backend/app/routers/data_collection.py` (backfill endpoint)

**Step 1: Add pricing_model to backfill task**

In the backfill loop, after fee extraction add:
```python
from app.services.pricing_model_detector import detect_pricing_model
detection = detect_pricing_model(
    description=listing.description or "",
    bedrooms=bedrooms,
    bathrooms=listing.bathrooms,
    rent=rent,
    city=listing.city or "",
)
```

Add to the UPDATE SQL:
```sql
pricing_model = :pricing_model, pricing_model_confidence = :pricing_model_confidence
```

And the params:
```python
"pricing_model": detection["pricing_model"],
"pricing_model_confidence": detection["confidence"],
```

**Step 2: Full test suite**

```bash
cd backend && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
```

**Step 3: Local end-to-end verification**

```bash
alembic upgrade head
python scripts/backfill_fees.py  # Run locally
# Start backend, search for Pittsburgh
# Verify: per-person listings show purple badge
# Verify: occupancy stepper appears and recalculates
# Verify: normal listings show no badge
```

**Step 4: Commit, push, deploy**

```bash
git add backend/app/tasks/true_cost_tasks.py
git commit -m "feat(backfill): include pricing_model detection in fee backfill"
git push origin main
# After deploy:
curl -X POST https://api-dev.snugd.ai/api/admin/data-collection/backfill-fees
```

---

## Execution Order Summary

| # | Task | Est. Size | Dependencies |
|---|------|-----------|--------------|
| 1 | DB migration + model changes | Small | None |
| 2 | Detection service + tests | Medium | None |
| 3 | Integrate into normalizer | Small | Tasks 1, 2 |
| 4 | API schema + frontend types | Small | Task 1 |
| 5 | Per-person badge on UI | Small | Task 4 |
| 6 | Occupancy calculator | Medium | Tasks 4, 5 |
| 7 | Claude AI prompts | Small | Task 4 |
| 8 | Backfill update + integration test | Small | Tasks 2, 3 |
