"""Tests for Claude service data preparation."""
import pytest
from app.services.claude_service import ClaudeService


class TestPrepareApartmentForScoring:
    """Verify Claude receives full data without truncation."""

    def test_full_description_sent(self):
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

    def test_neighborhood_included(self):
        apt = {
            "id": "test", "address": "123 Main St", "rent": 2000,
            "bedrooms": 2, "bathrooms": 1, "sqft": 900,
            "property_type": "Apartment", "available_date": "2026-03-01",
            "neighborhood": "Center City", "description": "Nice",
            "amenities": [], "data_quality_score": 85, "heuristic_score": 78,
        }
        slim = ClaudeService.prepare_apartment_for_scoring(apt)
        assert slim["neighborhood"] == "Center City"


class TestPriceOnRequestPayload:
    """An unpriced floorplan must not reach Claude with a rent attached.

    floorplans.py leaves `rent` numeric as a fallback so heuristic scoring can
    do `rent <= budget`, and the heuristic path then drops the budget term
    rather than score against it (decision D1). Passing that same fallback to
    Claude got it quoted back to the user as "$3,390 advertised rent" on a card
    whose price line read "Price on request".
    """

    BASE = {
        "id": "apt-1",
        "address": "235 Old Colony Ave, Boston, MA",
        "rent": 3390,
        "bedrooms": 0,
        "bathrooms": 1,
        "sqft": 631,
        "true_cost_monthly": 3725,
        "true_cost_move_in": 4000,
        "est_electric": 85,
        "est_gas": 50,
        "est_water": 35,
        "est_internet": 65,
        "est_renters_insurance": 18,
        "est_laundry": 0,
    }

    @staticmethod
    def _prep(apt):
        from app.services.claude_service import ClaudeService
        return ClaudeService.prepare_apartment_for_scoring(apt)

    def test_priced_listing_still_sends_rent_and_true_cost(self):
        data = self._prep(dict(self.BASE))
        assert data["rent"] == 3390
        assert data["true_cost_monthly"] == 3725
        assert "price_on_request" not in data

    def test_unpriced_floorplan_sends_no_rent(self):
        data = self._prep({**self.BASE, "matched_floorplan": {"price_on_request": True}})
        assert "rent" not in data
        assert data["price_on_request"] is True

    def test_unpriced_floorplan_sends_no_total(self):
        """true_cost_monthly is rent + extras, so publishing it would disclose
        the withheld rent by subtraction."""
        data = self._prep({**self.BASE, "matched_floorplan": {"price_on_request": True}})
        assert "true_cost_monthly" not in data
        assert "true_cost_move_in" not in data
        assert "cost_details" not in data

    def test_unpriced_floorplan_still_sends_the_known_extras(self):
        """Utilities and fees are estimated from the building and zip, not from
        the unit's rent, so they survive — and they are the useful half."""
        data = self._prep({**self.BASE, "matched_floorplan": {"price_on_request": True}})
        assert data["est_monthly_extras"] == 253

    def test_top_level_flag_is_honoured_too(self):
        """apartment_service sets price_on_request on the apartment itself;
        matched_floorplan carries it for the card. Either must work."""
        data = self._prep({**self.BASE, "price_on_request": True})
        assert "rent" not in data
        assert data["price_on_request"] is True

    def test_per_person_note_is_suppressed_when_unpriced(self):
        """The note interpolates the rent, so it would leak the figure."""
        data = self._prep({
            **self.BASE,
            "pricing_model": "per_person",
            "matched_floorplan": {"price_on_request": True},
        })
        assert "pricing_note" not in data

    def test_prompt_forbids_inventing_a_price(self):
        from app.services.claude_service import ClaudeService
        import inspect
        src = inspect.getsource(ClaudeService.score_apartments)
        assert "price_on_request" in src
        assert "neither a bargain nor a dealbreaker" in src
