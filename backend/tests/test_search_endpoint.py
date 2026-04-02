"""
Tests for the search endpoint with paginated heuristic-only results.
AI scoring is now handled by the separate /api/search/score-batch endpoint.
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth import get_optional_user

client = TestClient(app)

SAMPLE_APARTMENT = {
    "id": "apt-001",
    "address": "123 Main St, Pittsburgh, PA 15213",
    "rent": 1400,
    "bedrooms": 1,
    "bathrooms": 1,
    "sqft": 700,
    "property_type": "Apartment",
    "available_date": "2026-05-01",
    "amenities": ["Parking", "Laundry"],
    "neighborhood": "Oakland",
    "description": "Nice apartment",
    "images": ["https://example.com/img.jpg"],
}

SAMPLE_APARTMENT_2 = {
    "id": "apt-002",
    "address": "456 Oak Ave, Pittsburgh, PA 15213",
    "rent": 1800,
    "bedrooms": 2,
    "bathrooms": 1,
    "sqft": 900,
    "property_type": "Apartment",
    "available_date": "2026-05-01",
    "amenities": ["Gym", "Pool"],
    "neighborhood": "Shadyside",
    "description": "Spacious apartment",
    "images": ["https://example.com/img2.jpg"],
}


def _mock_anon():
    return None


class TestSearchEndpoint:
    """Test the /api/search endpoint."""

    def test_search_returns_apartments(self):
        """Test that search returns apartments matching criteria."""
        app.dependency_overrides[get_optional_user] = _mock_anon
        try:
            with patch(
                "app.main.apartment_service.get_apartments_paginated",
                new_callable=AsyncMock,
                return_value=([SAMPLE_APARTMENT], 1, False),
            ):
                response = client.post(
                    "/api/search",
                    json={
                        "city": "Pittsburgh, PA",
                        "budget": 2000,
                        "bedrooms": 1,
                        "bathrooms": 1,
                        "property_type": "Apartment",
                        "move_in_date": "2026-03-01",
                    },
                )

            assert response.status_code == 200
            data = response.json()

            # Should return apartments, total count, and pagination fields
            assert "apartments" in data
            assert "total_results" in data
            assert "page" in data
            assert "has_more" in data
            assert isinstance(data["apartments"], list)
            assert len(data["apartments"]) == 1

            apt = data["apartments"][0]
            assert "id" in apt
            assert "address" in apt
            assert "rent" in apt
            assert "match_score" in apt
            assert "reasoning" in apt
            assert "highlights" in apt
            # Search endpoint returns null scores (AI via score-batch)
            assert apt["match_score"] is None
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_search_respects_budget_filter(self):
        """Test that all returned apartments are within budget."""
        budget = 1500
        # Only apt with rent <= 1500 should be returned
        app.dependency_overrides[get_optional_user] = _mock_anon
        try:
            with patch(
                "app.main.apartment_service.get_apartments_paginated",
                new_callable=AsyncMock,
                return_value=([SAMPLE_APARTMENT], 1, False),
            ):
                response = client.post(
                    "/api/search",
                    json={
                        "city": "Pittsburgh, PA",
                        "budget": budget,
                        "bedrooms": 1,
                        "bathrooms": 1,
                        "property_type": "Apartment",
                        "move_in_date": "2026-03-01",
                    },
                )

            assert response.status_code == 200
            data = response.json()

            for apt in data["apartments"]:
                assert apt["rent"] <= budget
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_search_respects_bedroom_filter(self):
        """Test that all returned apartments have correct bedroom count."""
        bedrooms = 2
        app.dependency_overrides[get_optional_user] = _mock_anon
        try:
            with patch(
                "app.main.apartment_service.get_apartments_paginated",
                new_callable=AsyncMock,
                return_value=([SAMPLE_APARTMENT_2], 1, False),
            ):
                response = client.post(
                    "/api/search",
                    json={
                        "city": "Pittsburgh, PA",
                        "budget": 3000,
                        "bedrooms": bedrooms,
                        "bathrooms": 1,
                        "property_type": "Apartment",
                        "move_in_date": "2026-03-01",
                    },
                )

            assert response.status_code == 200
            data = response.json()

            for apt in data["apartments"]:
                assert apt["bedrooms"] == bedrooms
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_search_returns_null_match_scores(self):
        """Test that search returns null match scores (AI scoring moved to score-batch)."""
        app.dependency_overrides[get_optional_user] = _mock_anon
        try:
            with patch(
                "app.main.apartment_service.get_apartments_paginated",
                new_callable=AsyncMock,
                return_value=([SAMPLE_APARTMENT], 1, False),
            ):
                response = client.post(
                    "/api/search",
                    json={
                        "city": "Pittsburgh, PA",
                        "budget": 2000,
                        "bedrooms": 1,
                        "bathrooms": 1,
                        "property_type": "Apartment",
                        "move_in_date": "2026-03-01",
                    },
                )

            assert response.status_code == 200
            data = response.json()

            for apt in data["apartments"]:
                assert apt["match_score"] is None
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_search_includes_pagination_fields(self):
        """Test that response includes page and has_more fields."""
        app.dependency_overrides[get_optional_user] = _mock_anon
        try:
            with patch(
                "app.main.apartment_service.get_apartments_paginated",
                new_callable=AsyncMock,
                return_value=([SAMPLE_APARTMENT], 1, False),
            ):
                response = client.post(
                    "/api/search",
                    json={
                        "city": "Pittsburgh, PA",
                        "budget": 2000,
                        "bedrooms": 1,
                        "bathrooms": 1,
                        "property_type": "Apartment",
                        "move_in_date": "2026-03-01",
                    },
                )

            assert response.status_code == 200
            data = response.json()

            assert "page" in data
            assert "has_more" in data
            assert isinstance(data["page"], int)
            assert isinstance(data["has_more"], bool)
            assert data["page"] >= 1
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_search_with_preferences(self):
        """Test that preferences are accepted (scoring via score-batch)."""
        app.dependency_overrides[get_optional_user] = _mock_anon
        try:
            with patch(
                "app.main.apartment_service.get_apartments_paginated",
                new_callable=AsyncMock,
                return_value=([SAMPLE_APARTMENT], 1, False),
            ):
                response = client.post(
                    "/api/search",
                    json={
                        "city": "Pittsburgh, PA",
                        "budget": 2000,
                        "bedrooms": 1,
                        "bathrooms": 1,
                        "property_type": "Apartment",
                        "move_in_date": "2026-03-01",
                        "other_preferences": "pet friendly, close to downtown",
                    },
                )

            assert response.status_code == 200
            data = response.json()
            assert "apartments" in data
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_search_no_results(self):
        """Test search with no matching criteria returns empty."""
        app.dependency_overrides[get_optional_user] = _mock_anon
        try:
            with patch(
                "app.main.apartment_service.get_apartments_paginated",
                new_callable=AsyncMock,
                return_value=([], 0, False),
            ):
                response = client.post(
                    "/api/search",
                    json={
                        "city": "Nonexistent City, XX",
                        "budget": 500,
                        "bedrooms": 10,
                        "bathrooms": 5,
                        "property_type": "Castle",
                        "move_in_date": "2026-03-01",
                    },
                )

            assert response.status_code == 200
            data = response.json()

            assert data["apartments"] == []
            assert data["total_results"] == 0
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_search_limit_results(self):
        """Test that search returns at most 10 results per page."""
        # Create 10 apartments to simulate a full page
        apartments = [
            {**SAMPLE_APARTMENT, "id": f"apt-{i:03d}"} for i in range(10)
        ]
        app.dependency_overrides[get_optional_user] = _mock_anon
        try:
            with patch(
                "app.main.apartment_service.get_apartments_paginated",
                new_callable=AsyncMock,
                return_value=(apartments, 25, True),
            ):
                response = client.post(
                    "/api/search",
                    json={
                        "city": "Pittsburgh, PA",
                        "budget": 5000,
                        "bedrooms": 1,
                        "bathrooms": 1,
                        "property_type": "Apartment",
                        "move_in_date": "2026-03-01",
                    },
                )

            assert response.status_code == 200
            data = response.json()

            assert len(data["apartments"]) <= 10
        finally:
            app.dependency_overrides.pop(get_optional_user, None)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
