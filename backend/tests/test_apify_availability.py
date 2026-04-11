"""Tests for availability date extraction from Apify apartments.com data."""
import pytest
from app.services.scrapers.apify_service import ApifyService


@pytest.fixture
def scraper():
    return ApifyService(source_id="apartments_com")


def _make_raw(models=None, rentals=None, **overrides):
    """Build a minimal valid apartments.com raw listing."""
    base = {
        "id": "test-123",
        "address": "123 Main St",
        "location": {"fullAddress": "123 Main St, Pittsburgh, PA 15213", "city": "Pittsburgh", "state": "PA", "postalCode": "15213"},
        "rent": {"min": 1500, "max": 2000},
        "beds": "1 bd",
        "baths": "1 ba",
        "sqft": "600",
        "url": "https://www.apartments.com/test/123",
    }
    if models is not None:
        base["models"] = models
    if rentals is not None:
        base["rentals"] = rentals
    base.update(overrides)
    return base


# --- Test 1: Rentals with ISO dates → extracts earliest ---
def test_extracts_earliest_date_from_rentals(scraper):
    raw = _make_raw(
        models=[
            {"modelId": "m1", "availability": "2 Available units", "availabilityInfo": "Now"},
        ],
        rentals=[
            {"modelId": "m1", "availableDate": "2026-05-01T00:00:00-04:00", "availability": "Now"},
            {"modelId": "m1", "availableDate": "2026-04-15T00:00:00-04:00", "availability": "Now"},
        ],
    )
    listing = scraper._normalize_apartments_com_listing(raw)
    assert listing is not None
    assert listing.available_date == "2026-04-15"


# --- Test 2: All units "Now" (no ISO dates) → returns "Now" ---
def test_now_when_no_dates(scraper):
    raw = _make_raw(
        models=[
            {"modelId": "m1", "availability": "1 Available units", "availabilityInfo": "Now"},
        ],
        rentals=[
            {"modelId": "m1", "availability": "Now"},
        ],
    )
    listing = scraper._normalize_apartments_com_listing(raw)
    assert listing is not None
    assert listing.available_date == "Now"


# --- Test 3: All models "0 Available units" → returns "Unavailable" ---
def test_no_available_units(scraper):
    raw = _make_raw(
        models=[
            {"modelId": "m1", "availability": "0 Available units", "availabilityInfo": "N/A"},
            {"modelId": "m2", "availability": "0 Available units", "availabilityInfo": "N/A"},
        ],
        rentals=[],
    )
    listing = scraper._normalize_apartments_com_listing(raw)
    assert listing is not None
    assert listing.available_date == "Unavailable"


# --- Test 4: Mixed availability → only considers available models ---
def test_mixed_availability(scraper):
    raw = _make_raw(
        models=[
            {"modelId": "m1", "availability": "0 Available units", "availabilityInfo": "N/A"},
            {"modelId": "m2", "availability": "1 Available units", "availabilityInfo": "Now"},
        ],
        rentals=[
            {"modelId": "m1", "availableDate": "2026-04-01T00:00:00-04:00"},
            {"modelId": "m2", "availableDate": "2026-06-01T00:00:00-04:00"},
        ],
    )
    listing = scraper._normalize_apartments_com_listing(raw)
    assert listing is not None
    # m1 has no availability, so its rental is ignored; only m2's date is used
    assert listing.available_date == "2026-06-01"


# --- Test 5: No models/rentals arrays → returns None ---
def test_no_models_or_rentals(scraper):
    raw = _make_raw()  # no models or rentals keys
    listing = scraper._normalize_apartments_com_listing(raw)
    assert listing is not None
    assert listing.available_date is None


# --- Test 6: Malformed availableDate → skips without crashing ---
def test_malformed_date_skipped(scraper):
    raw = _make_raw(
        models=[
            {"modelId": "m1", "availability": "1 Available units"},
        ],
        rentals=[
            {"modelId": "m1", "availableDate": "bad"},
            {"modelId": "m1", "availableDate": ""},
            {"modelId": "m1", "availableDate": None},
        ],
    )
    listing = scraper._normalize_apartments_com_listing(raw)
    assert listing is not None
    # All dates are invalid/short, so falls back to "Now" (model has units)
    assert listing.available_date == "Now"


# --- Test 13: Multiple rentals same model, different dates → picks earliest ---
def test_multiple_rentals_picks_earliest(scraper):
    raw = _make_raw(
        models=[
            {"modelId": "m1", "availability": "3 Available units"},
        ],
        rentals=[
            {"modelId": "m1", "availableDate": "2026-07-01T00:00:00-04:00"},
            {"modelId": "m1", "availableDate": "2026-05-15T00:00:00-04:00"},
            {"modelId": "m1", "availableDate": "2026-06-01T00:00:00-04:00"},
        ],
    )
    listing = scraper._normalize_apartments_com_listing(raw)
    assert listing.available_date == "2026-05-15"


# --- Test 14: Rental modelId not in models array → ignored ---
def test_orphaned_rental_ignored(scraper):
    raw = _make_raw(
        models=[
            {"modelId": "m1", "availability": "1 Available units"},
        ],
        rentals=[
            {"modelId": "m_orphan", "availableDate": "2026-04-01T00:00:00-04:00"},
        ],
    )
    listing = scraper._normalize_apartments_com_listing(raw)
    # m1 has units but no matching rentals → "Now"
    assert listing.available_date == "Now"


# --- Test 15: Timezone offset in availableDate → parses correctly ---
def test_timezone_offset_parsed(scraper):
    raw = _make_raw(
        models=[
            {"modelId": "m1", "availability": "1 Available units"},
        ],
        rentals=[
            {"modelId": "m1", "availableDate": "2099-10-10T00:00:00Z"},
            {"modelId": "m1", "availableDate": "2099-10-05T00:00:00-05:00"},
        ],
    )
    listing = scraper._normalize_apartments_com_listing(raw)
    # Earliest upcoming date wins (both are in the future)
    assert listing.available_date == "2099-10-05"


# --- Test 16: Model has units but zero matching rentals → "Now" ---
def test_model_with_units_no_matching_rentals(scraper):
    raw = _make_raw(
        models=[
            {"modelId": "m1", "availability": "2 Available units"},
        ],
        rentals=[],  # empty rentals
    )
    listing = scraper._normalize_apartments_com_listing(raw)
    assert listing.available_date == "Now"


# --- Test 17: All rentals have past dates → returns earliest ---
def test_past_dates_collapse_to_now(scraper):
    """All-past availableDates collapse to 'Now' — Apify rental records
    retain original lease start dates that can be years stale."""
    raw = _make_raw(
        models=[
            {"modelId": "m1", "availability": "1 Available units"},
        ],
        rentals=[
            {"modelId": "m1", "availableDate": "2025-01-01T00:00:00-04:00"},
            {"modelId": "m1", "availableDate": "2025-06-15T00:00:00-04:00"},
        ],
    )
    listing = scraper._normalize_apartments_com_listing(raw)
    assert listing.available_date == "Now"
