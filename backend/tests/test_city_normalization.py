"""Tests for folding neighbourhood names into their municipality.

apartments.com labels listings with the neighbourhood rather than the city.
Left alone, comps keyed on `city` compute a separate median for Allston as
though it were a different market from Boston.

Boston cannot reuse the NYC zip-prefix approach: 021xx also covers Brookline,
Cambridge and Somerville, which are genuinely separate cities with their own
rents. These tests pin that distinction down, because folding a real
municipality in would silently corrupt comps for both markets.
"""
import pytest

from app.services.scrapers.apify_service import (
    ApifyService,
    _BOSTON_NEIGHBORHOODS,
    _NYC_ZIP_PREFIXES,
)


def _raw(city, state, zip_code="02134", neighborhood=None):
    return {
        "id": "p1",
        "propertyName": "Test Property",
        "url": "https://www.apartments.com/test/abc123/",
        "location": {
            "city": city,
            "state": state,
            "postalCode": zip_code,
            "streetAddress": "1 Test St",
            "fullAddress": f"1 Test St, {city}, {state} {zip_code}",
            **({"neighborhood": neighborhood} if neighborhood else {}),
        },
        "beds": "2 bd",
        "baths": "1 ba",
        "sqft": "800",
        "baseRent": {"min": 2000, "max": 2000},
        "totalRent": {"min": 2000, "max": 2000},
        "models": [],
        "fees": [],
        "amenities": [],
        "coordinates": {"latitude": 42.35, "longitude": -71.13},
    }


class TestBostonNeighborhoodSet:
    """The membership list is the whole safety property here."""

    @pytest.mark.parametrize("name", [
        "allston", "brighton", "charlestown", "dorchester", "east boston",
        "hyde park", "jamaica plain", "mattapan", "roslindale", "roxbury",
        "south boston", "west roxbury",
    ])
    def test_real_boston_neighborhoods_are_included(self, name):
        assert name in _BOSTON_NEIGHBORHOODS

    @pytest.mark.parametrize("name", [
        "brookline", "cambridge", "somerville", "chelsea", "everett",
        "revere", "watertown", "quincy", "newton", "medford", "malden",
    ])
    def test_separate_municipalities_are_excluded(self, name):
        """Folding these in would merge distinct rental markets."""
        assert name not in _BOSTON_NEIGHBORHOODS

    def test_chestnut_hill_is_excluded(self):
        """Straddles Boston, Brookline and Newton — genuinely ambiguous, so it
        is left as-is rather than guessed at."""
        assert "chestnut hill" not in _BOSTON_NEIGHBORHOODS

    def test_boston_itself_is_not_in_the_set(self):
        """Would be a no-op, but its presence would signal confused intent."""
        assert "boston" not in _BOSTON_NEIGHBORHOODS


class TestBostonNormalizationOnWrite:
    def setup_method(self):
        self.svc = ApifyService("apartments_com")

    def test_allston_becomes_boston(self):
        listing = self.svc._normalize_apartments_com_listing(_raw("Allston", "MA"))
        assert listing is not None
        assert listing.city == "Boston"

    def test_original_name_is_preserved_as_neighborhood(self):
        """Cards should still read "Allston, MA" — only comps grouping changes."""
        listing = self.svc._normalize_apartments_com_listing(_raw("Allston", "MA"))
        assert listing.neighborhood == "Allston"

    def test_existing_neighborhood_is_not_clobbered(self):
        listing = self.svc._normalize_apartments_com_listing(
            _raw("Allston", "MA", neighborhood="Lower Allston")
        )
        assert listing.city == "Boston"
        assert listing.neighborhood == "Lower Allston"

    @pytest.mark.parametrize("city", ["Brookline", "Cambridge", "Somerville", "Revere"])
    def test_separate_cities_are_left_alone(self, city):
        listing = self.svc._normalize_apartments_com_listing(_raw(city, "MA", "02445"))
        assert listing.city == city

    def test_matching_is_case_and_whitespace_insensitive(self):
        listing = self.svc._normalize_apartments_com_listing(_raw("  EAST BOSTON ", "MA"))
        assert listing.city == "Boston"

    def test_same_name_in_another_state_is_untouched(self):
        """There is a Brighton in several states; only MA folds into Boston."""
        listing = self.svc._normalize_apartments_com_listing(_raw("Brighton", "CO", "80601"))
        assert listing.city == "Brighton"

    def test_boston_stays_boston(self):
        listing = self.svc._normalize_apartments_com_listing(_raw("Boston", "MA", "02108"))
        assert listing.city == "Boston"


class TestNycNormalizationStillWorks:
    """Boston's branch is an elif on the NYC one — make sure it didn't break it."""

    def setup_method(self):
        self.svc = ApifyService("apartments_com")

    def test_brooklyn_still_becomes_new_york(self):
        listing = self.svc._normalize_apartments_com_listing(_raw("Brooklyn", "NY", "11201"))
        assert listing.city == "New York"
        assert listing.neighborhood == "Brooklyn"

    def test_long_island_is_still_excluded(self):
        """115-119 are Nassau/Suffolk, deliberately not NYC."""
        listing = self.svc._normalize_apartments_com_listing(_raw("Hempstead", "NY", "11550"))
        assert listing.city == "Hempstead"
        assert "115" not in _NYC_ZIP_PREFIXES


class TestScrapeInputFlags:
    """The include* flags drive per-listing detail fetches — cost and latency."""

    def setup_method(self):
        self.svc = ApifyService("apartments_com")

    def test_visuals_on_for_phash_reference_set(self):
        """Images are absent entirely when off, and they are the reference set
        for perceptual-hash scam detection."""
        actor_input = self.svc._build_apartments_com_input("Boston", "MA", 1000)
        assert actor_input["includeVisuals"] is True

    def test_walk_score_on_to_avoid_a_visible_regression(self):
        actor_input = self.svc._build_apartments_com_input("Boston", "MA", 1000)
        assert actor_input["includeWalkScore"] is True

    def test_reviews_and_interior_amenities_off(self):
        """`rating` and community amenities already arrive without these."""
        actor_input = self.svc._build_apartments_com_input("Boston", "MA", 1000)
        assert actor_input["includeReviews"] is False
        assert actor_input["includeInteriorAmenities"] is False

    def test_max_items_is_passed_through(self):
        actor_input = self.svc._build_apartments_com_input("Boston", "MA", 1000)
        assert actor_input["maxItems"] == 1000
