"""
Celery tasks for maintenance and cleanup operations.
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

from app.celery_app import celery_app
from app.database import get_session_context, is_database_enabled
from app.models.market_config import SEARCH_FLOOR
from app.tasks._async_runner import run_async

logger = logging.getLogger(__name__)

# Corpus-wide listing verification. Off by default — see the comment at the
# dispatch site in _decay_and_verify() for why.
BULK_VERIFICATION_ENABLED = os.getenv("ENABLE_BULK_VERIFICATION", "false").lower() == "true"

# Don't re-check the same listing more often than this.
VERIFICATION_COOLDOWN_HOURS = int(os.getenv("VERIFICATION_COOLDOWN_HOURS", "24"))


@celery_app.task
def cleanup_stale_listings(days_old: int = 30) -> Dict[str, Any]:
    """
    Mark listings not seen in X days as inactive.

    Args:
        days_old: Number of days since last seen

    Returns:
        Dict with cleanup results
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    logger.info(f"Cleaning up listings not seen in {days_old} days")

    async def _cleanup():
        from sqlalchemy import update
        from app.models.apartment import ApartmentModel

        cutoff = datetime.utcnow() - timedelta(days=days_old)

        async with get_session_context() as session:
            stmt = (
                update(ApartmentModel)
                .where(
                    ApartmentModel.last_seen_at < cutoff,
                    ApartmentModel.is_active == 1,
                )
                .values(is_active=0)
            )
            result = await session.execute(stmt)
            await session.commit()

            return result.rowcount

    try:
        count = run_async(_cleanup())
        logger.info(f"Marked {count} stale listings as inactive")
        return {
            "status": "completed",
            "deactivated_count": count,
            "cutoff_date": (datetime.utcnow() - timedelta(days=days_old)).isoformat(),
        }
    except Exception as e:
        logger.exception(f"Cleanup failed: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task
def update_listing_status() -> Dict[str, Any]:
    """
    Update listing status based on available dates.
    Mark listings with past available dates as potentially unavailable.

    Returns:
        Dict with update results
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    logger.info("Updating listing status based on dates")

    async def _update():
        from sqlalchemy import select
        from app.models.apartment import ApartmentModel

        today = datetime.utcnow().strftime("%Y-%m-%d")
        updated_count = 0

        async with get_session_context() as session:
            # Find active listings with past available dates
            # that haven't been seen recently
            cutoff = datetime.utcnow() - timedelta(days=7)

            stmt = select(ApartmentModel).where(
                ApartmentModel.is_active == 1,
                ApartmentModel.available_date < today,
                ApartmentModel.last_seen_at < cutoff,
            )
            result = await session.execute(stmt)

            for apt in result.scalars():
                apt.is_active = 0
                updated_count += 1

            await session.commit()

        return updated_count

    try:
        count = run_async(_update())
        logger.info(f"Updated status for {count} listings")
        return {
            "status": "completed",
            "updated_count": count,
        }
    except Exception as e:
        logger.exception(f"Status update failed: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task
def reset_rate_limits(period: str = "hour") -> Dict[str, Any]:
    """
    Reset rate limit counters for data sources.

    Args:
        period: "hour" or "day"

    Returns:
        Dict with reset results
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    logger.info(f"Resetting {period}ly rate limits")

    async def _reset():
        from sqlalchemy import update
        from app.models.data_source import DataSourceModel

        async with get_session_context() as session:
            now = datetime.utcnow()

            if period == "hour":
                stmt = (
                    update(DataSourceModel)
                    .values(
                        current_hour_calls=0,
                        rate_limit_reset_hour=now + timedelta(hours=1),
                    )
                )
            else:  # day
                stmt = (
                    update(DataSourceModel)
                    .values(
                        current_day_calls=0,
                        rate_limit_reset_day=now + timedelta(days=1),
                    )
                )

            result = await session.execute(stmt)
            await session.commit()

            return result.rowcount

    try:
        count = run_async(_reset())
        logger.info(f"Reset {period}ly rate limits for {count} sources")
        return {
            "status": "completed",
            "period": period,
            "sources_reset": count,
        }
    except Exception as e:
        logger.exception(f"Rate limit reset failed: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task
def vacuum_database() -> Dict[str, Any]:
    """
    Run database maintenance (vacuum/analyze).
    Should be run during low-traffic periods.

    Returns:
        Dict with vacuum results
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    logger.info("Running database vacuum")

    async def _vacuum():
        from sqlalchemy import text

        async with get_session_context() as session:
            # Run analyze on main tables
            await session.execute(text("ANALYZE apartments"))
            await session.execute(text("ANALYZE scrape_jobs"))
            await session.execute(text("ANALYZE data_sources"))
            await session.commit()

        return True

    try:
        run_async(_vacuum())
        logger.info("Database vacuum completed")
        return {"status": "completed"}
    except Exception as e:
        logger.exception(f"Vacuum failed: {e}")
        return {"status": "failed", "error": str(e)}


async def compute_metrics_snapshot() -> Dict[str, Any]:
    """Compute data-collection metrics in pure async form.

    Lives at module level (rather than nested inside the Celery task) so the
    FastAPI `/metrics` endpoint can `await` it directly. Going through the
    Celery task wrapper from a FastAPI handler used to fail silently because
    `run_async()` tried to spin a new event loop inside the request's running
    loop, and the endpoint's bare `except` swallowed the resulting
    RuntimeError and returned zeros.
    """
    from sqlalchemy import select, func
    from app.models.apartment import ApartmentModel
    from app.models.scrape_job import ScrapeJobModel

    metrics: Dict[str, Any] = {}

    async with get_session_context() as session:
        stmt = select(func.count(ApartmentModel.id))
        result = await session.execute(stmt)
        metrics["total_listings"] = result.scalar() or 0

        stmt = select(func.count(ApartmentModel.id)).where(
            ApartmentModel.is_active == 1
        )
        result = await session.execute(stmt)
        metrics["active_listings"] = result.scalar() or 0

        stmt = select(
            ApartmentModel.source,
            func.count(ApartmentModel.id)
        ).group_by(ApartmentModel.source)
        result = await session.execute(stmt)
        metrics["listings_by_source"] = {row[0]: row[1] for row in result}

        stmt = select(
            ApartmentModel.city,
            func.count(ApartmentModel.id)
        ).where(
            ApartmentModel.city.isnot(None)
        ).group_by(ApartmentModel.city).limit(20)
        result = await session.execute(stmt)
        metrics["listings_by_city"] = {row[0]: row[1] for row in result}

        stmt = select(func.avg(ApartmentModel.data_quality_score))
        result = await session.execute(stmt)
        metrics["avg_quality_score"] = round(result.scalar() or 0, 2)

        stmt = select(func.count(ScrapeJobModel.id)).where(
            ScrapeJobModel.created_at > datetime.utcnow() - timedelta(days=1)
        )
        result = await session.execute(stmt)
        metrics["jobs_last_24h"] = result.scalar() or 0

        stmt = select(func.count(ScrapeJobModel.id)).where(
            ScrapeJobModel.created_at > datetime.utcnow() - timedelta(days=1),
            ScrapeJobModel.status == "completed",
        )
        result = await session.execute(stmt)
        metrics["successful_jobs_last_24h"] = result.scalar() or 0

    metrics["timestamp"] = datetime.utcnow().isoformat()
    return metrics


@celery_app.task
def generate_metrics_snapshot() -> Dict[str, Any]:
    """Celery task wrapper around `compute_metrics_snapshot`."""
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    logger.info("Generating metrics snapshot")
    try:
        metrics = run_async(compute_metrics_snapshot())
        logger.info(f"Metrics snapshot: {metrics}")
        return {"status": "completed", "metrics": metrics}
    except Exception as e:
        logger.exception(f"Metrics generation failed: {e}")
        return {"status": "failed", "error": str(e)}


@celery_app.task
def decay_and_verify() -> Dict[str, Any]:
    """
    Hourly task: recalculate freshness confidence and trigger verification
    for listings that have decayed below threshold.
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    return run_async(_decay_and_verify())


async def _decay_and_verify() -> Dict[str, Any]:
    """Recompute freshness confidence for every active listing.

    Done as set-based SQL rather than an ORM loop. The previous version did
    `select(ApartmentModel).where(is_active == 1)` and iterated, which
    materialised every active listing as a full ORM object — including
    `raw_data` (the entire Apify payload) plus a dozen other JSONB columns. At
    3,240 listings that exceeded the worker's 512 MB and the task was SIGKILLed
    by the OOM killer on every run, so it never reached its commit. It had not
    succeeded since 2026-06-29.

    Nothing here needs Python. The computation is
    `100 - hours_since_last_seen * rate`, over columns already in the database,
    so it runs in constant memory as one statement — and stays that way as the
    corpus grows (raising maxItems to 1000 roughly triples it).
    """
    from sqlalchemy import text
    from app.models.market_config import TIER_DECAY_RATES, DEFAULT_DECAY_RATE

    rates = {
        "hot": TIER_DECAY_RATES["hot"],
        "std": TIER_DECAY_RATES["standard"],
        "cool": TIER_DECAY_RATES["cool"],
        "fallback": DEFAULT_DECAY_RATE,
        "floor": SEARCH_FLOOR,
    }

    async with get_session_context() as session:
        # The correlated subquery resolves each listing's tier; COALESCE covers
        # listings whose market_id is null or points at a deleted market, which
        # the ORM version handled by defaulting to "cool".
        decay_result = await session.execute(
            text("""
                UPDATE apartments a
                SET freshness_confidence = GREATEST(0, FLOOR(
                        100 - (EXTRACT(EPOCH FROM (now() - a.last_seen_at)) / 3600.0)
                              * COALESCE(
                                  CASE (SELECT m.tier FROM market_configs m
                                        WHERE m.id = a.market_id)
                                    WHEN 'hot' THEN :hot
                                    WHEN 'standard' THEN :std
                                    WHEN 'cool' THEN :cool
                                  END, :fallback)
                    ))::int
                WHERE a.is_active = 1
                  AND a.last_seen_at IS NOT NULL
            """),
            rates,
        )
        decayed = decay_result.rowcount or 0

        # Stamp only the rows whose value actually moved, so
        # max(confidence_updated_at) stays a truthful "when did decay last
        # succeed" signal for /pipeline-health.
        await session.execute(
            text("""
                UPDATE apartments
                SET confidence_updated_at = now()
                WHERE is_active = 1 AND last_seen_at IS NOT NULL
            """)
        )

        # Expire listings that have decayed to nothing. IS DISTINCT FROM rather
        # than <> because <> 'verified' is NULL for unverified rows, which would
        # silently exclude every one of them.
        deact_result = await session.execute(
            text("""
                UPDATE apartments
                SET is_active = 0
                WHERE is_active = 1
                  AND freshness_confidence = 0
                  AND verification_status IS DISTINCT FROM 'verified'
            """)
        )
        deactivated = deact_result.rowcount or 0

        await session.commit()

    verification_dispatched = 0
    if BULK_VERIFICATION_ENABLED:
        # Off by default — see the note on BULK_VERIFICATION_ENABLED. Selects
        # ids only, never whole rows, so this cannot reintroduce the OOM.
        async with get_session_context() as session:
            rows = await session.execute(
                text("""
                    SELECT id FROM apartments
                    WHERE is_active = 1
                      AND freshness_confidence < :floor
                      AND verification_status IS NULL
                    LIMIT 500
                """),
                {"floor": SEARCH_FLOOR},
            )
            ids = [r[0] for r in rows]
            if ids:
                await session.execute(
                    text("""
                        UPDATE apartments SET verification_status = 'pending'
                        WHERE id = ANY(:ids)
                    """),
                    {"ids": ids},
                )
                await session.commit()

        for apartment_id in ids:
            verify_listing.apply_async(
                kwargs={"apartment_id": apartment_id}, queue="maintenance"
            )
            verification_dispatched += 1

    logger.info(
        f"Decay update: {decayed} listings recomputed, "
        f"{verification_dispatched} verifications dispatched, "
        f"{deactivated} deactivated"
    )
    return {
        "status": "completed",
        "listings_recomputed": decayed,
        "verifications_dispatched": verification_dispatched,
        "deactivated": deactivated,
    }


@celery_app.task
def verify_listing(apartment_id: str) -> Dict[str, Any]:
    """
    Verify if a listing is still active by checking its source URL.
    """
    if not is_database_enabled():
        return {"status": "skipped"}

    return run_async(_verify_listing(apartment_id))


async def _verify_listing(apartment_id: str) -> Dict[str, Any]:
    """Check whether a listing is still live at its source URL.

    Three outcomes, and the distinction matters:

      gone     — the source says so (404, or a removal notice in a 200 body)
      verified — the source served us the live page
      unknown  — we could not tell (403, 429, 5xx, timeout, redirect to a
                 search page). This is the common case for apartments.com,
                 which is Akamai-fenced and blocks automated requests.

    The previous version had only two outcomes, and anything that wasn't a 404
    or a 200-with-removal-text counted as "verified". Since apartments.com 403s
    us, that meant every listing was certified alive *because* we were blocked —
    and because the deactivation guard skips anything marked "verified", those
    rows then became permanently immune to expiry. An unknown must stay unknown.
    """
    import httpx
    from sqlalchemy import select, update
    from app.models.apartment import ApartmentModel

    async with get_session_context() as session:
        result = await session.execute(
            select(ApartmentModel).where(ApartmentModel.id == apartment_id)
        )
        apt = result.scalar_one_or_none()
        if not apt or not apt.source_url:
            return {"status": "skipped", "reason": "no source_url"}

        # Cooldown: a listing that was checked recently doesn't need checking
        # again, whatever the answer was.
        if apt.verified_at:
            age_hours = (datetime.utcnow() - apt.verified_at.replace(tzinfo=None)).total_seconds() / 3600
            if age_hours < VERIFICATION_COOLDOWN_HOURS:
                return {"status": "skipped", "reason": "cooldown", "apartment_id": apartment_id}

        source_url = apt.source_url

    gone_indicators = [
        "no longer available",
        "this listing has been removed",
        "listing not found",
        "page not found",
    ]

    outcome = "unknown"
    detail = ""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(source_url)

        if response.status_code == 404:
            outcome = "gone"
            detail = "404"
        elif response.status_code == 200:
            body = response.text.lower()
            if any(indicator in body for indicator in gone_indicators):
                outcome = "gone"
                detail = "removal notice in body"
            else:
                outcome = "verified"
                detail = "200"
        else:
            # 403 (Akamai), 429, 5xx — we learned nothing about the listing.
            outcome = "unknown"
            detail = f"HTTP {response.status_code}"
    except Exception as e:
        outcome = "unknown"
        detail = f"{type(e).__name__}: {e}"

    now = datetime.utcnow()
    if outcome == "unknown":
        # Record only that we looked, so the cooldown applies and we don't
        # hammer a host that is refusing us. Deliberately does NOT touch
        # verification_status or freshness_confidence — an unanswered question
        # must not change the listing's standing in either direction.
        logger.info(f"Verification inconclusive for {apartment_id} ({detail})")
        async with get_session_context() as session:
            await session.execute(
                update(ApartmentModel)
                .where(ApartmentModel.id == apartment_id)
                .values(verified_at=now)
            )
            await session.commit()
        return {"status": "unknown", "apartment_id": apartment_id, "detail": detail}

    async with get_session_context() as session:
        if outcome == "gone":
            await session.execute(
                update(ApartmentModel)
                .where(ApartmentModel.id == apartment_id)
                .values(verification_status="gone", verified_at=now, is_active=0)
            )
        else:
            await session.execute(
                update(ApartmentModel)
                .where(ApartmentModel.id == apartment_id)
                .values(verification_status="verified", verified_at=now, freshness_confidence=80)
            )
        await session.commit()

    return {"status": outcome, "apartment_id": apartment_id, "detail": detail}


@celery_app.task
def cleanup_maintenance() -> Dict[str, Any]:
    """
    Daily maintenance: deactivate dead listings, reset circuit breakers,
    detect stale jobs, reset rate limits.
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    return run_async(_cleanup_maintenance())


async def _cleanup_maintenance() -> Dict[str, Any]:
    from sqlalchemy import update
    from app.models.apartment import ApartmentModel
    from app.models.market_config import MarketConfigModel
    from app.models.scrape_job import ScrapeJobModel

    now = datetime.utcnow()
    results = {}

    async with get_session_context() as session:
        # 1. Deactivate listings with confidence=0 and not verified
        stmt = (
            update(ApartmentModel)
            .where(
                ApartmentModel.freshness_confidence == 0,
                ApartmentModel.is_active == 1,
                ApartmentModel.verification_status != "verified",
            )
            .values(is_active=0)
        )
        result = await session.execute(stmt)
        results["deactivated"] = result.rowcount

        # 2. Reset circuit breakers (consecutive_failures -> 0)
        stmt = (
            update(MarketConfigModel)
            .where(MarketConfigModel.consecutive_failures > 0)
            .values(consecutive_failures=0)
        )
        result = await session.execute(stmt)
        results["circuit_breakers_reset"] = result.rowcount

        # 3. Detect stale jobs (running > 30 min)
        stale_cutoff = now - timedelta(minutes=30)
        stmt = (
            update(ScrapeJobModel)
            .where(
                ScrapeJobModel.status == "running",
                ScrapeJobModel.started_at < stale_cutoff,
            )
            .values(status="failed", completed_at=now)
        )
        result = await session.execute(stmt)
        results["stale_jobs_failed"] = result.rowcount

        await session.commit()

    # 4. Reset daily rate limits (reuse existing task logic)
    reset_result = reset_rate_limits(period="day")
    results["rate_limits_reset"] = reset_result

    logger.info(f"Daily maintenance: {results}")
    return {"status": "completed", **results}


@celery_app.task(bind=True, max_retries=2, soft_time_limit=1800)
def backfill_enrichment(self, batch_size: int = 200, only_missing: bool = True) -> Dict[str, Any]:
    """Backfill the enrichment columns from existing apartments.raw_data.

    Reads raw_data for apartments whose enrichment fields are still NULL and
    populates them in place. Idempotent: re-running only touches rows that
    still have null values when ``only_missing`` is True.
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    return run_async(_backfill_enrichment(batch_size=batch_size, only_missing=only_missing))


async def _backfill_enrichment(batch_size: int, only_missing: bool) -> Dict[str, Any]:
    from sqlalchemy import select, or_
    from app.models.apartment import ApartmentModel

    updated = 0
    scanned = 0
    skipped_no_raw = 0
    last_id: str = ""

    while True:
        async with get_session_context() as session:
            stmt = select(ApartmentModel).where(
                ApartmentModel.is_active == 1,
                ApartmentModel.raw_data.isnot(None),
            )
            if only_missing:
                # Only rows where every enrichment column is still null
                stmt = stmt.where(
                    ApartmentModel.specials.is_(None),
                    ApartmentModel.walk_score.is_(None),
                    ApartmentModel.transit_score.is_(None),
                    ApartmentModel.apartments_com_rating.is_(None),
                    ApartmentModel.available_units.is_(None),
                    ApartmentModel.transit_options.is_(None),
                    ApartmentModel.virtual_tour_urls.is_(None),
                    ApartmentModel.contact_name.is_(None),
                    ApartmentModel.property_website.is_(None),
                )
            if last_id:
                stmt = stmt.where(ApartmentModel.id > last_id)
            stmt = stmt.order_by(ApartmentModel.id).limit(batch_size)

            rows = (await session.execute(stmt)).scalars().all()
            if not rows:
                break

            for apt in rows:
                scanned += 1
                raw = apt.raw_data or {}
                if not isinstance(raw, dict):
                    skipped_no_raw += 1
                    last_id = apt.id
                    continue

                contact = raw.get("contact") or {}
                score = raw.get("score") or {}
                rentals = raw.get("rentals")
                transit = raw.get("transportation")
                vt = raw.get("virtualTours")
                specials_raw = raw.get("specials")

                touched = False

                if apt.contact_name is None and isinstance(contact, dict) and contact.get("name"):
                    apt.contact_name = contact.get("name")
                    touched = True
                if apt.walk_score is None and isinstance(score, dict) and isinstance(score.get("walkScore"), (int, float)):
                    apt.walk_score = int(score["walkScore"])
                    touched = True
                if apt.transit_score is None and isinstance(score, dict) and isinstance(score.get("transitScore"), (int, float)):
                    apt.transit_score = int(score["transitScore"])
                    touched = True
                if apt.apartments_com_rating is None and isinstance(raw.get("rating"), (int, float)):
                    apt.apartments_com_rating = float(raw["rating"])
                    touched = True
                if apt.property_website is None and raw.get("propertyWebsite"):
                    apt.property_website = raw.get("propertyWebsite")
                    touched = True
                if apt.specials is None and isinstance(specials_raw, dict) and specials_raw:
                    apt.specials = specials_raw
                    touched = True
                if apt.available_units is None and isinstance(rentals, list) and rentals:
                    apt.available_units = rentals
                    touched = True
                if apt.transit_options is None and isinstance(transit, list) and transit:
                    apt.transit_options = transit
                    touched = True
                if apt.virtual_tour_urls is None and isinstance(vt, list):
                    cleaned = [u for u in vt if isinstance(u, str)]
                    if cleaned:
                        apt.virtual_tour_urls = cleaned
                        touched = True

                if touched:
                    updated += 1
                last_id = apt.id

            await session.commit()

    logger.info(
        f"backfill_enrichment: scanned={scanned} updated={updated} skipped_no_raw={skipped_no_raw}"
    )
    return {
        "status": "completed",
        "scanned": scanned,
        "updated": updated,
        "skipped_no_raw": skipped_no_raw,
    }


@celery_app.task(bind=True, max_retries=2, soft_time_limit=1800)
def backfill_extended_fields(self, batch_size: int = 200, only_missing: bool = True) -> Dict[str, Any]:
    """Backfill nearby_schools + floor_plans from existing apartments.raw_data.

    Mirrors backfill_enrichment but for the columns added in migration
    m9i0j1k2l3m4 (task #27). Pure-backend extraction — no Apify cost.
    Idempotent when ``only_missing`` is True (the default).
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    return run_async(_backfill_extended_fields(batch_size=batch_size, only_missing=only_missing))


async def _backfill_extended_fields(batch_size: int, only_missing: bool) -> Dict[str, Any]:
    from sqlalchemy import select
    from app.models.apartment import ApartmentModel

    updated = 0
    scanned = 0
    skipped_no_raw = 0
    last_id: str = ""

    while True:
        async with get_session_context() as session:
            stmt = select(ApartmentModel).where(
                ApartmentModel.is_active == 1,
                ApartmentModel.raw_data.isnot(None),
            )
            if only_missing:
                stmt = stmt.where(
                    ApartmentModel.nearby_schools.is_(None),
                    ApartmentModel.floor_plans.is_(None),
                )
            if last_id:
                stmt = stmt.where(ApartmentModel.id > last_id)
            stmt = stmt.order_by(ApartmentModel.id).limit(batch_size)

            rows = (await session.execute(stmt)).scalars().all()
            if not rows:
                break

            for apt in rows:
                scanned += 1
                raw = apt.raw_data or {}
                if not isinstance(raw, dict):
                    skipped_no_raw += 1
                    last_id = apt.id
                    continue

                touched = False

                # Nearby schools (object: {public, private})
                if apt.nearby_schools is None:
                    schools_raw = raw.get("schools")
                    if isinstance(schools_raw, dict) and (
                        schools_raw.get("public") or schools_raw.get("private")
                    ):
                        apt.nearby_schools = schools_raw
                        touched = True

                # Floor plans (array, sourced from raw.models)
                if apt.floor_plans is None:
                    models_raw = raw.get("models")
                    if isinstance(models_raw, list) and models_raw:
                        apt.floor_plans = models_raw
                        touched = True

                if touched:
                    updated += 1
                last_id = apt.id

            await session.commit()

    logger.info(
        f"backfill_extended_fields: scanned={scanned} updated={updated} skipped_no_raw={skipped_no_raw}"
    )
    return {
        "status": "completed",
        "scanned": scanned,
        "updated": updated,
        "skipped_no_raw": skipped_no_raw,
    }


# NYC covers these zip prefixes (5 boroughs). Mirrors the constant in
# apify_service.py; duplicated here so the backfill is self-contained
# and doesn't pull in the scraper module.
_NYC_ZIP_PREFIXES = ("100", "101", "102", "103", "104",
                     "110", "111", "112", "113", "114")


@celery_app.task(bind=True, max_retries=2, soft_time_limit=600)
def backfill_nyc_city_normalization(self) -> Dict[str, Any]:
    """One-shot fix for the borough city-name issue.

    apartments.com tags NYC listings with 14+ distinct city values
    (Brooklyn, Bronx, Astoria, Long Island City, Jamaica, Flushing, ...)
    — only "New York" matches the search filter, so ~half of NYC was
    invisible to users searching the city. The scraper now normalizes
    on write (apify_service.py); this task fixes existing rows.

    Logic: for every active listing with state=NY and zip prefix in
    the NYC set AND city != "New York", move the current city into
    `neighborhood` (if neighborhood is empty) and set city="New York".
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    return run_async(_backfill_nyc_city_normalization())


async def _backfill_nyc_city_normalization() -> Dict[str, Any]:
    from sqlalchemy import select, func
    from app.models.apartment import ApartmentModel

    updated = 0
    scanned = 0
    sample_moves: List[Dict[str, str]] = []  # first few for the response

    async with get_session_context() as session:
        stmt = select(ApartmentModel).where(
            ApartmentModel.is_active == 1,
            ApartmentModel.state == "NY",
            ApartmentModel.zip_code.isnot(None),
            func.lower(ApartmentModel.city) != "new york",
        )
        result = await session.execute(stmt)

        for apt in result.scalars():
            scanned += 1
            zp = (apt.zip_code or "")[:3]
            if zp not in _NYC_ZIP_PREFIXES:
                continue
            original_city = apt.city
            if not apt.neighborhood:
                apt.neighborhood = original_city
            apt.city = "New York"
            if len(sample_moves) < 10:
                sample_moves.append({
                    "id": apt.id,
                    "zip": apt.zip_code,
                    "was_city": original_city,
                    "now_neighborhood": apt.neighborhood,
                })
            updated += 1

        await session.commit()

    logger.info(
        f"backfill_nyc_city_normalization: scanned={scanned} updated={updated}"
    )
    return {
        "status": "completed",
        "scanned": scanned,
        "updated": updated,
        "sample_moves": sample_moves,
    }


@celery_app.task
def backfill_boston_city_normalization() -> Dict[str, Any]:
    """Fold Boston neighbourhood names into "Boston" on existing rows.

    Same problem as the NYC borough issue, different solution. NYC is separable
    by zip prefix; Boston is not, because 021xx also covers Brookline,
    Cambridge and Somerville — genuinely different cities with different rents.
    So this keys on the neighbourhood name instead (see
    _BOSTON_NEIGHBORHOODS in apify_service.py, which also handles it on write).

    A measured Boston sweep (700 properties, 2026-09-25) was labelled with 27
    distinct cities, only 63% of them "Boston". Folding these names in raises
    that to ~75%; the remainder really are other municipalities. Without this,
    comps keyed on `city` compute a separate median for Allston as though it
    were a different market from Boston.

    Set-based rather than an ORM loop, deliberately: the decay task was being
    OOM-killed for exactly that pattern.
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    return run_async(_backfill_boston_city_normalization())


async def _backfill_boston_city_normalization() -> Dict[str, Any]:
    from sqlalchemy import text
    from app.services.scrapers.apify_service import _BOSTON_NEIGHBORHOODS

    names = sorted(_BOSTON_NEIGHBORHOODS)

    async with get_session_context() as session:
        # Preserve the neighbourhood name rather than discarding it, so cards
        # still read "Allston, MA" while comps group under Boston.
        result = await session.execute(
            text("""
                UPDATE apartments
                SET neighborhood = COALESCE(NULLIF(neighborhood, ''), city),
                    city = 'Boston'
                WHERE state = 'MA'
                  AND lower(btrim(city)) = ANY(:names)
            """),
            {"names": names},
        )
        updated = result.rowcount or 0
        await session.commit()

    logger.info(f"backfill_boston_city_normalization: updated={updated}")
    return {"status": "completed", "updated": updated, "names_matched": len(names)}


@celery_app.task(bind=True, max_retries=2, soft_time_limit=1800)
def backfill_floorplans(self, batch_size: int = 200, only_missing: bool = True) -> Dict[str, Any]:
    """Populate apartment_floorplans buckets from apartments.floor_plans.

    Phase 1 of docs/floorplan-search-design.md. apartments.com stores one row
    per building with the bedroom range collapsed to its low end, hiding larger
    units from ``bedrooms == N`` search. This parses the ``floor_plans`` (models)
    JSONB the scrape already captured into per-(bedrooms, bathrooms) buckets — no
    Apify cost, no re-scrape.

    Idempotent: rebuilds each building's buckets wholesale (delete + reinsert).
    With ``only_missing`` (default) it skips buildings that already have buckets,
    so re-runs are cheap; pass ``only_missing=False`` to rebuild everything.
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    return run_async(_backfill_floorplans(batch_size=batch_size, only_missing=only_missing))


async def _backfill_floorplans(batch_size: int, only_missing: bool) -> Dict[str, Any]:
    import re
    import uuid

    from sqlalchemy import select, delete, exists
    from app.models.apartment import ApartmentModel
    from app.models.apartment_floorplan import ApartmentFloorplanModel
    from app.services.floorplans import build_floorplan_buckets

    _DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    scanned = 0
    buildings_with_buckets = 0
    buckets_created = 0
    last_id = ""

    while True:
        async with get_session_context() as session:
            stmt = select(ApartmentModel).where(ApartmentModel.is_active == 1)
            if only_missing:
                stmt = stmt.where(
                    ~exists().where(ApartmentFloorplanModel.apartment_id == ApartmentModel.id)
                )
            if last_id:
                stmt = stmt.where(ApartmentModel.id > last_id)
            stmt = stmt.order_by(ApartmentModel.id).limit(batch_size)

            rows = (await session.execute(stmt)).scalars().all()
            if not rows:
                break

            for apt in rows:
                scanned += 1
                last_id = apt.id

                # Only carry a real date forward; building-level "Now"/"Unavailable"
                # tokens aren't dates.
                fallback_date = (
                    apt.available_date
                    if (apt.available_date and _DATE_RE.match(apt.available_date))
                    else None
                )

                buckets = build_floorplan_buckets(
                    apt.floor_plans,
                    apt.available_units,
                    fallback_bedrooms=apt.bedrooms,
                    fallback_bathrooms=apt.bathrooms,
                    fallback_rent=apt.rent,
                    fallback_sqft=apt.sqft,
                    fallback_available_date=fallback_date,
                    description=apt.description,
                    city=apt.city,
                )

                # Idempotent rebuild: clear this building's existing buckets first.
                await session.execute(
                    delete(ApartmentFloorplanModel).where(
                        ApartmentFloorplanModel.apartment_id == apt.id
                    )
                )
                for b in buckets:
                    session.add(
                        ApartmentFloorplanModel(
                            id=uuid.uuid4().hex,
                            apartment_id=apt.id,
                            bedrooms=b["bedrooms"],
                            bathrooms=b["bathrooms"],
                            min_rent=b["min_rent"],
                            max_rent=b["max_rent"],
                            min_sqft=b["min_sqft"],
                            max_sqft=b["max_sqft"],
                            available_units=b["available_units"],
                            earliest_available_date=b["earliest_available_date"],
                            model_ids=b["model_ids"],
                            pricing_model=b.get("pricing_model"),
                        )
                    )
                    buckets_created += 1
                if buckets:
                    buildings_with_buckets += 1

            await session.commit()

    logger.info(
        f"backfill_floorplans: scanned={scanned} "
        f"buildings_with_buckets={buildings_with_buckets} buckets_created={buckets_created}"
    )
    return {
        "status": "completed",
        "scanned": scanned,
        "buildings_with_buckets": buildings_with_buckets,
        "buckets_created": buckets_created,
    }
