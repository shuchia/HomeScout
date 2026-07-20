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
