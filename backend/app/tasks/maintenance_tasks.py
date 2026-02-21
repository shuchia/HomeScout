"""
Celery tasks for maintenance and cleanup operations.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from app.celery_app import celery_app
from app.database import get_session_context, is_database_enabled

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run an async coroutine in a sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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


@celery_app.task
def generate_metrics_snapshot() -> Dict[str, Any]:
    """
    Generate a snapshot of data collection metrics.

    Returns:
        Dict with current metrics
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    logger.info("Generating metrics snapshot")

    async def _metrics():
        from sqlalchemy import select, func
        from app.models.apartment import ApartmentModel
        from app.models.scrape_job import ScrapeJobModel

        metrics = {}

        async with get_session_context() as session:
            # Total listings
            stmt = select(func.count(ApartmentModel.id))
            result = await session.execute(stmt)
            metrics["total_listings"] = result.scalar() or 0

            # Active listings
            stmt = select(func.count(ApartmentModel.id)).where(
                ApartmentModel.is_active == 1
            )
            result = await session.execute(stmt)
            metrics["active_listings"] = result.scalar() or 0

            # Listings by source
            stmt = select(
                ApartmentModel.source,
                func.count(ApartmentModel.id)
            ).group_by(ApartmentModel.source)
            result = await session.execute(stmt)
            metrics["listings_by_source"] = {
                row[0]: row[1] for row in result
            }

            # Listings by city
            stmt = select(
                ApartmentModel.city,
                func.count(ApartmentModel.id)
            ).where(
                ApartmentModel.city.isnot(None)
            ).group_by(ApartmentModel.city).limit(20)
            result = await session.execute(stmt)
            metrics["listings_by_city"] = {
                row[0]: row[1] for row in result
            }

            # Average data quality
            stmt = select(func.avg(ApartmentModel.data_quality_score))
            result = await session.execute(stmt)
            metrics["avg_quality_score"] = round(result.scalar() or 0, 2)

            # Recent scrape jobs
            stmt = select(func.count(ScrapeJobModel.id)).where(
                ScrapeJobModel.created_at > datetime.utcnow() - timedelta(days=1)
            )
            result = await session.execute(stmt)
            metrics["jobs_last_24h"] = result.scalar() or 0

            # Successful jobs last 24h
            stmt = select(func.count(ScrapeJobModel.id)).where(
                ScrapeJobModel.created_at > datetime.utcnow() - timedelta(days=1),
                ScrapeJobModel.status == "completed",
            )
            result = await session.execute(stmt)
            metrics["successful_jobs_last_24h"] = result.scalar() or 0

        return metrics

    try:
        metrics = run_async(_metrics())
        metrics["timestamp"] = datetime.utcnow().isoformat()
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
    from sqlalchemy import select, update
    from app.models.apartment import ApartmentModel
    from app.models.market_config import MarketConfigModel

    now = datetime.utcnow()
    decay_counts = {"hot": 0, "standard": 0, "cool": 0}
    verification_dispatched = 0
    deactivated = 0

    async with get_session_context() as session:
        # Load all market configs for decay rates
        markets_result = await session.execute(select(MarketConfigModel))
        markets = {m.id: m for m in markets_result.scalars()}

        # Default decay rates by tier
        tier_rates = {"hot": 3, "standard": 2, "cool": 1}

        # Get all active listings
        stmt = select(ApartmentModel).where(ApartmentModel.is_active == 1)
        result = await session.execute(stmt)

        for apt in result.scalars():
            if not apt.last_seen_at:
                continue

            # Get decay rate from market or default
            market = markets.get(apt.market_id)
            tier = market.tier if market else "cool"
            decay_rate = tier_rates.get(tier, 1)

            # Calculate new confidence
            hours_since_seen = (now - apt.last_seen_at.replace(tzinfo=None)).total_seconds() / 3600
            new_confidence = max(0, int(100 - (hours_since_seen * decay_rate)))

            if new_confidence != apt.freshness_confidence:
                apt.freshness_confidence = new_confidence
                apt.confidence_updated_at = now
                decay_counts[tier] = decay_counts.get(tier, 0) + 1

            # Trigger verification at threshold
            if new_confidence < 40 and apt.verification_status is None:
                apt.verification_status = "pending"
                from app.tasks.maintenance_tasks import verify_listing
                verify_listing.apply_async(
                    kwargs={"apartment_id": apt.id},
                    queue="maintenance",
                )
                verification_dispatched += 1

            # Deactivate at zero confidence (unless verified)
            if new_confidence == 0 and apt.verification_status != "verified":
                apt.is_active = 0
                deactivated += 1

        await session.commit()

    logger.info(
        f"Decay update: {sum(decay_counts.values())} listings updated, "
        f"{verification_dispatched} verifications dispatched, "
        f"{deactivated} deactivated"
    )
    return {
        "status": "completed",
        "decay_counts": decay_counts,
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

        source_url = apt.source_url

    # Check the URL
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(source_url)

        gone_indicators = [
            "no longer available",
            "this listing has been removed",
            "listing not found",
            "page not found",
        ]

        is_gone = response.status_code == 404
        if not is_gone and response.status_code == 200:
            body = response.text.lower()
            is_gone = any(indicator in body for indicator in gone_indicators)

        async with get_session_context() as session:
            now = datetime.utcnow()
            if is_gone:
                await session.execute(
                    update(ApartmentModel)
                    .where(ApartmentModel.id == apartment_id)
                    .values(verification_status="gone", verified_at=now, is_active=0)
                )
                status = "gone"
            else:
                await session.execute(
                    update(ApartmentModel)
                    .where(ApartmentModel.id == apartment_id)
                    .values(verification_status="verified", verified_at=now, freshness_confidence=80)
                )
                status = "verified"
            await session.commit()

        return {"status": status, "apartment_id": apartment_id}

    except Exception as e:
        logger.warning(f"Verification failed for {apartment_id}: {e}")
        return {"status": "pending", "error": str(e)}


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
