"""Tests for DELETE /api/account (in-app account deletion)."""
from unittest.mock import patch, MagicMock

from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from app.auth import get_current_user, UserContext
from app.main import app

client = TestClient(app)

USER_ID = "11111111-2222-3333-4444-555555555555"
AUTH = {"Authorization": "Bearer fake-token"}


def _supabase(photos=None, notes=None):
    """supabase_admin whose tour_photos / tour_notes selects return the given rows."""
    sb = MagicMock()
    rows = {"tour_photos": photos or [], "tour_notes": notes or []}

    def table(name):
        t = MagicMock()
        t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=rows.get(name, []))
        return t

    sb.table.side_effect = table
    return sb


def _s3(listed=None, list_error=None, delete_errors=None):
    s3 = MagicMock()
    paginator = MagicMock()
    if list_error:
        paginator.paginate.side_effect = list_error
    else:
        paginator.paginate.return_value = [{"Contents": [{"Key": k} for k in (listed or [])]}]
    s3.get_paginator.return_value = paginator
    s3.delete_objects.return_value = {"Errors": delete_errors} if delete_errors else {}
    return s3


def _deleted_keys(s3):
    return sorted(o["Key"] for call in s3.delete_objects.call_args_list for o in call.kwargs["Delete"]["Objects"])


def _call(sb, s3, user_id=USER_ID):
    app.dependency_overrides[get_current_user] = lambda: UserContext(user_id=user_id, email="u@example.com")
    try:
        with patch("app.routers.account.supabase_admin", sb), \
             patch("app.routers.account._get_s3_client", return_value=s3), \
             patch("app.services.analytics_service.supabase_admin", None):
            return client.delete("/api/account", headers=AUTH)
    finally:
        app.dependency_overrides.clear()


def test_requires_auth():
    assert client.delete("/api/account").status_code == 401


def test_deletes_files_then_the_auth_user():
    sb = _supabase(
        photos=[{"s3_key": f"tours/{USER_ID}/t1/a.jpg", "thumbnail_s3_key": f"tours/{USER_ID}/t1/thumbs/a.jpg"}],
        notes=[{"audio_s3_key": f"tours/{USER_ID}/t1/voice/n.webm"}, {"audio_s3_key": None}],
    )
    # An orphan recording from a note deleted before recordings were cleaned up
    s3 = _s3(listed=[f"tours/{USER_ID}/t1/a.jpg", f"tours/{USER_ID}/t0/voice/orphan.webm"])

    order = []
    s3.delete_objects.side_effect = lambda **kw: order.append("files") or {}
    sb.auth.admin.delete_user.side_effect = lambda uid: order.append("auth")

    response = _call(sb, s3)

    assert response.status_code == 204
    assert _deleted_keys(s3) == sorted([
        f"tours/{USER_ID}/t1/a.jpg",
        f"tours/{USER_ID}/t1/thumbs/a.jpg",
        f"tours/{USER_ID}/t1/voice/n.webm",
        f"tours/{USER_ID}/t0/voice/orphan.webm",
    ])
    sb.auth.admin.delete_user.assert_called_once_with(USER_ID)
    assert order == ["files", "auth"]
    # The sweep is confined to this user's prefix
    s3.get_paginator.return_value.paginate.assert_called_once()
    assert s3.get_paginator.return_value.paginate.call_args.kwargs["Prefix"] == f"tours/{USER_ID}/"


def test_user_with_no_files_still_deleted():
    sb, s3 = _supabase(), _s3()
    assert _call(sb, s3).status_code == 204
    s3.delete_objects.assert_not_called()
    sb.auth.admin.delete_user.assert_called_once_with(USER_ID)


def test_without_list_permission_known_files_still_go():
    sb = _supabase(photos=[{"s3_key": f"tours/{USER_ID}/t1/a.jpg", "thumbnail_s3_key": None}])
    s3 = _s3(list_error=ClientError({"Error": {"Code": "AccessDenied"}}, "ListObjectsV2"))
    assert _call(sb, s3).status_code == 204
    assert _deleted_keys(s3) == [f"tours/{USER_ID}/t1/a.jpg"]
    sb.auth.admin.delete_user.assert_called_once()


def test_large_file_sets_are_batched_by_1000():
    listed = [f"tours/{USER_ID}/t/{i}.jpg" for i in range(2500)]
    sb, s3 = _supabase(), _s3(listed=listed)
    assert _call(sb, s3).status_code == 204
    assert [len(c.kwargs["Delete"]["Objects"]) for c in s3.delete_objects.call_args_list] == [1000, 1000, 500]


def test_file_failure_keeps_the_account():
    sb = _supabase(photos=[{"s3_key": f"tours/{USER_ID}/t1/a.jpg", "thumbnail_s3_key": None}])
    s3 = _s3(delete_errors=[{"Key": f"tours/{USER_ID}/t1/a.jpg", "Code": "AccessDenied"}])
    response = _call(sb, s3)
    assert response.status_code == 500
    assert "still there" in response.json()["detail"]
    sb.auth.admin.delete_user.assert_not_called()


def test_auth_failure_is_reported():
    sb, s3 = _supabase(), _s3()
    sb.auth.admin.delete_user.side_effect = Exception("gotrue down")
    assert _call(sb, s3).status_code == 500


def test_non_uuid_user_id_is_refused_before_touching_storage():
    sb, s3 = _supabase(), _s3()
    response = _call(sb, s3, user_id="")
    assert response.status_code == 400
    s3.get_paginator.assert_not_called()
    s3.delete_objects.assert_not_called()
    sb.auth.admin.delete_user.assert_not_called()
