"""Tests for Claude score caching."""
import pytest
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

    def test_cache_key_starts_with_prefix(self):
        key = ApartmentService.build_score_cache_key(
            city="Philadelphia", budget=2000, bedrooms=2, bathrooms=1,
            property_type="Apartment", move_in_date="2026-03-01",
            other_preferences="gym", apartment_ids=["a"],
        )
        assert key.startswith("claude_score:")
