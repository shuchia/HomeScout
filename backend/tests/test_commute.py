"""Tests for the commute calculator (CommuteService + endpoints)."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.commute_service import CommuteService


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------
class FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value


def _matrix(rows_durations):
    """Build a Distance Matrix-shaped response.

    rows_durations: list-per-origin of list-per-destination of seconds (or None
    for an unroutable element).
    """
    rows = []
    for origin in rows_durations:
        elements = []
        for secs in origin:
            if secs is None:
                elements.append({"status": "ZERO_RESULTS"})
            else:
                elements.append({"status": "OK", "duration": {"value": secs}})
        rows.append({"elements": elements})
    return {"status": "OK", "rows": rows}


def _service_with_response(response, redis=None):
    svc = CommuteService()
    svc.api_key = "test-key"
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=response)
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    svc._client = client
    svc._redis = redis if redis is not None else FakeRedis()
    return svc, client


APT = {"id": "apt-1", "latitude": 40.0, "longitude": -75.0}
LOC = {"label": "Office", "location_type": "work", "latitude": 40.1, "longitude": -75.1}


# ---------------------------------------------------------------------------
# CommuteService
# ---------------------------------------------------------------------------
async def test_disabled_without_api_key():
    svc = CommuteService()
    svc.api_key = ""
    assert svc.enabled is False
    result = await svc.get_commute_times_for_apartments([APT], [LOC])
    assert result == {}


async def test_no_locations_returns_empty():
    svc, _ = _service_with_response(_matrix([[600]]))
    assert await svc.get_commute_times_for_apartments([APT], []) == {}


async def test_compute_returns_minutes_per_mode():
    # 600s drive, 1500s transit, 2400s walk → 10 / 25 / 40 minutes.
    svc = CommuteService()
    svc.api_key = "test-key"
    svc._redis = FakeRedis()
    durations = {"driving": 600, "transit": 1500, "walking": 2400}

    async def fake_get(url, params=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=_matrix([[durations[params["mode"]]]]))
        return resp

    svc._client = MagicMock()
    svc._client.get = AsyncMock(side_effect=fake_get)

    result = await svc.get_commute_times_for_apartments([APT], [LOC])
    assert result["apt-1"][0] == {
        "label": "Office",
        "location_type": "work",
        "minutes_drive": 10,
        "minutes_transit": 25,
        "minutes_walk": 40,
    }


async def test_second_call_hits_cache():
    svc, client = _service_with_response(_matrix([[600]]))
    await svc.get_commute_times_for_apartments([APT], [LOC])
    calls_after_first = client.get.call_count
    assert calls_after_first == 3  # one per mode

    # Same apartment + location → fully served from Redis, no new API calls.
    result2 = await svc.get_commute_times_for_apartments([APT], [LOC])
    assert client.get.call_count == calls_after_first
    assert result2["apt-1"][0]["label"] == "Office"


async def test_fail_open_on_http_error():
    svc = CommuteService()
    svc.api_key = "test-key"
    svc._redis = FakeRedis()
    svc._client = MagicMock()
    svc._client.get = AsyncMock(side_effect=RuntimeError("boom"))

    result = await svc.get_commute_times_for_apartments([APT], [LOC])
    # Still returns a row, just with no minutes (no route).
    row = result["apt-1"][0]
    assert row["minutes_drive"] is None
    assert row["minutes_transit"] is None
    assert row["minutes_walk"] is None


async def test_apartment_without_coords_skipped():
    svc, _ = _service_with_response(_matrix([[600]]))
    no_coords = {"id": "apt-2", "latitude": None, "longitude": None}
    result = await svc.get_commute_times_for_apartments([no_coords], [LOC])
    assert "apt-2" not in result


# ---------------------------------------------------------------------------
# Endpoints (auth gating)
# ---------------------------------------------------------------------------
client = TestClient(app)


def test_list_locations_requires_auth():
    r = client.get("/api/user/locations")
    assert r.status_code in (401, 403)


def test_create_location_requires_auth():
    r = client.post("/api/user/locations", json={
        "location_type": "work", "label": "Office",
        "address": "123 Main St", "latitude": 40.0, "longitude": -75.0,
    })
    assert r.status_code in (401, 403)


def test_commute_anonymous_returns_empty_map():
    # get_optional_user → None for anonymous; endpoint returns empty map, not error.
    r = client.post("/api/apartments/commute", json={"apartment_ids": ["apt-1"]})
    assert r.status_code == 200
    assert r.json() == {"commute_times": {}}
