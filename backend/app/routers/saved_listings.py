"""Saved listings — the user's own copy of a listing.

One record per (user, listing), replacing the old split between `favorites`
and `tour_pipeline`. `is_favorite` is the star; `stage` is position in the
touring pipeline and is NULL when the listing isn't in it. They are
independent, so un-starring something you have already toured leaves it in the
pipeline.

Every route that represents the user committing to a listing — favouriting,
comparing, adding to tours — queues a check of that listing against its source.
The response does not wait for it: a check takes 10-20 seconds, so the row is
created from the corpus copy immediately and corrected shortly after. Clients
should poll or re-fetch to pick up `listing_checked_at`, `availability_status`
and any revised numbers.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import get_current_user, UserContext
from app.services.tier_service import supabase_admin

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_STAGES = ("interested", "outreach_sent", "scheduled", "toured", "deciding")


class CreateSavedListingRequest(BaseModel):
    apartment_id: Optional[str] = None
    source_url: Optional[str] = None
    is_favorite: bool = False
    stage: Optional[str] = None


class UpdateSavedListingRequest(BaseModel):
    is_favorite: Optional[bool] = None
    stage: Optional[str] = None
    tour_rating: Optional[int] = None
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None
    decision: Optional[str] = None
    decision_reason: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None


def _ensure_supabase():
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")


def _queue_check(saved_listing_id: str) -> None:
    """Queue a source check. Never blocks and never fails the request."""
    try:
        from app.tasks.listing_check_tasks import check_saved_listing

        check_saved_listing.apply_async(
            kwargs={"saved_listing_id": saved_listing_id}, queue="maintenance"
        )
    except Exception as e:
        # A missing check is a stale number, not a broken save.
        logger.warning(f"Could not queue check for {saved_listing_id}: {e}")


async def _corpus_listing(apartment_id: str) -> Optional[Dict[str, Any]]:
    """Read a listing out of the scraped corpus, in whichever mode is active."""
    from app.database import is_database_enabled, get_session_context

    if is_database_enabled():
        from sqlalchemy import select
        from app.models.apartment import ApartmentModel

        async with get_session_context() as session:
            result = await session.execute(
                select(ApartmentModel).where(ApartmentModel.id == apartment_id)
            )
            apt = result.scalar_one_or_none()
            return apt.to_dict() if apt else None

    from app.routers.apartments import _get_apartments_data

    for a in _get_apartments_data():
        if a.get("id") == apartment_id:
            return a
    return None


@router.post("/api/saved-listings", status_code=201)
async def create_saved_listing(
    body: CreateSavedListingRequest,
    user: UserContext = Depends(get_current_user),
):
    """Save a listing, or update the one already saved.

    Idempotent on (user, listing): favouriting something already in the tour
    pipeline flips the star rather than erroring, which is what the unique
    index on (user_id, dedupe_key) would otherwise turn into a 409.
    """
    _ensure_supabase()

    if not body.apartment_id and not body.source_url:
        raise HTTPException(
            status_code=400,
            detail="Either apartment_id or source_url is required.",
        )
    if body.stage and body.stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {body.stage}")

    listing: Dict[str, Any] = {}
    source_url = body.source_url
    if body.apartment_id:
        listing = await _corpus_listing(body.apartment_id) or {}
        if not listing:
            raise HTTPException(status_code=404, detail="Apartment not found")
        source_url = source_url or listing.get("source_url")

    try:
        dedupe = body.apartment_id or (source_url or "").lower()
        existing = (
            supabase_admin.table("saved_listings")
            .select("*")
            .eq("user_id", user.user_id)
            .eq("dedupe_key", dedupe)
            .execute()
        )

        if existing.data:
            row = existing.data[0]
            patch: Dict[str, Any] = {}
            if body.is_favorite:
                patch["is_favorite"] = True
            if body.stage:
                patch["stage"] = body.stage
            if patch:
                updated = (
                    supabase_admin.table("saved_listings")
                    .update(patch)
                    .eq("id", row["id"])
                    .execute()
                )
                row = updated.data[0] if updated.data else {**row, **patch}
            _queue_check(row["id"])
            return {"saved_listing": row, "created": False}

        insert: Dict[str, Any] = {
            "user_id": user.user_id,
            "apartment_id": body.apartment_id,
            "source": "corpus" if body.apartment_id else "url",
            "source_url": source_url,
            "listing": listing,
            "is_favorite": body.is_favorite,
            "stage": body.stage,
        }
        if listing.get("contact_phone"):
            insert["contact_phone"] = listing["contact_phone"]
        if listing.get("contact_email"):
            insert["contact_email"] = listing["contact_email"]

        result = supabase_admin.table("saved_listings").insert(insert).execute()
        row = result.data[0] if result.data else insert
        _queue_check(row["id"])

        from app.services.analytics_service import AnalyticsService

        await AnalyticsService.log_event(
            "favorite-add" if body.is_favorite else "listing-save",
            user_id=user.user_id,
            metadata={"apartment_id": body.apartment_id, "source_url": source_url},
        )

        return {"saved_listing": row, "created": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save listing: {e}")
        raise HTTPException(status_code=500, detail="Failed to save listing")


@router.get("/api/saved-listings")
async def list_saved_listings(
    favorites_only: bool = Query(False),
    in_pipeline: bool = Query(False),
    user: UserContext = Depends(get_current_user),
):
    """List saved listings. Unfiltered this is the board."""
    _ensure_supabase()
    try:
        q = (
            supabase_admin.table("saved_listings")
            .select("*")
            .eq("user_id", user.user_id)
        )
        if favorites_only:
            q = q.eq("is_favorite", True)
        if in_pipeline:
            q = q.not_.is_("stage", "null")
        result = q.order("created_at", desc=True).execute()
        return {"saved_listings": result.data or []}
    except Exception as e:
        logger.error(f"Failed to list saved listings: {e}")
        raise HTTPException(status_code=500, detail="Failed to list saved listings")


@router.post("/api/saved-listings/check")
async def check_saved_listings(
    ids: List[str],
    user: UserContext = Depends(get_current_user),
):
    """Queue checks for several saved listings at once.

    This is the comparison path: a brief or head-to-head run over listings
    saved at different times would otherwise compare across time, each snapshot
    accurate when taken but not contemporaneous with the others.
    """
    _ensure_supabase()
    if not ids:
        return {"queued": 0}
    try:
        owned = (
            supabase_admin.table("saved_listings")
            .select("id")
            .eq("user_id", user.user_id)
            .in_("id", ids[:50])
            .execute()
        )
        for row in owned.data or []:
            _queue_check(row["id"])
        return {"queued": len(owned.data or [])}
    except Exception as e:
        logger.error(f"Failed to queue checks: {e}")
        raise HTTPException(status_code=500, detail="Failed to queue checks")


@router.patch("/api/saved-listings/{saved_listing_id}")
async def update_saved_listing(
    saved_listing_id: str,
    body: UpdateSavedListingRequest,
    user: UserContext = Depends(get_current_user),
):
    """Update a saved listing's star, stage or tour fields."""
    _ensure_supabase()
    if body.stage is not None and body.stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {body.stage}")

    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="Nothing to update")

    try:
        result = (
            supabase_admin.table("saved_listings")
            .update(patch)
            .eq("id", saved_listing_id)
            .eq("user_id", user.user_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Saved listing not found")

        row = result.data[0]

        # Entering the pipeline is a commitment, so re-check. A decision is the
        # opposite — it freezes the record, and check_saved_listing skips
        # anything with `decision` set.
        if body.stage and not row.get("decision"):
            _queue_check(saved_listing_id)

        return {"saved_listing": row}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update saved listing: {e}")
        raise HTTPException(status_code=500, detail="Failed to update saved listing")


@router.delete("/api/saved-listings/{saved_listing_id}", status_code=204)
async def delete_saved_listing(
    saved_listing_id: str,
    user: UserContext = Depends(get_current_user),
):
    """Remove a saved listing entirely, notes and photos included."""
    _ensure_supabase()
    try:
        (
            supabase_admin.table("saved_listings")
            .delete()
            .eq("id", saved_listing_id)
            .eq("user_id", user.user_id)
            .execute()
        )
        return None
    except Exception as e:
        logger.error(f"Failed to delete saved listing: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete saved listing")


@router.post("/api/saved-listings/{saved_listing_id}/unfavorite")
async def unfavorite_saved_listing(
    saved_listing_id: str,
    user: UserContext = Depends(get_current_user),
):
    """Un-star a listing, keeping it if it is in the tour pipeline.

    The row is deleted only when nothing would remain — not starred and not in
    the pipeline — because there is no board UI yet, so such a row would be
    invisible but still counted against the user's saved listings. Once
    listings can live on a board without being starred, this must stop
    deleting and simply clear the flag.
    """
    _ensure_supabase()
    try:
        result = (
            supabase_admin.table("saved_listings")
            .select("id, stage")
            .eq("id", saved_listing_id)
            .eq("user_id", user.user_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Saved listing not found")

        row = result.data[0]
        if row.get("stage"):
            updated = (
                supabase_admin.table("saved_listings")
                .update({"is_favorite": False})
                .eq("id", saved_listing_id)
                .execute()
            )
            return {"saved_listing": updated.data[0] if updated.data else None, "deleted": False}

        (
            supabase_admin.table("saved_listings")
            .delete()
            .eq("id", saved_listing_id)
            .execute()
        )
        return {"saved_listing": None, "deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unfavorite: {e}")
        raise HTTPException(status_code=500, detail="Failed to unfavorite")
