"""Saved search CRUD endpoints (Pro only for creation)."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_user, UserContext
from app.services.tier_service import TierService, supabase_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class SaveSearchRequest(BaseModel):
    name: str
    city: str
    budget: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    property_type: Optional[str] = None
    preferences: Optional[str] = None


@router.get("/api/saved-searches")
async def list_saved_searches(
    user: UserContext = Depends(get_current_user),
):
    """List the authenticated user's saved searches."""
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    try:
        result = (
            supabase_admin.table("saved_searches")
            .select("*")
            .eq("user_id", user.user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return {"saved_searches": result.data or []}
    except Exception as e:
        logger.error(f"Failed to list saved searches: {e}")
        raise HTTPException(status_code=500, detail="Failed to list saved searches")


@router.post("/api/saved-searches", status_code=201)
async def create_saved_search(
    body: SaveSearchRequest,
    user: UserContext = Depends(get_current_user),
):
    """Create a saved search. Pro tier only."""
    tier = await TierService.get_user_tier(user.user_id)
    if tier != "pro":
        raise HTTPException(
            status_code=403,
            detail="Saved searches require a Pro subscription.",
        )

    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        row = {
            "user_id": user.user_id,
            "name": body.name,
            "city": body.city,
            "budget": body.budget,
            "bedrooms": body.bedrooms,
            "bathrooms": body.bathrooms,
            "property_type": body.property_type,
            "preferences": body.preferences,
        }
        result = (
            supabase_admin.table("saved_searches")
            .insert(row)
            .execute()
        )
        return {"saved_search": result.data[0] if result.data else row}
    except Exception as e:
        logger.error(f"Failed to create saved search: {e}")
        raise HTTPException(status_code=500, detail="Failed to create saved search")


@router.delete("/api/saved-searches/{search_id}")
async def delete_saved_search(
    search_id: str,
    user: UserContext = Depends(get_current_user),
):
    """Delete a saved search. Owner only."""
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        result = (
            supabase_admin.table("saved_searches")
            .delete()
            .eq("id", search_id)
            .eq("user_id", user.user_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Saved search not found")
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete saved search: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete saved search")
