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
