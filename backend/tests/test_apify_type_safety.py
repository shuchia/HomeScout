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


# --- fees nested list format (epctex actor) ---

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
    assert result.admin_fee == 150


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


# --- monthly fee pattern matching ---

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
