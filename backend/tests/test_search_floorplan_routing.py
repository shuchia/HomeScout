"""Phase 2 routing tests for floorplan-aware search dispatch.

Verifies the USE_FLOORPLAN_SEARCH flag routes _search_database to the right
implementation and that bedroom_mode is threaded through — without needing a
live Postgres (the actual join is validated on QA in the Phase 2 lead-in). The
two DB implementations are patched to record their calls.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.apartment_service import ApartmentService


@pytest.fixture
def service():
    # Avoid touching real infra during construction.
    with patch("app.services.apartment_service.is_database_enabled", return_value=True), \
         patch("app.services.apartment_service.ClaudeService"):
        svc = ApartmentService()
    svc._use_database = True
    return svc


@pytest.mark.asyncio
async def test_flag_off_routes_to_building(service):
    building = AsyncMock(return_value=[{"id": "b"}])
    floorplan = AsyncMock(return_value=[{"id": "f"}])
    with patch("app.services.apartment_service.USE_FLOORPLAN_SEARCH", False), \
         patch.object(service, "_search_database_building", building), \
         patch.object(service, "_search_database_floorplan", floorplan):
        out = await service._search_database(
            "Boston, MA", 4800, 3, 1, "Apartment", "2026-08-01"
        )
    building.assert_awaited_once()
    floorplan.assert_not_awaited()
    assert out == [{"id": "b"}]


@pytest.mark.asyncio
async def test_flag_on_routes_to_floorplan_with_mode(service):
    building = AsyncMock(return_value=[{"id": "b"}])
    floorplan = AsyncMock(return_value=[{"id": "f"}])
    with patch("app.services.apartment_service.USE_FLOORPLAN_SEARCH", True), \
         patch.object(service, "_search_database_building", building), \
         patch.object(service, "_search_database_floorplan", floorplan):
        out = await service._search_database(
            "Boston, MA", 4800, 3, 1, "Apartment", "2026-08-01", bedroom_mode="plus"
        )
    floorplan.assert_awaited_once()
    building.assert_not_awaited()
    # bedroom_mode threaded through to the floorplan impl.
    assert floorplan.await_args.args[-1] == "plus"
    assert out == [{"id": "f"}]


@pytest.mark.asyncio
async def test_search_apartments_passes_mode_through(service):
    inner = AsyncMock(return_value=[])
    with patch.object(service, "_search_database", inner):
        await service.search_apartments(
            "Boston, MA", 4800, 3, 1, "Apartment", "2026-08-01", bedroom_mode="plus"
        )
    assert inner.await_args.kwargs.get("bedroom_mode") == "plus"


# ── Phase 3: AI-scoring path projects the matched floorplan ──

@pytest.mark.asyncio
async def test_get_by_ids_projects_floorplan_when_flag_on(service):
    """With the flag on and bedrooms given, get_apartments_by_ids routes to the
    floorplan-projecting variant so AI scores the searched unit, not the studio."""
    fp = AsyncMock(return_value=[{"id": "x", "bedrooms": 3}])
    with patch("app.services.apartment_service.USE_FLOORPLAN_SEARCH", True), \
         patch.object(service, "_get_by_ids_floorplan", fp):
        out = await service.get_apartments_by_ids(
            ["x"], bedrooms=3, bathrooms=1, budget=4800
        )
    fp.assert_awaited_once()
    assert out[0]["bedrooms"] == 3


@pytest.mark.asyncio
async def test_get_by_ids_building_level_when_flag_off(service):
    """Flag off → no floorplan projection, even with bedrooms given."""
    fp = AsyncMock(return_value=[{"id": "proj"}])
    with patch("app.services.apartment_service.USE_FLOORPLAN_SEARCH", False), \
         patch.object(service, "_get_by_ids_floorplan", fp):
        # DB path with flag off hits the plain query; patch the session out by
        # forcing JSON mode so no DB is needed.
        service._use_database = False
        service._apartments_data = [{"id": "x", "bedrooms": 0}]
        out = await service.get_apartments_by_ids(["x"], bedrooms=3)
    fp.assert_not_awaited()
    assert out[0]["id"] == "x"


# ── Phase 4: near-miss fallback + match_type ──

from contextlib import asynccontextmanager


@asynccontextmanager
async def _fake_session():
    yield object()


@pytest.mark.asyncio
async def test_exact_match_tags_match_type(service):
    """Primary (exact) query returns rows → tagged match_type='exact', no near-miss."""
    rows = AsyncMock(return_value=[("apt", "fp")])
    proj = lambda r, match_type: [{"match_type": match_type}]
    with patch("app.services.apartment_service.get_session_context", lambda: _fake_session()), \
         patch.object(ApartmentService, "_floorplan_rows", rows), \
         patch.object(ApartmentService, "_project_floorplan_rows", side_effect=proj):
        out = await service._search_database_floorplan(
            "Boston, MA", 4800, 3, 1, "Apartment", bedroom_mode="exact"
        )
    assert rows.await_count == 1          # primary only, no near-miss
    assert out[0]["match_type"] == "exact"


@pytest.mark.asyncio
async def test_near_miss_fires_when_primary_empty(service):
    """Primary empty → widen bedrooms; first non-empty near-miss tagged 'near_miss'."""
    # primary → [], first near-miss delta → [], second → rows
    rows = AsyncMock(side_effect=[[], [], [("apt", "fp")]])
    proj = lambda r, match_type: [{"match_type": match_type}]
    with patch("app.services.apartment_service.get_session_context", lambda: _fake_session()), \
         patch.object(ApartmentService, "_floorplan_rows", rows), \
         patch.object(ApartmentService, "_project_floorplan_rows", side_effect=proj):
        out = await service._search_database_floorplan(
            "Boston, MA", 4800, 3, 1, "Apartment", bedroom_mode="exact"
        )
    assert rows.await_count == 3          # primary + 2 near-miss widenings
    assert out[0]["match_type"] == "near_miss"


@pytest.mark.asyncio
async def test_no_results_returns_empty(service):
    """Neither exact nor any near-miss matches → empty."""
    rows = AsyncMock(return_value=[])
    with patch("app.services.apartment_service.get_session_context", lambda: _fake_session()), \
         patch.object(ApartmentService, "_floorplan_rows", rows):
        out = await service._search_database_floorplan(
            "Boston, MA", 4800, 3, 1, "Apartment", bedroom_mode="exact"
        )
    assert out == []
