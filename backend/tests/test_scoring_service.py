"""Tests for ScoringService heuristic scoring."""
import pytest
from datetime import datetime, timedelta
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
        score = ScoringService.budget_fit_score(rent=2100, budget=2000)
        assert score == 50

    def test_rent_10_percent_over_returns_0(self):
        score = ScoringService.budget_fit_score(rent=2200, budget=2000)
        assert score == 0

    def test_rent_over_10_percent_returns_0(self):
        score = ScoringService.budget_fit_score(rent=2500, budget=2000)
        assert score == 0

    def test_rent_1_percent_over(self):
        score = ScoringService.budget_fit_score(rent=2020, budget=2000)
        assert 85 <= score <= 95


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
        assert score <= 45

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


class TestAmenityMatchScore:
    """Amenity match component: 20% weight."""

    def test_all_preferences_matched(self):
        score = ScoringService.amenity_match_score(
            other_preferences="I need parking and a gym",
            amenities=["Covered Parking", "Fitness Center", "Pool"],
        )
        assert score == 100

    def test_partial_match(self):
        score = ScoringService.amenity_match_score(
            other_preferences="pet-friendly with parking and gym",
            amenities=["Fitness Center"],
        )
        assert 30 <= score <= 35

    def test_no_match(self):
        score = ScoringService.amenity_match_score(
            other_preferences="I need a pool",
            amenities=["Parking", "Gym"],
        )
        assert score == 0

    def test_no_preferences_returns_100(self):
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
