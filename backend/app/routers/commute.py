"""Commute calculator endpoints.

Two surfaces:
  - CRUD for the user's saved work/school addresses (`/api/user/locations`),
    auth required, any tier. Geocoding happens client-side (Nominatim), so we
    just store the lat/lng. Mirrors `routers/saved_searches.py`.
  - `POST /api/apartments/commute` — given apartment IDs, returns drive/transit/
    walk minutes from each apartment to each of the user's saved locations.
    Restricted (by the frontend) to the shortlist views: tour detail, compare,
    favorites. Returns an empty map for anonymous users or users with no saved
    locations — never errors on the happy-path-less case.
"""
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_user, get_optional_user, UserContext
from app.schemas import UserLocationCreate
from app.services.commute_service import commute_service
from app.services.tier_service import supabase_admin
from app.database import is_database_enabled, get_session_context
from app.routers.apartments import _get_apartments_data

logger = logging.getLogger(__name__)

router = APIRouter()


class CommuteRequest(BaseModel):
    apartment_ids: List[str] = Field(..., max_length=50)


async def _apartment_coords(ids: List[str]) -> List[Dict[str, Any]]:
    """Fetch {id, latitude, longitude} for the given apartment IDs (dual-mode)."""
    if is_database_enabled():
        from sqlalchemy import select
        from app.models.apartment import ApartmentModel
        async with get_session_context() as session:
            rows = await session.execute(
                select(ApartmentModel).where(ApartmentModel.id.in_(ids))
            )
            return [
                {"id": a.id, "latitude": a.latitude, "longitude": a.longitude}
                for a in rows.scalars()
            ]
    wanted = set(ids)
    return [
        {"id": a.get("id"), "latitude": a.get("latitude"), "longitude": a.get("longitude")}
        for a in _get_apartments_data()
        if a.get("id") in wanted
    ]


# ---------------------------------------------------------------------------
# Saved work/school addresses
# ---------------------------------------------------------------------------
@router.get("/api/user/locations")
async def list_locations(user: UserContext = Depends(get_current_user)):
    """List the authenticated user's saved work/school locations."""
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    try:
        result = (
            supabase_admin.table("user_locations")
            .select("*")
            .eq("user_id", user.user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return {"locations": result.data or []}
    except Exception as e:
        logger.error(f"Failed to list locations: {e}")
        raise HTTPException(status_code=500, detail="Failed to list locations")


@router.post("/api/user/locations", status_code=201)
async def create_location(
    body: UserLocationCreate,
    user: UserContext = Depends(get_current_user),
):
    """Save a work/school address (geocoded client-side)."""
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    row = {
        "user_id": user.user_id,
        "location_type": body.location_type,
        "label": body.label,
        "address": body.address,
        "latitude": body.latitude,
        "longitude": body.longitude,
    }
    try:
        result = supabase_admin.table("user_locations").insert(row).execute()
        return {"location": result.data[0] if result.data else row}
    except Exception as e:
        # Most likely the unique(user_id, label) constraint.
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"You already have a location labeled “{body.label}”.")
        logger.error(f"Failed to create location: {e}")
        raise HTTPException(status_code=500, detail="Failed to save location")


@router.delete("/api/user/locations/{location_id}")
async def delete_location(
    location_id: str,
    user: UserContext = Depends(get_current_user),
):
    """Delete one of the authenticated user's saved locations."""
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    try:
        result = (
            supabase_admin.table("user_locations")
            .delete()
            .eq("id", location_id)
            .eq("user_id", user.user_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Location not found")
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete location: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete location")


# ---------------------------------------------------------------------------
# Commute computation
# ---------------------------------------------------------------------------
@router.post("/api/apartments/commute")
async def compute_commute(
    body: CommuteRequest,
    user: UserContext | None = Depends(get_optional_user),
):
    """Return apartment_id -> [commute rows] for the user's saved locations.

    Empty map (not an error) when: anonymous, no saved locations, no apartment
    IDs, or the commute service is disabled (missing API key).
    """
    empty: Dict[str, Any] = {"commute_times": {}}
    if not user or not body.apartment_ids or not supabase_admin:
        return empty

    try:
        loc_res = (
            supabase_admin.table("user_locations")
            .select("*")
            .eq("user_id", user.user_id)
            .execute()
        )
        locations = loc_res.data or []
    except Exception as e:
        logger.warning(f"Failed to load user locations for commute: {e}")
        return empty

    if not locations:
        return empty

    apartments = await _apartment_coords(body.apartment_ids)
    times = await commute_service.get_commute_times_for_apartments(apartments, locations)
    return {"commute_times": times}
