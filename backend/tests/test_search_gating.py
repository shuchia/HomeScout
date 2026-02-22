"""Tests for search endpoint tier gating."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth import get_optional_user, UserContext

client = TestClient(app)

SEARCH_BODY = {
    "city": "Pittsburgh",
    "budget": 2000,
    "bedrooms": 2,
    "bathrooms": 1,
    "property_type": "Apartment",
    "move_in_date": "2026-06-01",
}

SAMPLE_APARTMENT = {
    "id": "apt-001",
    "address": "123 Main St, Pittsburgh, PA 15213",
    "rent": 1800,
    "bedrooms": 2,
    "bathrooms": 1,
    "sqft": 900,
    "property_type": "Apartment",
    "available_date": "2026-05-01",
    "amenities": ["Parking", "Laundry"],
    "neighborhood": "Oakland",
    "description": "Nice apartment",
    "images": ["https://example.com/img.jpg"],
}


def _mock_anon():
    """Override get_optional_user to return None (anonymous)."""
    return None


def _mock_free_user():
    """Override get_optional_user to return a free-tier user."""
    return UserContext(user_id="user-free-123", email="free@test.com")


def _mock_pro_user():
    """Override get_optional_user to return a pro-tier user."""
    return UserContext(user_id="user-pro-456", email="pro@test.com")


class TestAnonymousSearch:
    """Anonymous users (no auth) get filtered results without AI scoring."""

    def test_anonymous_gets_results_without_scores(self):
        app.dependency_overrides[get_optional_user] = _mock_anon
        try:
            with patch(
                "app.main.apartment_service.search_apartments",
                new_callable=AsyncMock,
                return_value=[SAMPLE_APARTMENT],
            ):
                response = client.post("/api/search", json=SEARCH_BODY)

            assert response.status_code == 200
            data = response.json()
            assert data["tier"] == "anonymous"
            assert data["searches_remaining"] is None
            assert data["total_results"] == 1
            assert len(data["apartments"]) == 1

            apt = data["apartments"][0]
            assert apt["match_score"] is None
            assert apt["reasoning"] is None
            assert apt["highlights"] == []
            assert apt["id"] == "apt-001"
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_anonymous_does_not_call_claude(self):
        """Verify Claude AI scoring is NOT invoked for anonymous users."""
        app.dependency_overrides[get_optional_user] = _mock_anon
        try:
            with (
                patch(
                    "app.main.apartment_service.search_apartments",
                    new_callable=AsyncMock,
                    return_value=[SAMPLE_APARTMENT],
                ),
                patch(
                    "app.main.apartment_service.get_top_apartments",
                    new_callable=AsyncMock,
                ) as mock_top,
            ):
                response = client.post("/api/search", json=SEARCH_BODY)

            assert response.status_code == 200
            mock_top.assert_not_called()
        finally:
            app.dependency_overrides.pop(get_optional_user, None)


class TestFreeUserSearch:
    """Free users get filtered results without AI scoring, with daily limit."""

    def test_free_user_within_limit_gets_results(self):
        app.dependency_overrides[get_optional_user] = _mock_free_user
        try:
            with (
                patch(
                    "app.main.TierService.get_user_tier",
                    new_callable=AsyncMock,
                    return_value="free",
                ),
                patch(
                    "app.main.TierService.check_search_limit",
                    new_callable=AsyncMock,
                    return_value=(True, 2),
                ),
                patch(
                    "app.main.TierService.increment_search_count",
                    new_callable=AsyncMock,
                ) as mock_incr,
                patch(
                    "app.main.apartment_service.search_apartments",
                    new_callable=AsyncMock,
                    return_value=[SAMPLE_APARTMENT],
                ),
            ):
                response = client.post("/api/search", json=SEARCH_BODY)

            assert response.status_code == 200
            data = response.json()
            assert data["tier"] == "free"
            # Started with 2 remaining, after this search: 1
            assert data["searches_remaining"] == 1
            assert data["apartments"][0]["match_score"] is None
            mock_incr.assert_awaited_once_with("user-free-123")
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_free_user_at_limit_gets_429(self):
        """Free user who has used all daily searches gets 429."""
        app.dependency_overrides[get_optional_user] = _mock_free_user
        try:
            with (
                patch(
                    "app.main.TierService.get_user_tier",
                    new_callable=AsyncMock,
                    return_value="free",
                ),
                patch(
                    "app.main.TierService.check_search_limit",
                    new_callable=AsyncMock,
                    return_value=(False, 0),
                ),
            ):
                response = client.post("/api/search", json=SEARCH_BODY)

            assert response.status_code == 429
            assert "Daily search limit" in response.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_free_user_does_not_call_claude(self):
        """Verify Claude AI scoring is NOT invoked for free users."""
        app.dependency_overrides[get_optional_user] = _mock_free_user
        try:
            with (
                patch(
                    "app.main.TierService.get_user_tier",
                    new_callable=AsyncMock,
                    return_value="free",
                ),
                patch(
                    "app.main.TierService.check_search_limit",
                    new_callable=AsyncMock,
                    return_value=(True, 3),
                ),
                patch(
                    "app.main.TierService.increment_search_count",
                    new_callable=AsyncMock,
                ),
                patch(
                    "app.main.apartment_service.search_apartments",
                    new_callable=AsyncMock,
                    return_value=[],
                ),
                patch(
                    "app.main.apartment_service.get_top_apartments",
                    new_callable=AsyncMock,
                ) as mock_top,
            ):
                response = client.post("/api/search", json=SEARCH_BODY)

            assert response.status_code == 200
            mock_top.assert_not_called()
        finally:
            app.dependency_overrides.pop(get_optional_user, None)


class TestProUserSearch:
    """Pro users get full Claude AI-scored results."""

    def test_pro_user_gets_scored_results(self):
        scored_apartment = {
            **SAMPLE_APARTMENT,
            "match_score": 85,
            "reasoning": "Great match for your needs.",
            "highlights": ["Under budget", "Good location"],
        }
        app.dependency_overrides[get_optional_user] = _mock_pro_user
        try:
            with (
                patch(
                    "app.main.TierService.get_user_tier",
                    new_callable=AsyncMock,
                    return_value="pro",
                ),
                patch(
                    "app.main.apartment_service.get_top_apartments",
                    new_callable=AsyncMock,
                    return_value=([scored_apartment], 1),
                ),
            ):
                response = client.post("/api/search", json=SEARCH_BODY)

            assert response.status_code == 200
            data = response.json()
            assert data["tier"] == "pro"
            assert data["searches_remaining"] is None
            assert data["total_results"] == 1
            assert len(data["apartments"]) == 1

            apt = data["apartments"][0]
            assert apt["match_score"] == 85
            assert apt["reasoning"] == "Great match for your needs."
            assert "Under budget" in apt["highlights"]
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_pro_user_has_no_search_limit(self):
        """Pro users should NOT have check_search_limit called."""
        app.dependency_overrides[get_optional_user] = _mock_pro_user
        try:
            with (
                patch(
                    "app.main.TierService.get_user_tier",
                    new_callable=AsyncMock,
                    return_value="pro",
                ),
                patch(
                    "app.main.TierService.check_search_limit",
                    new_callable=AsyncMock,
                ) as mock_limit,
                patch(
                    "app.main.TierService.increment_search_count",
                    new_callable=AsyncMock,
                ) as mock_incr,
                patch(
                    "app.main.apartment_service.get_top_apartments",
                    new_callable=AsyncMock,
                    return_value=([], 0),
                ),
            ):
                response = client.post("/api/search", json=SEARCH_BODY)

            assert response.status_code == 200
            mock_limit.assert_not_called()
            mock_incr.assert_not_called()
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_pro_user_calls_claude(self):
        """Pro users should use get_top_apartments (Claude AI scoring)."""
        app.dependency_overrides[get_optional_user] = _mock_pro_user
        try:
            with (
                patch(
                    "app.main.TierService.get_user_tier",
                    new_callable=AsyncMock,
                    return_value="pro",
                ),
                patch(
                    "app.main.apartment_service.get_top_apartments",
                    new_callable=AsyncMock,
                    return_value=([], 0),
                ) as mock_top,
                patch(
                    "app.main.apartment_service.search_apartments",
                    new_callable=AsyncMock,
                ) as mock_search,
            ):
                response = client.post("/api/search", json=SEARCH_BODY)

            assert response.status_code == 200
            mock_top.assert_called_once()
            mock_search.assert_not_called()
        finally:
            app.dependency_overrides.pop(get_optional_user, None)


class TestSearchResponseShape:
    """Verify the response always includes tier and searches_remaining fields."""

    def test_response_includes_tier_and_remaining(self):
        app.dependency_overrides[get_optional_user] = _mock_anon
        try:
            with patch(
                "app.main.apartment_service.search_apartments",
                new_callable=AsyncMock,
                return_value=[],
            ):
                response = client.post("/api/search", json=SEARCH_BODY)

            data = response.json()
            assert "tier" in data
            assert "searches_remaining" in data
            assert "apartments" in data
            assert "total_results" in data
        finally:
            app.dependency_overrides.pop(get_optional_user, None)
