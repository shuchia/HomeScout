"""
Tests for the search endpoint with paginated heuristic-only results.
AI scoring is now handled by the separate /api/search/score-batch endpoint.
"""
import pytest
from unittest.mock import patch, MagicMock
import httpx
import asyncio

# Base URL for the running backend
BASE_URL = "http://localhost:8000"


class TestSearchEndpoint:
    """Test the /api/search endpoint."""

    def test_search_returns_apartments(self):
        """Test that search returns apartments matching criteria."""
        response = httpx.post(
            f"{BASE_URL}/api/search",
            json={
                "city": "Pittsburgh, PA",
                "budget": 2000,
                "bedrooms": 1,
                "bathrooms": 1,
                "property_type": "Apartment",
                "move_in_date": "2026-03-01"
            },
            timeout=60.0
        )

        assert response.status_code == 200
        data = response.json()

        # Should return apartments, total count, and pagination fields
        assert "apartments" in data
        assert "total_results" in data
        assert "page" in data
        assert "has_more" in data
        assert isinstance(data["apartments"], list)

        # If there are results, verify structure
        if data["apartments"]:
            apt = data["apartments"][0]
            assert "id" in apt
            assert "address" in apt
            assert "rent" in apt
            assert "match_score" in apt
            assert "reasoning" in apt
            assert "highlights" in apt
            # Search endpoint returns null scores (AI via score-batch)
            assert apt["match_score"] is None

    def test_search_respects_budget_filter(self):
        """Test that all returned apartments are within budget."""
        budget = 1500
        response = httpx.post(
            f"{BASE_URL}/api/search",
            json={
                "city": "Pittsburgh, PA",
                "budget": budget,
                "bedrooms": 1,
                "bathrooms": 1,
                "property_type": "Apartment",
                "move_in_date": "2026-03-01"
            },
            timeout=60.0
        )

        assert response.status_code == 200
        data = response.json()

        for apt in data["apartments"]:
            assert apt["rent"] <= budget, f"Apartment rent {apt['rent']} exceeds budget {budget}"

    def test_search_respects_bedroom_filter(self):
        """Test that all returned apartments have correct bedroom count."""
        bedrooms = 2
        response = httpx.post(
            f"{BASE_URL}/api/search",
            json={
                "city": "Pittsburgh, PA",
                "budget": 3000,
                "bedrooms": bedrooms,
                "bathrooms": 1,
                "property_type": "Apartment",
                "move_in_date": "2026-03-01"
            },
            timeout=60.0
        )

        assert response.status_code == 200
        data = response.json()

        for apt in data["apartments"]:
            assert apt["bedrooms"] == bedrooms, f"Expected {bedrooms} bedrooms, got {apt['bedrooms']}"

    def test_search_returns_null_match_scores(self):
        """Test that search returns null match scores (AI scoring moved to score-batch)."""
        response = httpx.post(
            f"{BASE_URL}/api/search",
            json={
                "city": "Pittsburgh, PA",
                "budget": 2000,
                "bedrooms": 1,
                "bathrooms": 1,
                "property_type": "Apartment",
                "move_in_date": "2026-03-01"
            },
            timeout=60.0
        )

        assert response.status_code == 200
        data = response.json()

        for apt in data["apartments"]:
            assert apt["match_score"] is None, f"Expected null match_score, got {apt['match_score']}"

    def test_search_includes_pagination_fields(self):
        """Test that response includes page and has_more fields."""
        response = httpx.post(
            f"{BASE_URL}/api/search",
            json={
                "city": "Pittsburgh, PA",
                "budget": 2000,
                "bedrooms": 1,
                "bathrooms": 1,
                "property_type": "Apartment",
                "move_in_date": "2026-03-01"
            },
            timeout=60.0
        )

        assert response.status_code == 200
        data = response.json()

        assert "page" in data
        assert "has_more" in data
        assert isinstance(data["page"], int)
        assert isinstance(data["has_more"], bool)
        assert data["page"] >= 1

    def test_search_with_preferences(self):
        """Test that preferences are accepted (scoring via score-batch)."""
        response = httpx.post(
            f"{BASE_URL}/api/search",
            json={
                "city": "Pittsburgh, PA",
                "budget": 2000,
                "bedrooms": 1,
                "bathrooms": 1,
                "property_type": "Apartment",
                "move_in_date": "2026-03-01",
                "other_preferences": "pet friendly, close to downtown"
            },
            timeout=60.0
        )

        assert response.status_code == 200
        data = response.json()
        assert "apartments" in data

    def test_search_bryn_mawr(self):
        """Test search for Bryn Mawr apartments."""
        response = httpx.post(
            f"{BASE_URL}/api/search",
            json={
                "city": "Bryn Mawr, PA",
                "budget": 2500,
                "bedrooms": 1,
                "bathrooms": 1,
                "property_type": "Apartment",
                "move_in_date": "2026-03-01"
            },
            timeout=60.0
        )

        assert response.status_code == 200
        data = response.json()

        # Should return results (we have Bryn Mawr listings)
        assert "apartments" in data
        assert "total_results" in data

        # Verify city in results
        for apt in data["apartments"]:
            assert "Bryn Mawr" in apt["address"] or "PA" in apt["address"]

    def test_search_no_results(self):
        """Test search with impossible criteria returns empty."""
        response = httpx.post(
            f"{BASE_URL}/api/search",
            json={
                "city": "Nonexistent City, XX",
                "budget": 500,
                "bedrooms": 10,
                "bathrooms": 5,
                "property_type": "Castle",
                "move_in_date": "2026-03-01"
            },
            timeout=60.0
        )

        assert response.status_code == 200
        data = response.json()

        assert data["apartments"] == []
        assert data["total_results"] == 0

    def test_search_limit_results(self):
        """Test that search returns at most 10 results per page."""
        response = httpx.post(
            f"{BASE_URL}/api/search",
            json={
                "city": "Pittsburgh, PA",
                "budget": 5000,  # High budget to get many results
                "bedrooms": 1,
                "bathrooms": 1,
                "property_type": "Apartment",
                "move_in_date": "2026-03-01"
            },
            timeout=60.0
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["apartments"]) <= 10, "Should return at most 10 results per page"


