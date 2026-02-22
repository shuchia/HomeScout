"""Tests for saved search CRUD endpoints."""
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.auth import get_current_user, UserContext
from app.main import app

client = TestClient(app)


def _mock_user():
    """Return a UserContext for testing."""
    return UserContext(user_id="user-123", email="test@test.com")


SAMPLE_SAVED_SEARCH = {
    "id": "ss-001",
    "user_id": "user-123",
    "name": "Pittsburgh 2BR",
    "city": "Pittsburgh",
    "budget": 2000,
    "bedrooms": 2,
    "bathrooms": 1,
    "property_type": "Apartment",
    "preferences": "near downtown",
    "created_at": "2026-02-20T00:00:00+00:00",
}

CREATE_BODY = {
    "name": "Pittsburgh 2BR",
    "city": "Pittsburgh",
    "budget": 2000,
    "bedrooms": 2,
    "bathrooms": 1,
    "property_type": "Apartment",
    "preferences": "near downtown",
}


class TestListSavedSearches:
    def test_requires_auth(self):
        """No auth token returns 401."""
        response = client.get("/api/saved-searches")
        assert response.status_code == 401

    def test_returns_data(self):
        """Authenticated user gets their saved searches."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()
            mock_sb.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                data=[SAMPLE_SAVED_SEARCH]
            )

            with patch("app.routers.saved_searches.supabase_admin", mock_sb):
                response = client.get(
                    "/api/saved-searches",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            data = response.json()
            assert len(data["saved_searches"]) == 1
            assert data["saved_searches"][0]["name"] == "Pittsburgh 2BR"
        finally:
            app.dependency_overrides.pop(get_current_user, None)


class TestCreateSavedSearch:
    def test_requires_auth(self):
        """No auth token returns 401."""
        response = client.post("/api/saved-searches", json=CREATE_BODY)
        assert response.status_code == 401

    def test_free_tier_returns_403(self):
        """Free tier user cannot create saved searches."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            with patch(
                "app.routers.saved_searches.TierService.get_user_tier",
                new_callable=AsyncMock,
                return_value="free",
            ):
                response = client.post(
                    "/api/saved-searches",
                    json=CREATE_BODY,
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 403
            assert "Pro" in response.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_pro_tier_creates_search(self):
        """Pro tier user can create a saved search."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()
            mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock(
                data=[SAMPLE_SAVED_SEARCH]
            )

            with (
                patch(
                    "app.routers.saved_searches.TierService.get_user_tier",
                    new_callable=AsyncMock,
                    return_value="pro",
                ),
                patch("app.routers.saved_searches.supabase_admin", mock_sb),
            ):
                response = client.post(
                    "/api/saved-searches",
                    json=CREATE_BODY,
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 201
            data = response.json()
            assert data["saved_search"]["name"] == "Pittsburgh 2BR"
        finally:
            app.dependency_overrides.pop(get_current_user, None)


class TestDeleteSavedSearch:
    def test_requires_auth(self):
        """No auth token returns 401."""
        response = client.delete("/api/saved-searches/ss-001")
        assert response.status_code == 401

    def test_deletes_own_search(self):
        """Authenticated user can delete their own saved search."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()
            mock_sb.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[SAMPLE_SAVED_SEARCH]
            )

            with patch("app.routers.saved_searches.supabase_admin", mock_sb):
                response = client.delete(
                    "/api/saved-searches/ss-001",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            assert response.json()["status"] == "deleted"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_not_found_returns_404(self):
        """Deleting a non-existent saved search returns 404."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()
            mock_sb.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )

            with patch("app.routers.saved_searches.supabase_admin", mock_sb):
                response = client.delete(
                    "/api/saved-searches/ss-999",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_current_user, None)
