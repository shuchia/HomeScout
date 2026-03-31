"""Tests for proximity search integration."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth import get_optional_user, UserContext

client = TestClient(app)

SEARCH_BODY_WITH_PROXIMITY = {
    "city": "Philadelphia, PA",
    "budget": 2000,
    "bedrooms": 1,
    "bathrooms": 1,
    "property_type": "Apartment",
    "move_in_date": "2026-06-01",
    "near_lat": 39.9483,
    "near_lng": -75.1932,
    "near_label": "Children's Hospital of Philadelphia",
}

SAMPLE_APT_CLOSE = {
    "id": "apt-close",
    "address": "100 Close St, Philadelphia, PA",
    "rent": 1800,
    "bedrooms": 1,
    "bathrooms": 1,
    "sqft": 700,
    "property_type": "Apartment",
    "available_date": "2026-05-01",
    "amenities": ["Parking"],
    "neighborhood": "University City",
    "description": "Close apartment",
    "images": ["https://example.com/img.jpg"],
    "latitude": 39.9490,
    "longitude": -75.1940,
}

SAMPLE_APT_FAR = {
    "id": "apt-far",
    "address": "999 Far Ave, Philadelphia, PA",
    "rent": 1500,
    "bedrooms": 1,
    "bathrooms": 1,
    "sqft": 600,
    "property_type": "Apartment",
    "available_date": "2026-05-01",
    "amenities": [],
    "neighborhood": "Northeast",
    "description": "Far apartment",
    "images": ["https://example.com/img2.jpg"],
    "latitude": 40.05,
    "longitude": -75.05,
}


def _mock_free_user():
    return UserContext(user_id="user-free-123", email="free@test.com")


def _mock_pro_user():
    return UserContext(user_id="user-pro-456", email="pro@test.com")


class TestProximitySearchSchema:
    @patch("app.main.apartment_service")
    @patch("app.main.TierService")
    def test_search_accepts_proximity_fields(self, mock_tier, mock_svc):
        app.dependency_overrides[get_optional_user] = _mock_free_user
        mock_tier.get_user_tier = AsyncMock(return_value="free")
        mock_tier.check_search_limit = AsyncMock(return_value=(True, 2))
        mock_tier.increment_search_count = AsyncMock()
        mock_svc.search_apartments = AsyncMock(return_value=[SAMPLE_APT_CLOSE])

        response = client.post("/api/search", json=SEARCH_BODY_WITH_PROXIMITY)
        assert response.status_code == 200
        assert len(response.json()["apartments"]) >= 1
        app.dependency_overrides.clear()

    @patch("app.main.apartment_service")
    @patch("app.main.TierService")
    def test_search_returns_distance_miles(self, mock_tier, mock_svc):
        app.dependency_overrides[get_optional_user] = _mock_free_user
        mock_tier.get_user_tier = AsyncMock(return_value="free")
        mock_tier.check_search_limit = AsyncMock(return_value=(True, 2))
        mock_tier.increment_search_count = AsyncMock()
        mock_svc.search_apartments = AsyncMock(return_value=[SAMPLE_APT_CLOSE, SAMPLE_APT_FAR])

        response = client.post("/api/search", json=SEARCH_BODY_WITH_PROXIMITY)
        assert response.status_code == 200
        apts = response.json()["apartments"]
        for apt in apts:
            assert "distance_miles" in apt
        app.dependency_overrides.clear()

    @patch("app.main.apartment_service")
    @patch("app.main.TierService")
    def test_search_sorted_by_distance(self, mock_tier, mock_svc):
        app.dependency_overrides[get_optional_user] = _mock_free_user
        mock_tier.get_user_tier = AsyncMock(return_value="free")
        mock_tier.check_search_limit = AsyncMock(return_value=(True, 2))
        mock_tier.increment_search_count = AsyncMock()
        mock_svc.search_apartments = AsyncMock(return_value=[SAMPLE_APT_FAR, SAMPLE_APT_CLOSE])

        response = client.post("/api/search", json=SEARCH_BODY_WITH_PROXIMITY)
        apts = response.json()["apartments"]
        assert apts[0]["id"] == "apt-close"
        assert apts[1]["id"] == "apt-far"
        app.dependency_overrides.clear()

    @patch("app.main.apartment_service")
    @patch("app.main.TierService")
    def test_max_distance_ignored_for_free(self, mock_tier, mock_svc):
        app.dependency_overrides[get_optional_user] = _mock_free_user
        mock_tier.get_user_tier = AsyncMock(return_value="free")
        mock_tier.check_search_limit = AsyncMock(return_value=(True, 2))
        mock_tier.increment_search_count = AsyncMock()
        mock_svc.search_apartments = AsyncMock(return_value=[SAMPLE_APT_CLOSE, SAMPLE_APT_FAR])

        body = {**SEARCH_BODY_WITH_PROXIMITY, "max_distance_miles": 1.0}
        response = client.post("/api/search", json=body)
        apts = response.json()["apartments"]
        assert len(apts) == 2
        app.dependency_overrides.clear()

    @patch("app.main.apartment_service")
    @patch("app.main.TierService")
    def test_max_distance_filters_for_pro(self, mock_tier, mock_svc):
        app.dependency_overrides[get_optional_user] = _mock_pro_user
        mock_tier.get_user_tier = AsyncMock(return_value="pro")
        mock_svc.get_top_apartments = AsyncMock(return_value=([SAMPLE_APT_CLOSE, SAMPLE_APT_FAR], 2))

        body = {**SEARCH_BODY_WITH_PROXIMITY, "max_distance_miles": 1.0}
        response = client.post("/api/search", json=body)
        apts = response.json()["apartments"]
        assert len(apts) == 1
        assert apts[0]["id"] == "apt-close"
        app.dependency_overrides.clear()
