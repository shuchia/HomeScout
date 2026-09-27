"""Background checks of saved listings against their source.

Runs out of band because a check takes 10-20 seconds — the Apify actor has
container start-up overhead even for a single listing. Blocking a favourite
button on that would be a worse experience than briefly showing a price that
turns out to have moved, so the request returns immediately with the corpus
copy and this corrects it a few seconds later.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from app.celery_app import celery_app
from app.tasks._async_runner import run_async

logger = logging.getLogger(__name__)


@celery_app.task
def check_saved_listing(saved_listing_id: str) -> Dict[str, Any]:
    """Check one saved listing and write back what we learn."""
    return run_async(_check_saved_listing(saved_listing_id))


async def _check_saved_listing(saved_listing_id: str) -> Dict[str, Any]:
    from app.services.tier_service import supabase_admin
    from app.services.listing_check import check_listing, GONE, LIVE, UNKNOWN

    if not supabase_admin:
        return {"status": "skipped", "reason": "Supabase not configured"}

    row_result = (
        supabase_admin.table("saved_listings")
        .select("id, user_id, source_url, listing, decision")
        .eq("id", saved_listing_id)
        .execute()
    )
    if not row_result.data:
        return {"status": "skipped", "reason": "not found"}

    row = row_result.data[0]

    # A listing the user has already applied for or passed on keeps the state
    # it was decided on. Refreshing it would rewrite the basis of a decision
    # that has already been made.
    if row.get("decision"):
        return {"status": "skipped", "reason": "decided", "id": saved_listing_id}

    current = row.get("listing") or {}
    source_url = row.get("source_url") or current.get("source_url")

    status, updated, changes = await check_listing(source_url, current)

    now = datetime.now(timezone.utc).isoformat()
    patch: Dict[str, Any] = {
        "availability_status": status,
        "listing_checked_at": now,
    }
    if status == LIVE and updated is not None:
        patch["listing"] = updated

    if changes:
        # Drives the "price changed since you saved this" marker. Deliberately
        # overwrites rather than accumulating: the user needs to know the
        # current state differs from what they last saw, not every hop it took
        # to get there. The full history goes to analytics_events below.
        patch["last_change"] = changes
        patch["last_change_at"] = now

    try:
        (
            supabase_admin.table("saved_listings")
            .update(patch)
            .eq("id", saved_listing_id)
            .execute()
        )
    except Exception as e:
        logger.warning(f"Could not write check result for {saved_listing_id}: {e}")
        return {"status": "failed", "error": str(e)}

    # `listing` is overwritten in place, so without this the fact that a price
    # ever moved leaves no trace anywhere. Logging the diff keeps that history
    # at no schema cost — see the note in migration 011 on listing_as_saved.
    if changes:
        from app.services.analytics_service import AnalyticsService

        await AnalyticsService.log_event(
            "listing-changed",
            user_id=row.get("user_id"),
            metadata={
                "saved_listing_id": saved_listing_id,
                "source_url": source_url,
                "changes": changes,
            },
        )

    if status == GONE:
        from app.services.analytics_service import AnalyticsService

        await AnalyticsService.log_event(
            "listing-gone",
            user_id=row.get("user_id"),
            metadata={"saved_listing_id": saved_listing_id, "source_url": source_url},
        )

    logger.info(
        f"Checked saved listing {saved_listing_id}: {status}, "
        f"{len(changes)} material change(s)"
    )
    return {
        "status": "completed",
        "id": saved_listing_id,
        "availability_status": status,
        "changes": changes,
    }
