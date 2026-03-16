"""Tests for tour pipeline CRUD endpoints."""
from unittest.mock import patch, MagicMock, ANY
from fastapi.testclient import TestClient

from app.auth import get_current_user, UserContext
from app.main import app

client = TestClient(app)


def _mock_user():
    """Return a UserContext for testing."""
    return UserContext(user_id="user-123", email="test@test.com")


SAMPLE_TOUR = {
    "id": "tour-001",
    "user_id": "user-123",
    "apartment_id": "apt-001",
    "stage": "interested",
    "inquiry_email_draft": None,
    "outreach_sent_at": None,
    "scheduled_date": None,
    "scheduled_time": None,
    "tour_rating": None,
    "toured_at": None,
    "decision": None,
    "decision_reason": None,
    "created_at": "2026-03-15T00:00:00+00:00",
    "updated_at": "2026-03-15T00:00:00+00:00",
}

SAMPLE_NOTE = {
    "id": "note-001",
    "content": "Nice kitchen",
    "source": "text",
    "transcription_status": None,
    "created_at": "2026-03-15T01:00:00+00:00",
}

SAMPLE_PHOTO = {
    "id": "photo-001",
    "thumbnail_url": "https://example.com/thumb.jpg",
    "caption": "Living room",
    "created_at": "2026-03-15T01:00:00+00:00",
}

SAMPLE_TAG = {
    "id": "tag-001",
    "tag": "bright",
    "sentiment": "positive",
}


class TestCreateTour:
    def test_requires_auth(self):
        """POST /api/tours without auth returns 401."""
        response = client.post("/api/tours", json={"apartment_id": "apt-001"})
        assert response.status_code == 401

    def test_creates_tour(self):
        """POST /api/tours creates a new tour entry."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()
            # Duplicate check returns empty
            mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )
            # Insert returns the new row
            mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock(
                data=[SAMPLE_TOUR]
            )

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.post(
                    "/api/tours",
                    json={"apartment_id": "apt-001"},
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 201
            data = response.json()
            assert data["tour"]["apartment_id"] == "apt-001"
            assert data["tour"]["stage"] == "interested"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_duplicate_apartment_returns_409(self):
        """POST /api/tours with existing apartment returns 409."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()
            # Duplicate check returns existing entry
            mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": "tour-001"}]
            )

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.post(
                    "/api/tours",
                    json={"apartment_id": "apt-001"},
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 409
            assert "already" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.pop(get_current_user, None)


class TestListTours:
    def test_requires_auth_and_returns_list(self):
        """GET /api/tours requires auth and returns grouped list."""
        # First verify auth is required
        response = client.get("/api/tours")
        assert response.status_code == 401

        # Then verify authenticated returns data
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()
            mock_sb.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                data=[SAMPLE_TOUR]
            )

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.get(
                    "/api/tours",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            data = response.json()
            assert len(data["tours"]) == 1
            assert data["tours"][0]["id"] == "tour-001"
        finally:
            app.dependency_overrides.pop(get_current_user, None)


class TestGetTour:
    def test_returns_tour_with_related_data(self):
        """GET /api/tours/{id} returns tour with notes, photos, tags."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()

            # We need to handle multiple table() calls returning different chains.
            # Use side_effect to differentiate by table name.
            def table_router(table_name):
                mock_table = MagicMock()
                if table_name == "tour_pipeline":
                    # .select().eq(id).eq(user_id).execute()
                    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[SAMPLE_TOUR]
                    )
                elif table_name == "tour_notes":
                    # .select().eq(tour_pipeline_id).order().execute()
                    mock_table.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                        data=[SAMPLE_NOTE]
                    )
                elif table_name == "tour_photos":
                    # .select().eq(tour_pipeline_id).order().execute()
                    mock_table.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                        data=[SAMPLE_PHOTO]
                    )
                elif table_name == "tour_tags":
                    # .select().eq(tour_pipeline_id).execute()
                    mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[SAMPLE_TAG]
                    )
                return mock_table

            mock_sb.table.side_effect = table_router

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.get(
                    "/api/tours/tour-001",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            tour = response.json()["tour"]
            assert tour["id"] == "tour-001"
            assert len(tour["notes"]) == 1
            assert tour["notes"][0]["content"] == "Nice kitchen"
            assert len(tour["photos"]) == 1
            assert tour["photos"][0]["caption"] == "Living room"
            assert len(tour["tags"]) == 1
            assert tour["tags"][0]["tag"] == "bright"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_not_found_returns_404(self):
        """GET /api/tours/{id} for non-existent tour returns 404."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()
            mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.get(
                    "/api/tours/nonexistent",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_current_user, None)


class TestUpdateTour:
    def test_advances_stage(self):
        """PATCH /api/tours/{id} advances stage and returns updated tour."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            updated_tour = {**SAMPLE_TOUR, "stage": "scheduled"}
            mock_sb = MagicMock()
            mock_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[updated_tour]
            )

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.patch(
                    "/api/tours/tour-001",
                    json={"stage": "scheduled"},
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            assert response.json()["tour"]["stage"] == "scheduled"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_toured_stage_auto_sets_toured_at(self):
        """PATCH to 'toured' stage auto-sets toured_at timestamp."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            updated_tour = {
                **SAMPLE_TOUR,
                "stage": "toured",
                "toured_at": "2026-03-15T12:00:00+00:00",
            }
            mock_sb = MagicMock()
            mock_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[updated_tour]
            )

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.patch(
                    "/api/tours/tour-001",
                    json={"stage": "toured"},
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            # Verify the update call included toured_at
            call_args = mock_sb.table.return_value.update.call_args
            update_payload = call_args[0][0]
            assert "toured_at" in update_payload
            assert "stage" in update_payload
            assert update_payload["stage"] == "toured"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_outreach_sent_auto_sets_outreach_sent_at(self):
        """PATCH to 'outreach_sent' stage auto-sets outreach_sent_at."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            updated_tour = {
                **SAMPLE_TOUR,
                "stage": "outreach_sent",
                "outreach_sent_at": "2026-03-15T12:00:00+00:00",
            }
            mock_sb = MagicMock()
            mock_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[updated_tour]
            )

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.patch(
                    "/api/tours/tour-001",
                    json={"stage": "outreach_sent"},
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            call_args = mock_sb.table.return_value.update.call_args
            update_payload = call_args[0][0]
            assert "outreach_sent_at" in update_payload
            assert update_payload["stage"] == "outreach_sent"
        finally:
            app.dependency_overrides.pop(get_current_user, None)


    def test_invalid_stage_returns_422(self):
        """PATCH with invalid stage returns 422."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            response = client.patch(
                "/api/tours/tour-001",
                json={"stage": "invalid_stage"},
                headers={"Authorization": "Bearer fake-token"},
            )
            assert response.status_code == 422
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_empty_update_returns_400(self):
        """PATCH with no fields returns 400."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            with patch("app.routers.tours.supabase_admin", MagicMock()):
                response = client.patch(
                    "/api/tours/tour-001",
                    json={},
                    headers={"Authorization": "Bearer fake-token"},
                )
            assert response.status_code == 400
            assert "No fields" in response.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_current_user, None)


class TestDeleteTour:
    def test_removes_tour(self):
        """DELETE /api/tours/{id} removes tour and returns status."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()
            mock_sb.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[SAMPLE_TOUR]
            )

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.delete(
                    "/api/tours/tour-001",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            assert response.json()["status"] == "deleted"
        finally:
            app.dependency_overrides.pop(get_current_user, None)
