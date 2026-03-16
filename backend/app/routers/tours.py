"""Tour pipeline CRUD endpoints."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, UserContext
from app.services.tier_service import supabase_admin
from app.schemas import (
    CreateTourRequest,
    UpdateTourRequest,
    CreateNoteRequest,
    CreatePhotoRequest,
    UpdatePhotoRequest,
    CreateTagRequest,
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


DEFAULT_TAGS = [
    {"tag": "Great light", "sentiment": "pro"},
    {"tag": "Spacious", "sentiment": "pro"},
    {"tag": "Quiet", "sentiment": "pro"},
    {"tag": "Modern", "sentiment": "pro"},
    {"tag": "Good storage", "sentiment": "pro"},
    {"tag": "Pet-friendly", "sentiment": "pro"},
    {"tag": "Small kitchen", "sentiment": "con"},
    {"tag": "Street noise", "sentiment": "con"},
    {"tag": "Needs work", "sentiment": "con"},
    {"tag": "Limited parking", "sentiment": "con"},
]


def _verify_tour_ownership(tour_id: str, user_id: str):
    """Verify the tour belongs to the user, raise 404 if not."""
    result = (
        supabase_admin.table("tour_pipeline")
        .select("id")
        .eq("id", tour_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Tour not found")


# ── Tag suggestions (must be before /{tour_id} routes) ──────────────


@router.get("/api/tours/tags/suggestions")
async def get_tag_suggestions(
    user: UserContext = Depends(get_current_user),
):
    """Return default tag suggestions plus the user's past tags."""
    _ensure_supabase()

    try:
        # Fetch user's existing tags across all tours
        user_tours = (
            supabase_admin.table("tour_pipeline")
            .select("id")
            .eq("user_id", user.user_id)
            .execute()
        )
        tour_ids = [t["id"] for t in (user_tours.data or [])]

        user_tags: list[dict] = []
        if tour_ids:
            tags_result = (
                supabase_admin.table("tour_tags")
                .select("tag, sentiment")
                .in_("tour_pipeline_id", tour_ids)
                .execute()
            )
            # Count occurrences
            tag_counts: dict[tuple, int] = {}
            for row in (tags_result.data or []):
                key = (row["tag"], row["sentiment"])
                tag_counts[key] = tag_counts.get(key, 0) + 1

            user_tags = [
                {"tag": k[0], "sentiment": k[1], "count": v}
                for k, v in tag_counts.items()
            ]

        # Build defaults with count=0
        user_keys = {(t["tag"], t["sentiment"]) for t in user_tags}

        suggestions = list(user_tags)
        for d in DEFAULT_TAGS:
            if (d["tag"], d["sentiment"]) not in user_keys:
                suggestions.append({"tag": d["tag"], "sentiment": d["sentiment"], "count": 0})

        return {"suggestions": suggestions}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tag suggestions: {e}")
        raise HTTPException(status_code=500, detail="Failed to get tag suggestions")


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
            .eq("tour_pipeline_id", tour_id)
            .order("created_at", desc=True)
            .execute()
        )

        photos_result = (
            supabase_admin.table("tour_photos")
            .select("id, thumbnail_url, caption, created_at")
            .eq("tour_pipeline_id", tour_id)
            .order("created_at", desc=True)
            .execute()
        )

        tags_result = (
            supabase_admin.table("tour_tags")
            .select("id, tag, sentiment")
            .eq("tour_pipeline_id", tour_id)
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


# ── Notes sub-resource endpoints ─────────────────────────────────────


@router.post("/api/tours/{tour_id}/notes", status_code=201)
async def create_note(
    tour_id: str,
    body: CreateNoteRequest,
    user: UserContext = Depends(get_current_user),
):
    """Add a typed note to a tour."""
    _ensure_supabase()

    try:
        _verify_tour_ownership(tour_id, user.user_id)

        row = {
            "tour_pipeline_id": tour_id,
            "content": body.content,
            "source": "typed",
            "transcription_status": "complete",
        }
        result = (
            supabase_admin.table("tour_notes")
            .insert(row)
            .execute()
        )
        note = result.data[0] if result.data else row
        return {"note": note}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create note: {e}")
        raise HTTPException(status_code=500, detail="Failed to create note")


@router.get("/api/tours/{tour_id}/notes")
async def list_notes(
    tour_id: str,
    user: UserContext = Depends(get_current_user),
):
    """List all notes for a tour in chronological order."""
    _ensure_supabase()

    try:
        _verify_tour_ownership(tour_id, user.user_id)

        result = (
            supabase_admin.table("tour_notes")
            .select("id, content, source, transcription_status, created_at")
            .eq("tour_pipeline_id", tour_id)
            .order("created_at", desc=False)
            .execute()
        )
        return {"notes": result.data or []}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list notes: {e}")
        raise HTTPException(status_code=500, detail="Failed to list notes")


@router.delete("/api/tours/{tour_id}/notes/{note_id}")
async def delete_note(
    tour_id: str,
    note_id: str,
    user: UserContext = Depends(get_current_user),
):
    """Delete a note from a tour."""
    _ensure_supabase()

    try:
        _verify_tour_ownership(tour_id, user.user_id)

        result = (
            supabase_admin.table("tour_notes")
            .delete()
            .eq("id", note_id)
            .eq("tour_pipeline_id", tour_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Note not found")

        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete note: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete note")


# ── Photos sub-resource endpoints ────────────────────────────────────


@router.post("/api/tours/{tour_id}/photos", status_code=201)
async def create_photo(
    tour_id: str,
    body: CreatePhotoRequest,
    user: UserContext = Depends(get_current_user),
):
    """Add a photo entry to a tour (metadata only; S3 upload is Task 4)."""
    _ensure_supabase()

    try:
        _verify_tour_ownership(tour_id, user.user_id)

        row = {
            "tour_pipeline_id": tour_id,
            "s3_key": body.s3_key,
            "thumbnail_url": body.thumbnail_url,
            "caption": body.caption,
        }
        result = (
            supabase_admin.table("tour_photos")
            .insert(row)
            .execute()
        )
        photo = result.data[0] if result.data else row
        return {"photo": photo}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create photo: {e}")
        raise HTTPException(status_code=500, detail="Failed to create photo")


@router.get("/api/tours/{tour_id}/photos")
async def list_photos(
    tour_id: str,
    user: UserContext = Depends(get_current_user),
):
    """List all photos for a tour."""
    _ensure_supabase()

    try:
        _verify_tour_ownership(tour_id, user.user_id)

        result = (
            supabase_admin.table("tour_photos")
            .select("id, s3_key, thumbnail_url, caption, created_at")
            .eq("tour_pipeline_id", tour_id)
            .order("created_at", desc=True)
            .execute()
        )
        return {"photos": result.data or []}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list photos: {e}")
        raise HTTPException(status_code=500, detail="Failed to list photos")


@router.patch("/api/tours/{tour_id}/photos/{photo_id}")
async def update_photo(
    tour_id: str,
    photo_id: str,
    body: UpdatePhotoRequest,
    user: UserContext = Depends(get_current_user),
):
    """Update a photo's caption."""
    _ensure_supabase()

    try:
        _verify_tour_ownership(tour_id, user.user_id)

        result = (
            supabase_admin.table("tour_photos")
            .update({"caption": body.caption})
            .eq("id", photo_id)
            .eq("tour_pipeline_id", tour_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Photo not found")

        return {"photo": result.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update photo: {e}")
        raise HTTPException(status_code=500, detail="Failed to update photo")


@router.delete("/api/tours/{tour_id}/photos/{photo_id}")
async def delete_photo(
    tour_id: str,
    photo_id: str,
    user: UserContext = Depends(get_current_user),
):
    """Delete a photo from a tour."""
    _ensure_supabase()

    try:
        _verify_tour_ownership(tour_id, user.user_id)

        result = (
            supabase_admin.table("tour_photos")
            .delete()
            .eq("id", photo_id)
            .eq("tour_pipeline_id", tour_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Photo not found")

        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete photo: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete photo")


# ── Tags sub-resource endpoints ──────────────────────────────────────


@router.post("/api/tours/{tour_id}/tags", status_code=201)
async def create_tag(
    tour_id: str,
    body: CreateTagRequest,
    user: UserContext = Depends(get_current_user),
):
    """Add a pro/con tag to a tour."""
    _ensure_supabase()

    try:
        _verify_tour_ownership(tour_id, user.user_id)

        row = {
            "tour_pipeline_id": tour_id,
            "tag": body.tag,
            "sentiment": body.sentiment,
        }
        result = (
            supabase_admin.table("tour_tags")
            .insert(row)
            .execute()
        )
        tag = result.data[0] if result.data else row
        return {"tag": tag}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create tag: {e}")
        raise HTTPException(status_code=500, detail="Failed to create tag")


@router.delete("/api/tours/{tour_id}/tags/{tag_id}")
async def delete_tag(
    tour_id: str,
    tag_id: str,
    user: UserContext = Depends(get_current_user),
):
    """Remove a tag from a tour."""
    _ensure_supabase()

    try:
        _verify_tour_ownership(tour_id, user.user_id)

        result = (
            supabase_admin.table("tour_tags")
            .delete()
            .eq("id", tag_id)
            .eq("tour_pipeline_id", tour_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Tag not found")

        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete tag: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete tag")
