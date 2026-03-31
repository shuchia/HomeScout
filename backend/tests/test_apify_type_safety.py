"""Tests that the Apify normalizer handles unexpected field types without crashing.

These tests protect against silent failures where Apify returns a field as a
different type than expected (e.g., `fees` as list instead of dict), causing
the normalizer to crash and silently drop all listings for a property.
"""
import pytest
from app.services.scrapers.apify_service import ApifyService


@pytest.fixture
def scraper():
    return ApifyService(source_id="apartments_com")


def _base():
    """Minimal valid apartments.com listing."""
    return {
        "id": "test",
        "location": {"fullAddress": "123 Main St, Test, PA 12345", "city": "Test", "state": "PA", "postalCode": "12345"},
        "rent": {"min": 1000, "max": 1500},
        "beds": "1 bd",
        "baths": "1 ba",
        "sqft": "600",
        "url": "https://example.com",
    }


# --- location field ---

def test_location_as_list(scraper):
    raw = {**_base(), "location": [{"fullAddress": "123 Main"}]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is None  # filtered (no address), but no crash


def test_location_as_string(scraper):
    raw = {**_base(), "location": "123 Main St"}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is None


def test_location_as_none(scraper):
    raw = {**_base(), "location": None}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is None


# --- rent field ---

def test_rent_as_string(scraper):
    raw = {**_base(), "rent": "$1,000"}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
    assert result.rent == 1000


def test_rent_as_int(scraper):
    raw = {**_base(), "rent": 1000}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


def test_rent_as_none(scraper):
    raw = {**_base(), "rent": None}
    assert scraper._normalize_apartments_com_listing(raw) is None


def test_rent_as_list(scraper):
    raw = {**_base(), "rent": [1000, 1500]}
    assert scraper._normalize_apartments_com_listing(raw) is None


# --- coordinates field ---

def test_coordinates_as_list(scraper):
    raw = {**_base(), "coordinates": [40.7, -77.8]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None  # should not crash


def test_coordinates_as_none(scraper):
    raw = {**_base(), "coordinates": None}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


def test_coordinates_as_string(scraper):
    raw = {**_base(), "coordinates": "40.7,-77.8"}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


# --- sqft field ---

def test_sqft_as_int(scraper):
    raw = {**_base(), "sqft": 600}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
    assert result.sqft == 600


def test_sqft_as_float(scraper):
    raw = {**_base(), "sqft": 600.5}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
    assert result.sqft == 600


def test_sqft_as_none(scraper):
    raw = {**_base(), "sqft": None}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
    assert result.sqft is None


# --- fees field ---

def test_fees_as_list(scraper):
    raw = {**_base(), "fees": [{"title": "Details", "policies": []}]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


def test_fees_as_none(scraper):
    raw = {**_base(), "fees": None}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


def test_fees_as_string(scraper):
    raw = {**_base(), "fees": "N/A"}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


# --- petPolicy field ---

def test_pet_policy_as_list(scraper):
    raw = {**_base(), "petPolicy": [{"type": "cat"}]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


def test_pet_policy_as_string(scraper):
    raw = {**_base(), "petPolicy": "No pets"}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


# --- contact field ---

def test_contact_as_list(scraper):
    raw = {**_base(), "contact": [{"phone": "555-1234"}]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


def test_contact_as_string(scraper):
    raw = {**_base(), "contact": "555-1234"}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


def test_contact_as_none(scraper):
    raw = {**_base(), "contact": None}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


# --- propertyManagement field ---

def test_mgmt_as_list(scraper):
    raw = {**_base(), "propertyManagement": ["Company"]}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


def test_mgmt_as_string(scraper):
    raw = {**_base(), "propertyManagement": "Company Name"}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


# --- amenities field ---

def test_amenities_as_string(scraper):
    raw = {**_base(), "amenities": "pool,gym"}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


def test_amenities_as_none(scraper):
    raw = {**_base(), "amenities": None}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


def test_amenities_as_dict(scraper):
    raw = {**_base(), "amenities": {"pool": True}}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


# --- models/rentals fields ---

def test_models_as_dict(scraper):
    raw = {**_base(), "models": {"m1": "data"}}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


def test_models_as_string(scraper):
    raw = {**_base(), "models": "none"}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


def test_rentals_as_dict(scraper):
    raw = {**_base(), "rentals": {"r1": "data"}}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


# --- beds/baths as non-string ---

def test_beds_as_int(scraper):
    raw = {**_base(), "beds": 2}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None


def test_baths_as_float(scraper):
    raw = {**_base(), "baths": 1.5}
    result = scraper._normalize_apartments_com_listing(raw)
    assert result is not None