class TestHealthEndpoints:
    """Test health and stats endpoints."""

    def test_health_endpoint(self):
        """Test /health returns healthy status."""
        response = httpx.get(f"{BASE_URL}/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_root_endpoint(self):
        """Test / returns healthy status."""
        response = httpx.get(f"{BASE_URL}/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_apartments_count(self):
        """Test /api/apartments/count returns count."""
        response = httpx.get(f"{BASE_URL}/api/apartments/count")

        assert response.status_code == 200
        data = response.json()
        assert "total_apartments" in data
        assert isinstance(data["total_apartments"], int)

    def test_apartments_stats(self):
        """Test /api/apartments/stats returns statistics."""
        response = httpx.get(f"{BASE_URL}/api/apartments/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "stats" in data
        stats = data["stats"]
        assert "total_active" in stats
        assert "by_city" in stats


class TestListEndpoint:
    """Test /api/apartments/list endpoint."""

    def test_list_all_apartments(self):
        """Test listing apartments without filters."""
        response = httpx.get(f"{BASE_URL}/api/apartments/list")

        assert response.status_code == 200
        data = response.json()
        assert "apartments" in data
        assert "total" in data

    def test_list_by_city(self):
        """Test listing apartments filtered by city."""
        response = httpx.get(f"{BASE_URL}/api/apartments/list?city=Pittsburgh")

        assert response.status_code == 200
        data = response.json()

        for apt in data["apartments"]:
            assert "Pittsburgh" in apt["address"].lower() or "pittsburgh" in apt.get("city", "").lower()

    def test_list_with_pagination(self):
        """Test listing with limit and offset."""
        response = httpx.get(f"{BASE_URL}/api/apartments/list?limit=5&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert len(data["apartments"]) <= 5

    def test_list_with_rent_filter(self):
        """Test listing with rent range filter."""
        max_rent = 1500
        response = httpx.get(f"{BASE_URL}/api/apartments/list?max_rent={max_rent}")

        assert response.status_code == 200
        data = response.json()

        for apt in data["apartments"]:
            assert apt["rent"] <= max_rent


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])
