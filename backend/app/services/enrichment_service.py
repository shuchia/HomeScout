"""Per-listing detail enrichment via Apify URL-mode.

Triggered after the user adds an apartment to their tour pipeline. The bulk
search scrape covers ~80% of useful fields, but the leasing-office email,
floor-plan-level fees, and a few other detail-page fields only appear when
we navigate directly to the listing URL. This module wraps that call.

Design choices worth noting:

- **No Celery.** This runs as a FastAPI `BackgroundTasks` after the request
  response is returned. It's an enhancement, not a correctness requirement
  — if the api container restarts mid-call we lose the run, the user clicks
  something else and it re-triggers. Trading Celery's durability for a
  drastically simpler ops surface.

- **7-day TTL on `apartments.last_enriched_at`.** Re-enriching the same
  listing within a week burns Apify credits for nearly-identical data.
  The window is intentionally generous — leasing offices don't change
  their email weekly.

- **Optimistic write of `last_enriched_at`.** We set the timestamp *before*
  the Apify call returns. If the call fails, we still don't re-try for 7
  days — preventing a dead listing from being hammered. The downside (we
  miss the data for that week) is acceptable for an enhancement feature.

- **Backfills the tour_pipeline row(s).** The tour-detail UI reads
  `tour.contact_email` (Supabase) rather than `apartment.contact_email`
  (Postgres), because the tour row is where the user can override contact
  info. When fresh enrichment data lands, we propagate it to any tour rows
  for that apartment whose contact fields are still null.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import select, update

from app.database import get_session_context, is_database_enabled
from app.models.apartment import ApartmentModel
from app.services.scrapers.apify_service import ApifyService

logger = logging.getLogger(__name__)

ENRICHMENT_TTL_DAYS = 7


async def enrich_apartment(apartment_id: str) -> Dict[str, Any]:
    """Hit Apify URL-mode for the given apartment and merge the result.

    Idempotent across rapid duplicate calls thanks to the TTL check. Safe to
    fire from `BackgroundTasks` — never raises; logs and returns a status
    dict instead. The status dict is mostly for tests and the admin
    debug endpoint; the BackgroundTasks invocation ignores it.
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "db_disabled"}

    # --- Phase 1: read the listing under a short session, no Apify call yet
    async with get_session_context() as session:
        result = await session.execute(
            select(ApartmentModel).where(ApartmentModel.id == apartment_id)
        )
        apt = result.scalar_one_or_none()
        if not apt:
            return {"status": "not_found", "apartment_id": apartment_id}

        if not apt.source_url:
            return {"status": "skipped", "reason": "no_source_url", "apartment_id": apartment_id}

        if apt.last_enriched_at:
            # last_enriched_at is timezone-aware; normalize to UTC for the diff
            last = apt.last_enriched_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - last
            if age < timedelta(days=ENRICHMENT_TTL_DAYS):
                return {
                    "status": "skipped",
                    "reason": "fresh",
                    "apartment_id": apartment_id,
                    "age_days": age.days,
                }

        # Capture what we need outside the session
        source_url = apt.source_url
        source = apt.source

    # --- Phase 2: long-running Apify URL-mode call (no DB session held)
    svc = ApifyService(source)
    try:
        listing = await svc.scrape_by_url(source_url)
    except Exception as e:
        logger.warning(f"Apify URL-mode call failed for {apartment_id}: {e}")
        listing = None
    finally:
        try:
            await svc.close()
        except Exception:
            pass

    # --- Phase 3: merge results back. Even on failure, stamp last_enriched_at
    #     so we don't pound a dead listing repeatedly within the TTL.
    now = datetime.now(timezone.utc)

    if not listing:
        async with get_session_context() as session:
            await session.execute(
                update(ApartmentModel)
                .where(ApartmentModel.id == apartment_id)
                .values(last_enriched_at=now)
            )
        return {"status": "no_data", "apartment_id": apartment_id}

    updates_made: Dict[str, Any] = {}
    fields_to_merge = (
        # Field name, "should overwrite if currently empty" semantics.
        # We never blow away non-null user-visible data with a null from
        # a re-scrape; only fill blanks.
        "contact_email",
        "contact_phone",
        "contact_name",
        "property_website",
        "walk_score",
        "transit_score",
        "apartments_com_rating",
        "specials",
        "available_units",
        "transit_options",
        "virtual_tour_urls",
    )

    async with get_session_context() as session:
        result = await session.execute(
            select(ApartmentModel).where(ApartmentModel.id == apartment_id)
        )
        apt = result.scalar_one_or_none()
        if not apt:
            return {"status": "not_found", "apartment_id": apartment_id}

        for field in fields_to_merge:
            current = getattr(apt, field, None)
            new = getattr(listing, field, None)
            if new in (None, "", [], {}):
                continue
            if current in (None, "", [], {}):
                setattr(apt, field, new)
                updates_made[field] = "filled"

        apt.last_enriched_at = now
        await session.commit()

    # --- Phase 4: backfill tour_pipeline rows that don't yet have contact info
    contact_email = listing.contact_email if "contact_email" in updates_made else None
    contact_phone = listing.contact_phone if "contact_phone" in updates_made else None
    if contact_email or contact_phone:
        try:
            from app.services.tier_service import supabase_admin

            if supabase_admin:
                tours = (
                    supabase_admin.table("tour_pipeline")
                    .select("id, contact_email, contact_phone")
                    .eq("apartment_id", apartment_id)
                    .execute()
                )
                for row in tours.data or []:
                    patch: Dict[str, Any] = {}
                    if contact_email and not row.get("contact_email"):
                        patch["contact_email"] = listing.contact_email
                    if contact_phone and not row.get("contact_phone"):
                        patch["contact_phone"] = listing.contact_phone
                    if patch:
                        supabase_admin.table("tour_pipeline").update(patch).eq("id", row["id"]).execute()
        except Exception as e:
            logger.warning(f"Could not backfill tour_pipeline contact info for {apartment_id}: {e}")

    logger.info(f"Enriched apartment {apartment_id}: filled {list(updates_made.keys()) or 'nothing'}")
    return {
        "status": "enriched",
        "apartment_id": apartment_id,
        "fields_updated": list(updates_made.keys()),
    }
