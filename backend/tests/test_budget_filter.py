"""Tests for soft budget filter (10% buffer)."""
import pytest
from app.services.apartment_service import ApartmentService


class TestSoftBudgetJsonFilter:
    """JSON mode: budget filter should include up to 10% over."""

    def test_at_budget_included(self):
        svc = ApartmentService.__new__(ApartmentService)
        svc._use_database = False
        svc._apartments_data = [
            {"id": "1", "address": "Philadelphia, PA", "rent": 2000,
             "bedrooms": 2, "bathrooms": 1, "property_type": "Apartment",
             "available_date": "2026-03-01"},
        ]
        result = svc._search_json("Philadelphia", 2000, 2, 1, "Apartment", "2026-04-01")
        assert len(result) == 1

    def test_5_percent_over_included(self):
        svc = ApartmentService.__new__(ApartmentService)
        svc._use_database = False
        svc._apartments_data = [
            {"id": "1", "address": "Philadelphia, PA", "rent": 2100,
             "bedrooms": 2, "bathrooms": 1, "property_type": "Apartment",
             "available_date": "2026-03-01"},
        ]
        result = svc._search_json("Philadelphia", 2000, 2, 1, "Apartment", "2026-04-01")
        assert len(result) == 1

    def test_over_10_percent_excluded(self):
        svc = ApartmentService.__new__(ApartmentService)
        svc._use_database = False
        svc._apartments_data = [
            {"id": "1", "address": "Philadelphia, PA", "rent": 2201,
             "bedrooms": 2, "bathrooms": 1, "property_type": "Apartment",
             "available_date": "2026-03-01"},
        ]
        result = svc._search_json("Philadelphia", 2000, 2, 1, "Apartment", "2026-04-01")
        assert len(result) == 0
