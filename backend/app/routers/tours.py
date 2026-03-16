"""Tour pipeline CRUD endpoints."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, UserContext
from app.services.tier_service import supabase_admin
from app.schemas import (
    CreateTourRequest,
    UpdateTourRequest,
    TourResponse,
    NoteResponse,
    PhotoResponse,
    TagResponse,
    VALID_TOUR_STAGES,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _ensure_supabase():
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")


def _build_tour_response(row: dict, notes=None, photos=None, tags=None) -> dict:
    """Build a TourResponse-compatible dict from a DB row."""
    return {
        "id": row["id"],
        "apartment_id": row["apartment_id"],
        "stage": row["stage"],
        "inquiry_email_draft": row.get("inquiry_email_draft"),
        "outreach_sent_at": row.get("outreach_sent_at"),
        "scheduled_date": row.get("scheduled_date"),
        "scheduled_time": row.get("scheduled_time"),
        "tour_rating": row.get("tour_rating"),
        "toured_at": row.get("toured_at"),
        "notes": notes or [],
        "photos": photos or [],
        "tags": tags or [],
        "decision": row.get("decision"),
        "decision_reason": row.get("decision_reason"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.post("/api/tours", status_code=201)
async def create_tour(
    body: CreateTourRequest,
    user: UserContext = Depends(get_current_user),
):
    """Add an apartment to the user's tour pipeline."""
    _ensure_supabase()

    try:
        # Check for duplicate apartment in this user's pipeline
        existing = (
            supabase_admin.table("tour_pipeline")
            .select("id")
            .eq("user_id", user.user_id)
            .eq("apartment_id", body.apartment_id)
            .execute()
        )
        if existing.data:
            raise HTTPException(
                status_code=409,
                detail="Apartment is already in your tour pipeline.",
            )

        row = {
            "user_id": user.user_id,
            "apartment_id": body.apartment_id,
            "stage": "interested",
        }
        result = (
            supabase_admin.table("tour_pipeline")
            .insert(row)
            .execute()
        )
        tour = result.data[0] if result.data else row
        return {"tour": _build_tour_response(tour)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create tour: {e}")
        raise HTTPException(status_code=500, detail="Failed to create tour")


@router.get("/api/tours")
async def list_tours(
    user: UserContext = Depends(get_current_user),
):
    """List all tour pipeline entries for the authenticated user."""
    _ensure_supabase()

    try:
        result = (
            supabase_admin.table("tour_pipeline")
            .select("*")
            .eq("user_id", user.user_id)
            .order("updated_at", desc=True)
            .execute()
        )
        tours = [_build_tour_response(row) for row in (result.data or [])]

        # Group: scheduled entries with closest dates first, then the rest by updated_at
        scheduled = [t for t in tours if t["stage"] == "scheduled"]
        others = [t for t in tours if t["stage"] != "scheduled"]

        # Sort scheduled by scheduled_date ascending (closest first)
        scheduled.sort(key=lambda t: t.get("scheduled_date") or "9999-12-31")

        return {"tours": scheduled + others}
    except Exception as e:
        logger.error(f"Failed to list tours: {e}")
        raise HTTPException(status_code=500, detail="Failed to list tours")


@router.get("/api/tours/{tour_id}")
async def get_tour(
    tour_id: str,
    user: UserContext = Depends(get_current_user),
):
    """Get a single tour pipeline entry with notes, photos, and tags."""
    _ensure_supabase()

    try:
        result = (
            supabase_admin.table("tour_pipeline")
            .select("*")
            .eq("id", tour_id)
            .eq("user_id", user.user_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Tour not found")

        tour_row = result.data[0]

        # Fetch related notes, photos, tags
        notes_result = (
            supabase_admin.table("tour_notes")
            .select("id, content, source, transcription_status, created_at")
            .eq("tour_id", tour_id)
            .order("created_at", desc=True)
            .execute()
        )

        photos_result = (
            supabase_admin.table("tour_photos")
            .select("id, thumbnail_url, caption, created_at")
            .eq("tour_id", tour_id)
            .order("created_at", desc=True)
            .execute()
        )

        tags_result = (
            supabase_admin.table("tour_tags")
            .select("id, tag, sentiment")
            .eq("tour_id", tour_id)
            .execute()
        )

        return {
            "tour": _build_tour_response(
                tour_row,
                notes=notes_result.data or [],
                photos=photos_result.data or [],
                tags=tags_result.data or [],
            )
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tour: {e}")
        raise HTTPException(status_code=500, detail="Failed to get tour")


@router.patch("/api/tours/{tour_id}")
async def update_tour(
    tour_id: str,
    body: UpdateTourRequest,
    user: UserContext = Depends(get_current_user),
):
    """Update a tour pipeline entry (advance stage, set rating, etc.)."""
    _ensure_supabase()

    try:
        # Build update dict from non-None fields
        updates = {}
        if body.stage is not None:
            updates["stage"] = body.stage
        if body.scheduled_date is not None:
            updates["scheduled_date"] = body.scheduled_date.isoformat()
        if body.scheduled_time is not None:
            updates["scheduled_time"] = body.scheduled_time.isoformat()
        if body.tour_rating is not None:
            updates["tour_rating"] = body.tour_rating
        if body.decision is not None:
            updates["decision"] = body.decision
        if body.decision_reason is not None:
            updates["decision_reason"] = body.decision_reason

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Auto-set timestamps for stage transitions
        if body.stage == "toured":
            updates.setdefault(
                "toured_at",
                datetime.now(timezone.utc).isoformat(),
            )
        if body.stage == "outreach_sent":
            updates.setdefault(
                "outreach_sent_at",
                datetime.now(timezone.utc).isoformat(),
            )

        result = (
            supabase_admin.table("tour_pipeline")
            .update(updates)
            .eq("id", tour_id)
            .eq("user_id", user.user_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Tour not found")

        return {"tour": _build_tour_response(result.data[0])}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update tour: {e}")
        raise HTTPException(status_code=500, detail="Failed to update tour")


@router.delete("/api/tours/{tour_id}")
async def delete_tour(
    tour_id: str,
    user: UserContext = Depends(get_current_user),
):
    """Remove a tour from the pipeline."""
    _ensure_supabase()

    try:
        result = (
            supabase_admin.table("tour_pipeline")
            .delete()
            .eq("id", tour_id)
            .eq("user_id", user.user_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Tour not found")

        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete tour: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete tour")
