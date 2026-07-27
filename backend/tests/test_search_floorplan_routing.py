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
