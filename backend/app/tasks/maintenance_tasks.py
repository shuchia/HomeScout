"""
Celery tasks for maintenance and cleanup operations.
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

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
    from sqlalchemy import select, func, or_
    from sqlalchemy.dialects.postgresql import JSONB
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

        # Floorplan buckets — the index floorplan-aware search actually joins
        # against. Nothing reported on it before, so the only way to answer
        # "how many buckets are indexed" was an ad-hoc task against the
        # database. A building with no buckets is invisible to that search when
        # USE_FLOORPLAN_SEARCH is on, which makes `active_without_buckets` the
        # number worth watching: it is coverage debt, not a curiosity.
        from app.models.apartment_floorplan import ApartmentFloorplanModel

        buckets_total = (
            await session.execute(select(func.count(ApartmentFloorplanModel.id)))
        ).scalar() or 0

        active_join = (
            select(func.count(ApartmentFloorplanModel.id))
            .select_from(ApartmentFloorplanModel)
            .join(ApartmentModel, ApartmentModel.id == ApartmentFloorplanModel.apartment_id)
            .where(ApartmentModel.is_active == 1)
        )
        buckets_active = (await session.execute(active_join)).scalar() or 0

        buildings_with_buckets = (
            await session.execute(
                select(func.count(func.distinct(ApartmentFloorplanModel.apartment_id)))
                .select_from(ApartmentFloorplanModel)
                .join(ApartmentModel, ApartmentModel.id == ApartmentFloorplanModel.apartment_id)
                .where(ApartmentModel.is_active == 1)
            )
        ).scalar() or 0

        unpriced = (
            await session.execute(
                select(func.count(ApartmentFloorplanModel.id)).where(
                    ApartmentFloorplanModel.min_rent.is_(None)
                )
            )
        ).scalar() or 0

        metrics["floorplans"] = {
            "buckets_total": buckets_total,
            "buckets_on_active_listings": buckets_active,
            "active_buildings_with_buckets": buildings_with_buckets,
            "active_buildings_without_buckets": max(
                0, (metrics.get("active_listings") or 0) - buildings_with_buckets
            ),
            "buckets_price_on_request": unpriced,
        }

        # --- Ingestion invariants -------------------------------------------
        #
        # Every pipeline fault found in 2026 produced output that *looked like
        # data*: an Akamai 403 read as "verified", a payload field that moved
        # read as "price on request", availability gated on a key that
        # single-unit listings never carry read as "date unknown", a 100-row
        # config cap read as "this market only has 100 listings". None raised,
        # and /health stayed green through all of them.
        #
        # These ratios are the cheapest thing that would have caught four of
        # the nine. They are not thresholds — the absolute values differ
        # legitimately between markets. What matters is a *step change*.
        #
        # Computed PER CITY as well as overall, because a global ratio cannot
        # survive the corpus growing. Adding a market with a different
        # character (more by-the-room listings, more price-on-request) shifts
        # every global ratio at once, which both raises a false alarm and
        # masks a real regression somewhere else. Per-city baselines are
        # independent: a new city simply has none until it is blessed, and the
        # existing ones keep working untouched.
        def _pct(n: int, d: int) -> float:
            return round(100.0 * n / d, 2) if d else 0.0

        no_date_cond = or_(
            ApartmentModel.available_date.is_(None),
            ApartmentModel.available_date == "",
        )
        no_models_cond = or_(
            ApartmentModel.floor_plans.is_(None),
            func.jsonb_array_length(func.cast(ApartmentModel.floor_plans, JSONB)) == 0,
        )
        no_rent_cond = or_(ApartmentModel.rent.is_(None), ApartmentModel.rent <= 1)
        # Per-person share. Watched because getting this wrong is silent and
        # always flattering: one room's rent published as a whole unit's, which
        # the heuristic then ranks to the top. 5 Linden St shipped as a 4-bed
        # Allston house for $1,130. A detector that loses a signal shows up
        # here as the share collapsing; one that over-fires shows it spiking.
        per_person_cond = ApartmentModel.pricing_model == "per_person"

        per_city_rows = (
            await session.execute(
                select(
                    ApartmentModel.city,
                    func.count(ApartmentModel.id),
                    func.count(func.nullif(no_date_cond, False)),
                    func.count(func.nullif(no_models_cond, False)),
                    func.count(func.nullif(no_rent_cond, False)),
                    func.count(func.nullif(per_person_cond, False)),
                )
                .where(ApartmentModel.is_active == 1, ApartmentModel.city.isnot(None))
                .group_by(ApartmentModel.city)
            )
        ).all()

        bucket_rows = (
            await session.execute(
                select(
                    ApartmentModel.city,
                    func.count(ApartmentFloorplanModel.id),
                    func.count(
                        func.nullif(ApartmentFloorplanModel.min_rent.is_(None), False)
                    ),
                )
                .select_from(ApartmentFloorplanModel)
                .join(
                    ApartmentModel,
                    ApartmentModel.id == ApartmentFloorplanModel.apartment_id,
                )
                .where(ApartmentModel.is_active == 1, ApartmentModel.city.isnot(None))
                .group_by(ApartmentModel.city)
            )
        ).all()
        buckets_by_city = {r[0]: (r[1], r[2]) for r in bucket_rows}

        by_city: Dict[str, Any] = {}
        tot_date = tot_models = tot_rent = tot_pp = 0
        for city, n, nd, nm, nr, npp in per_city_rows:
            tot_date += nd
            tot_models += nm
            tot_rent += nr
            tot_pp += npp
            b_total, b_unpriced = buckets_by_city.get(city, (0, 0))
            by_city[city] = {
                "active_listings": n,
                "pct_buckets_price_on_request": _pct(b_unpriced, b_total),
                "pct_listings_without_available_date": _pct(nd, n),
                "pct_listings_without_floorplans": _pct(nm, n),
                "pct_listings_without_rent": _pct(nr, n),
                "pct_listings_per_person": _pct(npp, n),
            }

        metrics["invariants"] = {
            "overall": {
                "active_listings": active,
                "pct_buckets_price_on_request": _pct(unpriced, buckets_total),
                "pct_listings_without_available_date": _pct(tot_date, active),
                "pct_listings_without_floorplans": _pct(tot_models, active),
                "pct_listings_without_rent": _pct(tot_rent, active),
                "pct_listings_per_person": _pct(tot_pp, active),
                "buildings_without_buckets": metrics["floorplans"][
                    "active_buildings_without_buckets"
                ],
            },
            "by_city": by_city,
        }

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

    # Every bound parameter is CAST explicitly. Postgres cannot infer a type
    # for a placeholder inside a CASE arm, so asyncpg binds it as text and the
    # statement dies with 'operator does not exist: numeric * text'.
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
                        100.0 - (EXTRACT(EPOCH FROM (now() - a.last_seen_at))::double precision / 3600.0)
                              * COALESCE(
                                  CASE (SELECT m.tier FROM market_configs m
                                        WHERE m.id = a.market_id)
                                    WHEN 'hot' THEN CAST(:hot AS double precision)
                                    WHEN 'standard' THEN CAST(:std AS double precision)
                                    WHEN 'cool' THEN CAST(:cool AS double precision)
                                  END, CAST(:fallback AS double precision))
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
                      AND freshness_confidence < CAST(:floor AS integer)
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
                    source_url=apt.source_url,
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


@celery_app.task(bind=True, max_retries=2, soft_time_limit=1800)
def backfill_available_dates(self, batch_size: int = 500, apply: bool = False) -> Dict[str, Any]:
    """Recover availability dates already held in ``available_units``.

    The scrape stored the rentals array verbatim, but the extraction in
    ``apify_service`` was gated on ``models`` being non-empty. Single-unit and
    by-the-room listings publish no models and key their rentals by ``key``
    rather than ``modelId``, so their dates were dropped on the floor — 9
    Hancock St held ``availableDate: 2026-11-01`` while the card said
    availability could not be found.

    Measured on QA 2026-10-03: 65% of listings carry no models and 86% of those
    have a date in rentals, ~56% of the corpus. The bulk list endpoint
    independently counted 56.1% of rows with an empty ``available_date``.

    Reads from Postgres only — no Apify cost. Dry run by default; pass
    ``apply=True`` to write. Only fills rows whose ``available_date`` is empty,
    so a real date already present is never overwritten.
    """
    from app.tasks._async_runner import run_async

    return run_async(_backfill_available_dates(batch_size=batch_size, apply=apply))


async def _backfill_available_dates(batch_size: int, apply: bool) -> Dict[str, Any]:
    from sqlalchemy import select, or_
    from app.models.apartment import ApartmentModel
    from app.services.floorplans import earliest_rental_date

    scanned = 0
    recoverable = 0
    updated = 0
    no_date_available = 0
    samples: List[Dict[str, Any]] = []
    last_id = ""

    while True:
        async with get_session_context() as session:
            stmt = (
                select(ApartmentModel)
                .where(
                    ApartmentModel.is_active == 1,
                    or_(
                        ApartmentModel.available_date.is_(None),
                        ApartmentModel.available_date == "",
                    ),
                )
                .order_by(ApartmentModel.id)
                .limit(batch_size)
            )
            if last_id:
                stmt = stmt.where(ApartmentModel.id > last_id)

            rows = (await session.execute(stmt)).scalars().all()
            if not rows:
                break

            for apt in rows:
                scanned += 1
                last_id = apt.id

                found = earliest_rental_date(apt.available_units)
                if not found:
                    no_date_available += 1
                    continue

                recoverable += 1
                if len(samples) < 10:
                    samples.append(
                        {"id": apt.id, "address": apt.address, "available_date": found}
                    )
                if apply:
                    apt.available_date = found
                    updated += 1

            if apply:
                await session.commit()

    logger.info(
        f"backfill_available_dates: scanned={scanned} recoverable={recoverable} "
        f"updated={updated} apply={apply}"
    )
    return {
        "status": "completed",
        "apply": apply,
        "scanned": scanned,
        "recoverable": recoverable,
        "updated": updated,
        "no_date_in_payload": no_date_available,
        "samples": samples,
    }


@celery_app.task(bind=True, max_retries=2, soft_time_limit=1800)
def merge_duplicate_properties(self, apply: bool = False) -> Dict[str, Any]:
    """Collapse rows that are repeat captures of one source listing.

    The content hash and the fuzzy matcher both key on rent, so a property
    whose advertised price moved far enough was inserted again. Measured on QA
    2026-10-03: 583 of 3,737 rows (15.6%), every market between 12.7% and 26%,
    accumulating over a median 50 days. Ingestion now dedupes on the source id
    (see deduplicator.source_key), which stops new ones; this clears the
    backlog.

    Losers are **deactivated, not deleted**. `saved_listings.apartment_id`
    lives in Supabase and references these ids across a database boundary, so
    no transaction can repoint it — deleting would orphan every favourite and
    tour pointing at a merged row. is_active = 0 takes them out of search
    (which is the whole point) while leaving the id resolvable, and is
    reversible if a merge turns out to be wrong.

    The survivor is the row search would have shown anyway: freshest, then
    most-seen, then oldest. It inherits the group's earliest first_seen_at and
    the sum of times_seen, so the longitudinal signal survives the merge.

    Dry run by default.
    """
    from app.tasks._async_runner import run_async

    return run_async(_merge_duplicate_properties(apply=apply))


async def _merge_duplicate_properties(apply: bool) -> Dict[str, Any]:
    from collections import defaultdict
    from sqlalchemy import select, update
    from app.models.apartment import ApartmentModel
    from app.services.deduplication.deduplicator import source_key

    # Columns only. Selecting whole ApartmentModel entities pulls floor_plans,
    # available_units, images, amenities and description — JSONB blobs running
    # to tens of KB each — and 4,312 of them OOM-kills the 512MB worker. That
    # is the same SIGKILL that took out the old decay task; the fix is the same
    # one _backfill_floorplans already uses.
    cols = (
        ApartmentModel.id,
        ApartmentModel.source,
        ApartmentModel.external_id,
        ApartmentModel.source_url,
        ApartmentModel.address,
        ApartmentModel.rent,
        ApartmentModel.freshness_confidence,
        ApartmentModel.times_seen,
        ApartmentModel.first_seen_at,
    )

    groups: Dict[str, List[Any]] = defaultdict(list)
    scanned = 0

    async with get_session_context() as session:
        result = await session.stream(
            select(*cols).where(ApartmentModel.is_active == 1)
        )
        async for row in result:
            scanned += 1
            key = source_key(
                {
                    "source": row.source,
                    "external_id": row.external_id,
                    "source_url": row.source_url,
                }
            )
            if key:
                groups[key].append(row)

    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}

    deactivated = 0
    samples: List[Dict[str, Any]] = []
    plan: List[Dict[str, Any]] = []

    for key, members in dup_groups.items():
        members.sort(
            key=lambda r: (
                -(r.freshness_confidence or 0),
                -(r.times_seen or 0),
                r.first_seen_at or datetime.max,
            )
        )
        survivor, losers = members[0], members[1:]

        seen_dates = [r.first_seen_at for r in members if r.first_seen_at]
        earliest = min(seen_dates) if seen_dates else survivor.first_seen_at
        total_seen = sum((r.times_seen or 0) for r in members)

        plan.append({
            "survivor_id": survivor.id,
            "loser_ids": [r.id for r in losers],
            "first_seen_at": earliest,
            "times_seen": total_seen,
        })
        if len(samples) < 10:
            samples.append({
                "source_key": key,
                "address": survivor.address,
                "survivor": survivor.id,
                "survivor_rent": survivor.rent,
                "deactivating": [r.id for r in losers],
                "rents": [r.rent for r in members],
                "freshness": [r.freshness_confidence for r in members],
                "times_seen_total": total_seen,
            })
        deactivated += len(losers)

    if apply:
        # Targeted UPDATEs in batches, so nothing is held in memory and a
        # failure part-way leaves a consistent subset rather than a half-merged
        # group.
        async with get_session_context() as session:
            for entry in plan:
                await session.execute(
                    update(ApartmentModel)
                    .where(ApartmentModel.id == entry["survivor_id"])
                    .values(
                        first_seen_at=entry["first_seen_at"],
                        times_seen=entry["times_seen"],
                    )
                )
                await session.execute(
                    update(ApartmentModel)
                    .where(ApartmentModel.id.in_(entry["loser_ids"]))
                    .values(is_active=0)
                )
            await session.commit()

    logger.info(
        f"merge_duplicate_properties: scanned={scanned} groups={len(dup_groups)} "
        f"deactivated={deactivated} apply={apply}"
    )
    return {
        "status": "completed",
        "apply": apply,
        "active_rows_scanned": scanned,
        "duplicate_groups": len(dup_groups),
        "rows_deactivated": deactivated,
        "samples": samples,
    }


@celery_app.task(bind=True, max_retries=1, soft_time_limit=3600)
def corpus_audit(self, sample_size: int = 40, city: Optional[str] = None) -> Dict[str, Any]:
    """Check a random sample of the corpus against its source.

    This is the answer to "does the corpus look right", and it is deliberately
    not a human comparing cards to apartments.com by hand. That does not scale
    past a handful of listings, is not repeatable, and cannot be run again
    after a parser change to prove the fix held.

    Each sampled listing is re-fetched through the same `scrape_url()` the
    saved-listing check uses — Apify's infrastructure, so no Akamai problem —
    normalized through the same normalizer, and diffed on the fields that
    matter. ~$0.0005 per listing: a 40-listing audit costs about two cents and
    a 200-listing one about ten.

    What it reports is an *agreement rate* per field. A parser that has
    stopped reading something shows up as that field disagreeing on nearly
    every listing, which is a very different signature from a market where
    prices genuinely moved (a few listings, in both directions).

    Run this before blessing an invariants baseline. Blessing a corpus that is
    already wrong pins the breakage as normal and the drift check will never
    fire.
    """
    from app.tasks._async_runner import run_async

    return run_async(_corpus_audit(sample_size=sample_size, city=city))


async def _corpus_audit(sample_size: int, city: Optional[str]) -> Dict[str, Any]:
    from collections import Counter
    from sqlalchemy import select, func
    from app.models.apartment import ApartmentModel
    from app.services.listing_check import check_listing, LIVE, GONE, UNKNOWN

    async with get_session_context() as session:
        stmt = (
            select(
                ApartmentModel.id,
                ApartmentModel.address,
                ApartmentModel.city,
                ApartmentModel.source_url,
                ApartmentModel.rent,
                ApartmentModel.bedrooms,
                ApartmentModel.bathrooms,
                ApartmentModel.sqft,
                ApartmentModel.available_date,
            )
            .where(
                ApartmentModel.is_active == 1,
                ApartmentModel.source_url.isnot(None),
            )
            .order_by(func.random())
            .limit(sample_size)
        )
        if city:
            stmt = stmt.where(ApartmentModel.city == city)
        rows = (await session.execute(stmt)).all()

    status_counts: Counter = Counter()
    field_disagreements: Counter = Counter()
    field_checked: Counter = Counter()
    examples: List[Dict[str, Any]] = []

    for row in rows:
        current = {
            "rent": row.rent,
            "bedrooms": row.bedrooms,
            "bathrooms": row.bathrooms,
            "sqft": row.sqft,
            "available_date": row.available_date,
        }
        try:
            status, updated, changes = await check_listing(row.source_url, current)
        except Exception as e:
            logger.warning(f"corpus_audit: check failed for {row.id}: {e}")
            status_counts[UNKNOWN] += 1
            continue

        status_counts[status] += 1
        if status != LIVE or not updated:
            continue

        for field in ("rent", "bedrooms", "bathrooms", "sqft", "available_date"):
            # Only count a field the source actually answered on; a field it
            # did not return is not a disagreement, and conflating the two is
            # the mistake this whole exercise exists to stop making.
            if updated.get(field) in (None, "", 0):
                continue
            field_checked[field] += 1
            if field in changes:
                field_disagreements[field] += 1

        if changes and len(examples) < 10:
            examples.append({
                "address": row.address,
                "city": row.city,
                "changes": changes,
            })

    agreement = {}
    for field, checked in field_checked.items():
        bad = field_disagreements.get(field, 0)
        agreement[field] = {
            "checked": checked,
            "disagreed": bad,
            "agreement_pct": round(100.0 * (checked - bad) / checked, 1) if checked else None,
        }

    reachable = status_counts[LIVE]
    result = {
        "status": "completed",
        "sampled": len(rows),
        "city": city,
        "source_status": dict(status_counts),
        "reachable": reachable,
        "field_agreement": agreement,
        "examples": examples,
        "estimated_cost_usd": round(len(rows) * 0.0005, 4),
    }
    logger.info(
        f"corpus_audit: sampled={len(rows)} live={reachable} "
        f"agreement={ {k: v['agreement_pct'] for k, v in agreement.items()} }"
    )
    return result


@celery_app.task(bind=True, max_retries=2, soft_time_limit=1800)
def backfill_pricing_model(self, apply: bool = False, batch_size: int = 500) -> Dict[str, Any]:
    """Re-run pricing-model detection over the stored corpus.

    The detector had no vocabulary for the commonest by-the-room case —
    renting one room in a shared house — and never read the listing URL,
    whose slug is often the most explicit signal available. 5 Linden St,
    Boston ("Room for rent: ... a private room in a shared apartment ... Full
    bedroom in a 4 bedroom / 1 bathroom apartment", slug
    "room-in-shared-4-bed-1-bath-home-in-allston") scored 0.4 against a 0.6
    threshold and was published as a whole 4-bed house for $1,130.

    90 listings across five markets were mislabelled the same way. Every such
    error runs in the too-good-to-be-true direction: one room's rent shown as
    a whole unit's, which the heuristic then ranks straight to the top.

    Reads description and source_url from Postgres — no Apify cost. Dry run by
    default. Run backfill-floorplans afterwards so per-bucket pricing_model
    picks the change up too.
    """
    from app.tasks._async_runner import run_async

    return run_async(_backfill_pricing_model(apply=apply, batch_size=batch_size))


async def _backfill_pricing_model(apply: bool, batch_size: int) -> Dict[str, Any]:
    from sqlalchemy import select, update
    from app.models.apartment import ApartmentModel
    from app.services.pricing_model_detector import detect_pricing_model

    scanned = 0
    changed = 0
    now_uncertain = 0
    flips: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    last_id = ""

    while True:
        async with get_session_context() as session:
            stmt = (
                select(
                    ApartmentModel.id,
                    ApartmentModel.address,
                    ApartmentModel.city,
                    ApartmentModel.description,
                    ApartmentModel.source_url,
                    ApartmentModel.bedrooms,
                    ApartmentModel.bathrooms,
                    ApartmentModel.rent,
                    ApartmentModel.pricing_model,
                )
                .where(ApartmentModel.is_active == 1)
                .order_by(ApartmentModel.id)
                .limit(batch_size)
            )
            if last_id:
                stmt = stmt.where(ApartmentModel.id > last_id)
            rows = (await session.execute(stmt)).all()
            if not rows:
                break

            for r in rows:
                scanned += 1
                last_id = r.id
                det = detect_pricing_model(
                    description=r.description or "",
                    bedrooms=r.bedrooms or 0,
                    bathrooms=r.bathrooms or 0,
                    rent=r.rent or 0,
                    city=r.city or "",
                    source_url=r.source_url or "",
                )
                if det.get("uncertain"):
                    now_uncertain += 1
                was = r.pricing_model or "per_unit"
                if det["pricing_model"] == was:
                    continue
                changed += 1
                pending.append({
                    "id": r.id,
                    "pricing_model": det["pricing_model"],
                    "pricing_model_confidence": det["confidence"],
                })
                if len(flips) < 15:
                    flips.append({
                        "address": r.address,
                        "city": r.city,
                        "beds_baths": f"{r.bedrooms}bd/{r.bathrooms}ba",
                        "rent": r.rent,
                        "from": was,
                        "to": det["pricing_model"],
                    })

            if apply and pending:
                for entry in pending:
                    await session.execute(
                        update(ApartmentModel)
                        .where(ApartmentModel.id == entry["id"])
                        .values(
                            pricing_model=entry["pricing_model"],
                            pricing_model_confidence=entry["pricing_model_confidence"],
                        )
                    )
                await session.commit()
            pending = []

    logger.info(
        f"backfill_pricing_model: scanned={scanned} changed={changed} "
        f"uncertain={now_uncertain} apply={apply}"
    )
    return {
        "status": "completed",
        "apply": apply,
        "scanned": scanned,
        "changed": changed,
        "still_uncertain": now_uncertain,
        "examples": flips,
    }
