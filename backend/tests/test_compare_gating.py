"""Tests for compare endpoint tier gating."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth import get_optional_user, UserContext

client = TestClient(app)

SAMPLE_APARTMENTS = [
    {
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
        "images": ["https://example.com/img1.jpg"],
    },
    {
        "id": "apt-002",
        "address": "456 Oak Ave, Pittsburgh, PA 15213",
        "rent": 2100,
        "bedrooms": 2,
        "bathrooms": 2,
        "sqft": 1100,
        "property_type": "Apartment",
        "available_date": "2026-06-01",
        "amenities": ["Parking", "Gym", "Pool"],
        "neighborhood": "Shadyside",
        "description": "Spacious apartment",
        "images": ["https://example.com/img2.jpg"],
    },
]

COMPARE_BODY = {
    "apartment_ids": ["apt-001", "apt-002"],
    "preferences": "Looking for good value",
}

MOCK_ANALYSIS = {
    "winner": {"apartment_id": "apt-001", "reason": "Best overall value"},
    "categories": ["Value", "Space & Layout", "Amenities"],
    "apartment_scores": [
        {
            "apartment_id": "apt-001",
            "overall_score": 85,
            "reasoning": "Great value for money",
            "highlights": ["Lower rent", "Good amenities"],
            "category_scores": {
                "Value": {"score": 90, "note": "Best price"},
                "Space & Layout": {"score": 80, "note": "Decent space"},
                "Amenities": {"score": 75, "note": "Standard amenities"},
            },
        },
        {
            "apartment_id": "apt-002",
            "overall_score": 78,
            "reasoning": "More space but pricier",
            "highlights": ["Larger unit", "More amenities"],
            "category_scores": {
                "Value": {"score": 70, "note": "Higher rent"},
                "Space & Layout": {"score": 90, "note": "Spacious"},
                "Amenities": {"score": 85, "note": "Pool and gym"},
            },
        },
    ],
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


def _make_json_data():
    """Return sample apartment data for the JSON data source mock."""
    return list(SAMPLE_APARTMENTS)


class TestAnonymousCompare:
    """Anonymous users get apartment data for side-by-side but no Claude analysis."""

    def test_anonymous_gets_apartments_without_analysis(self):
        app.dependency_overrides[get_optional_user] = _mock_anon
        try:
            with patch(
                "app.routers.apartments.is_database_enabled",
                return_value=False,
            ), patch(
                "app.routers.apartments._get_apartments_data",
                return_value=_make_json_data(),
            ):
                response = client.post("/api/apartments/compare", json=COMPARE_BODY)

            assert response.status_code == 200
            data = response.json()
            assert data["tier"] == "anonymous"
            assert data["comparison_analysis"] is None
            assert len(data["apartments"]) == 2
            assert data["apartments"][0]["id"] == "apt-001"
            assert data["apartments"][1]["id"] == "apt-002"
            assert "comparison_fields" in data
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_anonymous_does_not_call_claude(self):
        """Verify Claude analysis is NOT invoked for anonymous users."""
        app.dependency_overrides[get_optional_user] = _mock_anon
        try:
            with patch(
                "app.routers.apartments.is_database_enabled",
                return_value=False,
            ), patch(
                "app.routers.apartments._get_apartments_data",
                return_value=_make_json_data(),
            ), patch(
                "app.routers.apartments.asyncio.to_thread",
                new_callable=AsyncMock,
            ) as mock_claude:
                response = client.post("/api/apartments/compare", json=COMPARE_BODY)

            assert response.status_code == 200
            mock_claude.assert_not_called()
        finally:
            app.dependency_overrides.pop(get_optional_user, None)


class TestFreeUserCompare:
    """Free users get apartment data for side-by-side but no Claude analysis."""

    def test_free_user_gets_apartments_without_analysis(self):
        app.dependency_overrides[get_optional_user] = _mock_free_user
        try:
            with patch(
                "app.routers.apartments.TierService.get_user_tier",
                new_callable=AsyncMock,
                return_value="free",
            ), patch(
                "app.routers.apartments.is_database_enabled",
                return_value=False,
            ), patch(
                "app.routers.apartments._get_apartments_data",
                return_value=_make_json_data(),
            ):
                response = client.post("/api/apartments/compare", json=COMPARE_BODY)

            assert response.status_code == 200
            data = response.json()
            assert data["tier"] == "free"
            assert data["comparison_analysis"] is None
            assert len(data["apartments"]) == 2
            assert data["apartments"][0]["id"] == "apt-001"
            assert data["apartments"][1]["id"] == "apt-002"
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_free_user_does_not_call_claude(self):
        """Verify Claude analysis is NOT invoked for free users."""
        app.dependency_overrides[get_optional_user] = _mock_free_user
        try:
            with patch(
                "app.routers.apartments.TierService.get_user_tier",
                new_callable=AsyncMock,
                return_value="free",
            ), patch(
                "app.routers.apartments.is_database_enabled",
                return_value=False,
            ), patch(
                "app.routers.apartments._get_apartments_data",
                return_value=_make_json_data(),
            ), patch(
                "app.routers.apartments.asyncio.to_thread",
                new_callable=AsyncMock,
            ) as mock_claude:
                response = client.post("/api/apartments/compare", json=COMPARE_BODY)

            assert response.status_code == 200
            mock_claude.assert_not_called()
        finally:
            app.dependency_overrides.pop(get_optional_user, None)


class TestProUserCompare:
    """Pro users get full Claude comparison analysis."""

    def test_pro_user_gets_full_analysis(self):
        app.dependency_overrides[get_optional_user] = _mock_pro_user
        try:
            with patch(
                "app.routers.apartments.TierService.get_user_tier",
                new_callable=AsyncMock,
                return_value="pro",
            ), patch(
                "app.routers.apartments.is_database_enabled",
                return_value=False,
            ), patch(
                "app.routers.apartments._get_apartments_data",
                return_value=_make_json_data(),
            ), patch(
                "app.routers.apartments.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value=MOCK_ANALYSIS,
            ):
                response = client.post("/api/apartments/compare", json=COMPARE_BODY)

            assert response.status_code == 200
            data = response.json()
            assert data["tier"] == "pro"
            assert data["comparison_analysis"] is not None

            analysis = data["comparison_analysis"]
            assert analysis["winner"]["apartment_id"] == "apt-001"
            assert analysis["winner"]["reason"] == "Best overall value"
            assert len(analysis["categories"]) == 3
            assert len(analysis["apartment_scores"]) == 2
            assert analysis["apartment_scores"][0]["overall_score"] == 85
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_pro_user_calls_claude(self):
        """Verify Claude analysis IS invoked for pro users with 2+ apartments."""
        app.dependency_overrides[get_optional_user] = _mock_pro_user
        try:
            with patch(
                "app.routers.apartments.TierService.get_user_tier",
                new_callable=AsyncMock,
                return_value="pro",
            ), patch(
                "app.routers.apartments.is_database_enabled",
                return_value=False,
            ), patch(
                "app.routers.apartments._get_apartments_data",
                return_value=_make_json_data(),
            ), patch(
                "app.routers.apartments.asyncio.to_thread",
                new_callable=AsyncMock,
                return_value=MOCK_ANALYSIS,
            ) as mock_claude:
                response = client.post("/api/apartments/compare", json=COMPARE_BODY)

            assert response.status_code == 200
            mock_claude.assert_called_once()
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_pro_user_with_single_apartment_no_analysis(self):
        """Pro user with only 1 apartment should not trigger Claude analysis."""
        app.dependency_overrides[get_optional_user] = _mock_pro_user
        try:
            with patch(
                "app.routers.apartments.TierService.get_user_tier",
                new_callable=AsyncMock,
                return_value="pro",
            ), patch(
                "app.routers.apartments.is_database_enabled",
                return_value=False,
            ), patch(
                "app.routers.apartments._get_apartments_data",
                return_value=_make_json_data(),
            ):
                response = client.post(
                    "/api/apartments/compare",
                    json={"apartment_ids": ["apt-001"]},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["tier"] == "pro"
            assert data["comparison_analysis"] is None
            assert len(data["apartments"]) == 1
        finally:
            app.dependency_overrides.pop(get_optional_user, None)


class TestCompareResponseShape:
    """Verify the response always includes the tier field."""

    def test_response_includes_tier_field(self):
        app.dependency_overrides[get_optional_user] = _mock_anon
        try:
            with patch(
                "app.routers.apartments.is_database_enabled",
                return_value=False,
            ), patch(
                "app.routers.apartments._get_apartments_data",
                return_value=_make_json_data(),
            ):
                response = client.post("/api/apartments/compare", json=COMPARE_BODY)

            data = response.json()
            assert "tier" in data
            assert "apartments" in data
            assert "comparison_fields" in data
            assert "comparison_analysis" in data
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

    def test_empty_apartment_ids_returns_tier(self):
        app.dependency_overrides[get_optional_user] = _mock_free_user
        try:
            response = client.post(
                "/api/apartments/compare",
                json={"apartment_ids": []},
            )

            assert response.status_code == 200
            data = response.json()
            assert "tier" in data
            assert data["apartments"] == []
            assert data["comparison_analysis"] is None
        finally:
            app.dependency_overrides.pop(get_optional_user, None)
