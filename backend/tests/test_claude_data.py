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
