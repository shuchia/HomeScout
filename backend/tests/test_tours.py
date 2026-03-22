"""Tests for tour pipeline CRUD endpoints."""
from io import BytesIO
from unittest.mock import patch, MagicMock, ANY, AsyncMock
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


# ── Notes sub-resource tests ─────────────────────────────────────────

SAMPLE_NOTE_CREATED = {
    "id": "note-002",
    "tour_pipeline_id": "tour-001",
    "content": "Great natural light",
    "source": "typed",
    "transcription_status": "complete",
    "created_at": "2026-03-15T02:00:00+00:00",
}


class TestNotes:
    def test_create_note_requires_auth(self):
        """POST /api/tours/{id}/notes without auth returns 401."""
        response = client.post(
            "/api/tours/tour-001/notes",
            json={"content": "Nice place"},
        )
        assert response.status_code == 401

    def test_create_note(self):
        """POST /api/tours/{id}/notes creates a typed note (201)."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()

            def table_router(table_name):
                mock_table = MagicMock()
                if table_name == "tour_pipeline":
                    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[{"id": "tour-001"}]
                    )
                elif table_name == "tour_notes":
                    mock_table.insert.return_value.execute.return_value = MagicMock(
                        data=[SAMPLE_NOTE_CREATED]
                    )
                return mock_table

            mock_sb.table.side_effect = table_router

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.post(
                    "/api/tours/tour-001/notes",
                    json={"content": "Great natural light"},
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 201
            note = response.json()["note"]
            assert note["content"] == "Great natural light"
            assert note["source"] == "typed"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_list_notes(self):
        """GET /api/tours/{id}/notes lists notes chronologically."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()

            def table_router(table_name):
                mock_table = MagicMock()
                if table_name == "tour_pipeline":
                    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[{"id": "tour-001"}]
                    )
                elif table_name == "tour_notes":
                    mock_table.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                        data=[SAMPLE_NOTE_CREATED]
                    )
                return mock_table

            mock_sb.table.side_effect = table_router

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.get(
                    "/api/tours/tour-001/notes",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            assert len(response.json()["notes"]) == 1
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_delete_note(self):
        """DELETE /api/tours/{id}/notes/{note_id} removes note."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()

            def table_router(table_name):
                mock_table = MagicMock()
                if table_name == "tour_pipeline":
                    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[{"id": "tour-001"}]
                    )
                elif table_name == "tour_notes":
                    mock_table.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[SAMPLE_NOTE_CREATED]
                    )
                return mock_table

            mock_sb.table.side_effect = table_router

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.delete(
                    "/api/tours/tour-001/notes/note-002",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            assert response.json()["status"] == "deleted"
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ── Photos sub-resource tests ────────────────────────────────────────

SAMPLE_PHOTO_CREATED = {
    "id": "photo-002",
    "tour_pipeline_id": "tour-001",
    "user_id": "user-123",
    "s3_key": "tours/user-123/tour-001/abc.jpg",
    "thumbnail_s3_key": "tours/user-123/tour-001/thumbs/abc.jpg",
    "thumbnail_url": "https://s3.example.com/presigned-thumb",
    "caption": "Kitchen",
    "created_at": "2026-03-15T02:00:00+00:00",
}


def _make_test_jpeg() -> bytes:
    """Create a minimal valid JPEG for upload tests."""
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (10, 10), color="blue").save(buf, format="JPEG")
    return buf.getvalue()


class TestPhotos:
    def test_create_photo(self):
        """POST /api/tours/{id}/photos uploads file and creates photo entry (201)."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()

            def table_router(table_name):
                mock_table = MagicMock()
                if table_name == "tour_pipeline":
                    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[{"id": "tour-001"}]
                    )
                elif table_name == "tour_photos":
                    mock_table.insert.return_value.execute.return_value = MagicMock(
                        data=[SAMPLE_PHOTO_CREATED]
                    )
                return mock_table

            mock_sb.table.side_effect = table_router

            mock_upload_result = {
                "s3_key": "tours/user-123/tour-001/abc.jpg",
                "thumbnail_s3_key": "tours/user-123/tour-001/thumbs/abc.jpg",
            }

            with patch("app.routers.tours.supabase_admin", mock_sb), \
                 patch("app.routers.tours.PhotoService.upload_photo", return_value=mock_upload_result), \
                 patch("app.routers.tours.PhotoService.get_presigned_url", return_value="https://s3.example.com/presigned-thumb"):
                jpeg_data = _make_test_jpeg()
                response = client.post(
                    "/api/tours/tour-001/photos?caption=Kitchen",
                    files={"file": ("photo.jpg", BytesIO(jpeg_data), "image/jpeg")},
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 201
            photo = response.json()["photo"]
            assert photo["s3_key"] == "tours/user-123/tour-001/abc.jpg"
            assert photo["caption"] == "Kitchen"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_update_photo_caption(self):
        """PATCH /api/tours/{id}/photos/{photo_id} updates caption."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()
            updated_photo = {**SAMPLE_PHOTO_CREATED, "caption": "Updated kitchen"}

            def table_router(table_name):
                mock_table = MagicMock()
                if table_name == "tour_pipeline":
                    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[{"id": "tour-001"}]
                    )
                elif table_name == "tour_photos":
                    mock_table.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[updated_photo]
                    )
                return mock_table

            mock_sb.table.side_effect = table_router

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.patch(
                    "/api/tours/tour-001/photos/photo-002",
                    json={"caption": "Updated kitchen"},
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            assert response.json()["photo"]["caption"] == "Updated kitchen"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_delete_photo(self):
        """DELETE /api/tours/{id}/photos/{photo_id} removes photo and deletes from S3."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()

            def table_router(table_name):
                mock_table = MagicMock()
                if table_name == "tour_pipeline":
                    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[{"id": "tour-001"}]
                    )
                elif table_name == "tour_photos":
                    mock_table.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[SAMPLE_PHOTO_CREATED]
                    )
                return mock_table

            mock_sb.table.side_effect = table_router

            mock_delete = MagicMock()

            with patch("app.routers.tours.supabase_admin", mock_sb), \
                 patch("app.routers.tours.PhotoService.delete_photo", mock_delete):
                response = client.delete(
                    "/api/tours/tour-001/photos/photo-002",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            assert response.json()["status"] == "deleted"
            # Verify S3 deletion was called
            mock_delete.assert_called_once_with(
                s3_key="tours/user-123/tour-001/abc.jpg",
                thumbnail_s3_key="tours/user-123/tour-001/thumbs/abc.jpg",
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ── Tags sub-resource tests ──────────────────────────────────────────

SAMPLE_TAG_CREATED = {
    "id": "tag-002",
    "tour_pipeline_id": "tour-001",
    "tag": "Great light",
    "sentiment": "pro",
}


class TestTags:
    def test_create_tag(self):
        """POST /api/tours/{id}/tags creates tag (201)."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()

            def table_router(table_name):
                mock_table = MagicMock()
                if table_name == "tour_pipeline":
                    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[{"id": "tour-001"}]
                    )
                elif table_name == "tour_tags":
                    mock_table.insert.return_value.execute.return_value = MagicMock(
                        data=[SAMPLE_TAG_CREATED]
                    )
                return mock_table

            mock_sb.table.side_effect = table_router

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.post(
                    "/api/tours/tour-001/tags",
                    json={"tag": "Great light", "sentiment": "pro"},
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 201
            tag = response.json()["tag"]
            assert tag["tag"] == "Great light"
            assert tag["sentiment"] == "pro"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_create_tag_invalid_sentiment(self):
        """POST /api/tours/{id}/tags with invalid sentiment returns 422."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            response = client.post(
                "/api/tours/tour-001/tags",
                json={"tag": "Great light", "sentiment": "neutral"},
                headers={"Authorization": "Bearer fake-token"},
            )
            assert response.status_code == 422
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_delete_tag(self):
        """DELETE /api/tours/{id}/tags/{tag_id} removes tag."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()

            def table_router(table_name):
                mock_table = MagicMock()
                if table_name == "tour_pipeline":
                    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[{"id": "tour-001"}]
                    )
                elif table_name == "tour_tags":
                    mock_table.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[SAMPLE_TAG_CREATED]
                    )
                return mock_table

            mock_sb.table.side_effect = table_router

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.delete(
                    "/api/tours/tour-001/tags/tag-002",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            assert response.json()["status"] == "deleted"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_tag_suggestions(self):
        """GET /api/tours/tags/suggestions returns defaults + user tags."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()

            def table_router(table_name):
                mock_table = MagicMock()
                if table_name == "tour_pipeline":
                    # User has one tour
                    mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[{"id": "tour-001"}]
                    )
                elif table_name == "tour_tags":
                    # User has used "Great light" once
                    mock_table.select.return_value.in_.return_value.execute.return_value = MagicMock(
                        data=[{"tag": "Great light", "sentiment": "pro"}]
                    )
                return mock_table

            mock_sb.table.side_effect = table_router

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.get(
                    "/api/tours/tags/suggestions",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            suggestions = response.json()["suggestions"]
            # Should have user tag (count=1) + remaining defaults (count=0)
            tags_by_name = {s["tag"]: s for s in suggestions}
            assert tags_by_name["Great light"]["count"] == 1
            assert tags_by_name["Small kitchen"]["count"] == 0
            # Total: 1 user tag + 9 remaining defaults = 10
            assert len(suggestions) == 10
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ── Inquiry email tests ─────────────────────────────────────────────

SAMPLE_APARTMENT = {
    "id": "apt-001",
    "address": "123 Main St, Philadelphia, PA 19103",
    "rent": 2200,
    "bedrooms": 2,
    "bathrooms": 1,
    "sqft": 0,
    "property_type": "Apartment",
    "available_date": "2026-04-01",
    "amenities": ["Laundry", "Gym"],
    "neighborhood": "Center City",
    "description": "Bright 2BR apartment in Center City.",
    "images": [],
}


class TestInquiryEmail:
    def test_requires_auth(self):
        """POST /api/tours/{id}/inquiry-email without auth returns 401."""
        response = client.post("/api/tours/tour-001/inquiry-email")
        assert response.status_code == 401

    def test_generates_email(self):
        """POST /api/tours/{id}/inquiry-email calls Claude and returns email."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()

            def table_router(table_name):
                mock_table = MagicMock()
                if table_name == "tour_pipeline":
                    # For the select (fetch tour)
                    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[SAMPLE_TOUR]
                    )
                    # For the update (save draft)
                    mock_table.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[{**SAMPLE_TOUR, "inquiry_email_draft": "Subject: Hi\n\nBody"}]
                    )
                return mock_table

            mock_sb.table.side_effect = table_router

            mock_claude_result = {
                "subject": "Inquiry About 2BR at 123 Main St",
                "body": "Dear Property Manager,\n\nI am writing to inquire about the 2-bedroom apartment...",
            }

            with patch("app.routers.tours.supabase_admin", mock_sb), \
                 patch("app.database.is_database_enabled", return_value=False), \
                 patch("app.routers.apartments._get_apartments_data", return_value=[SAMPLE_APARTMENT]), \
                 patch("app.services.claude_service.ClaudeService.generate_inquiry_email", return_value=mock_claude_result):
                response = client.post(
                    "/api/tours/tour-001/inquiry-email",
                    json={"name": "Jane Doe", "budget": 2500},
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["subject"] == "Inquiry About 2BR at 123 Main St"
            assert "inquire" in data["body"].lower()
            assert "inquiry_email_draft" in data
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_tour_not_found_returns_404(self):
        """POST /api/tours/{id}/inquiry-email for non-existent tour returns 404."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()
            mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )

            with patch("app.routers.tours.supabase_admin", mock_sb):
                response = client.post(
                    "/api/tours/nonexistent/inquiry-email",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ── Day Plan tests ─────────────────────────────────────────────────

SAMPLE_TOUR_SCHEDULED = {
    **SAMPLE_TOUR,
    "stage": "scheduled",
    "scheduled_date": "2026-03-25",
    "scheduled_time": "10:00:00",
}

SAMPLE_TOUR_SCHEDULED_2 = {
    **SAMPLE_TOUR,
    "id": "tour-002",
    "apartment_id": "apt-002",
    "stage": "scheduled",
    "scheduled_date": "2026-03-25",
    "scheduled_time": "14:00:00",
}


class TestDayPlan:
    def test_requires_auth(self):
        """POST /api/tours/day-plan without auth returns 401."""
        response = client.post(
            "/api/tours/day-plan",
            json={"date": "2026-03-25", "tour_ids": ["tour-001", "tour-002"]},
        )
        assert response.status_code == 401

    def test_generates_day_plan(self):
        """POST /api/tours/day-plan calls Claude and returns plan."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()

            def table_router(table_name):
                mock_table = MagicMock()
                if table_name == "tour_pipeline":
                    # in_ query for fetching tours by IDs
                    mock_table.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
                        data=[SAMPLE_TOUR_SCHEDULED, SAMPLE_TOUR_SCHEDULED_2]
                    )
                return mock_table

            mock_sb.table.side_effect = table_router

            mock_claude_result = {
                "tours_ordered": [
                    {"apartment_id": "apt-001", "address": "123 Main St", "suggested_time": "10:00", "order": 1},
                    {"apartment_id": "apt-002", "address": "456 Oak Ave", "suggested_time": "11:30", "order": 2},
                ],
                "travel_notes": ["15 min drive between stops"],
                "tips": ["These two are close — book back-to-back"],
            }

            with patch("app.routers.tours.supabase_admin", mock_sb), \
                 patch("app.database.is_database_enabled", return_value=False), \
                 patch("app.routers.apartments._get_apartments_data", return_value=[SAMPLE_APARTMENT, {**SAMPLE_APARTMENT, "id": "apt-002", "address": "456 Oak Ave"}]), \
                 patch("app.services.claude_service.ClaudeService.generate_day_plan", return_value=mock_claude_result):
                response = client.post(
                    "/api/tours/day-plan",
                    json={"date": "2026-03-25", "tour_ids": ["tour-001", "tour-002"]},
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            data = response.json()
            assert len(data["tours_ordered"]) == 2
            assert len(data["travel_notes"]) >= 1
            assert len(data["tips"]) >= 1
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ── Enhance Note tests ─────────────────────────────────────────────


class TestEnhanceNote:
    def test_requires_auth(self):
        """POST /api/tours/{id}/enhance-note without auth returns 401."""
        response = client.post(
            "/api/tours/tour-001/enhance-note",
            json={"note_id": "note-001"},
        )
        assert response.status_code == 401

    def test_enhances_note(self):
        """POST /api/tours/{id}/enhance-note calls Claude and returns enhanced note."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()

            def table_router(table_name):
                mock_table = MagicMock()
                if table_name == "tour_pipeline":
                    # _verify_tour_ownership: select().eq().eq().execute()
                    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[SAMPLE_TOUR]
                    )
                elif table_name == "tour_notes":
                    # Fetch note by id + tour_pipeline_id
                    mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[{"id": "note-001", "content": "uh kitchen was like really nice, kinda small tho"}]
                    )
                return mock_table

            mock_sb.table.side_effect = table_router

            mock_claude_result = {
                "enhanced_text": "The kitchen was well-appointed but compact in size.",
                "suggested_tags": [
                    {"tag": "Nice kitchen", "sentiment": "pro"},
                    {"tag": "Small kitchen", "sentiment": "con"},
                ],
            }

            with patch("app.routers.tours.supabase_admin", mock_sb), \
                 patch("app.database.is_database_enabled", return_value=False), \
                 patch("app.routers.apartments._get_apartments_data", return_value=[SAMPLE_APARTMENT]), \
                 patch("app.services.claude_service.ClaudeService.enhance_note", return_value=mock_claude_result):
                response = client.post(
                    "/api/tours/tour-001/enhance-note",
                    json={"note_id": "note-001"},
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            data = response.json()
            assert "enhanced_text" in data
            assert len(data["suggested_tags"]) == 2
            assert data["suggested_tags"][0]["sentiment"] in ("pro", "con")
        finally:
            app.dependency_overrides.pop(get_current_user, None)


# ── Decision Brief tests ──────────────────────────────────────────

SAMPLE_TOUR_TOURED = {
    **SAMPLE_TOUR,
    "stage": "toured",
    "tour_rating": 4,
    "toured_at": "2026-03-20T12:00:00+00:00",
}

SAMPLE_TOUR_TOURED_2 = {
    **SAMPLE_TOUR,
    "id": "tour-002",
    "apartment_id": "apt-002",
    "stage": "toured",
    "tour_rating": 3,
    "toured_at": "2026-03-21T12:00:00+00:00",
}


class TestDecisionBrief:
    def test_requires_auth(self):
        """POST /api/tours/decision-brief without auth returns 401."""
        response = client.post("/api/tours/decision-brief")
        assert response.status_code == 401

    def test_generates_brief(self):
        """POST /api/tours/decision-brief calls Claude and returns brief."""
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()

            def table_router(table_name):
                mock_table = MagicMock()
                if table_name == "tour_pipeline":
                    # Fetch toured/deciding tours
                    mock_table.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
                        data=[SAMPLE_TOUR_TOURED, SAMPLE_TOUR_TOURED_2]
                    )
                elif table_name == "tour_notes":
                    mock_table.select.return_value.in_.return_value.execute.return_value = MagicMock(
                        data=[{"tour_pipeline_id": "tour-001", "content": "Great light"}]
                    )
                elif table_name == "tour_tags":
                    mock_table.select.return_value.in_.return_value.execute.return_value = MagicMock(
                        data=[{"tour_pipeline_id": "tour-001", "tag": "Spacious", "sentiment": "pro"}]
                    )
                return mock_table

            mock_sb.table.side_effect = table_router

            mock_claude_result = {
                "apartments": [
                    {
                        "apartment_id": "apt-001",
                        "ai_take": "Strong option with great natural light and spacious layout.",
                        "strengths": ["Great light", "Spacious"],
                        "concerns": ["Higher rent"],
                    },
                    {
                        "apartment_id": "apt-002",
                        "ai_take": "Budget-friendly but smaller.",
                        "strengths": ["Lower rent"],
                        "concerns": ["Less space"],
                    },
                ],
                "recommendation": {
                    "apartment_id": "apt-001",
                    "reasoning": "Better overall value with superior space and light.",
                },
            }

            with patch("app.routers.tours.supabase_admin", mock_sb), \
                 patch("app.database.is_database_enabled", return_value=False), \
                 patch("app.routers.apartments._get_apartments_data", return_value=[SAMPLE_APARTMENT, {**SAMPLE_APARTMENT, "id": "apt-002", "address": "456 Oak Ave"}]), \
                 patch("app.services.claude_service.ClaudeService.generate_decision_brief", return_value=mock_claude_result):
                response = client.post(
                    "/api/tours/decision-brief",
                    headers={"Authorization": "Bearer fake-token"},
                )

            assert response.status_code == 200
            data = response.json()
            assert len(data["apartments"]) == 2
            assert data["recommendation"]["apartment_id"] == "apt-001"
            assert "reasoning" in data["recommendation"]
        finally:
            app.dependency_overrides.pop(get_current_user, None)
