"""
Dispatcher task — runs hourly, checks which markets need scraping,
and spawns individual scrape_city_task for each.
"""
import random
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from app.celery_app import celery_app
from app.database import get_session_context, is_database_enabled

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run an async coroutine in a sync context."""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task
def dispatch_scrapes() -> Dict[str, Any]:
    """
    Hourly dispatcher: check market_configs, spawn scrape tasks for markets that are due.

    Skips markets that:
    - are disabled
    - were scraped recently (within scrape_frequency_hours)
    - have 3+ consecutive failures (circuit breaker)
    - already have a running scrape job
    """
    if not is_database_enabled():
        return {"status": "skipped", "reason": "Database not enabled"}

    return run_async(_dispatch())


async def _dispatch() -> Dict[str, Any]:
    from sqlalchemy import select
    from app.models.market_config import MarketConfigModel
    from app.models.scrape_job import ScrapeJobModel

    now = datetime.now(timezone.utc)
    dispatched = []
    skipped = []

    async with get_session_context() as session:
        # Get all enabled markets
        stmt = select(MarketConfigModel).where(MarketConfigModel.is_enabled == True)
        result = await session.execute(stmt)
        markets = list(result.scalars())

        # Get currently running jobs
        running_stmt = select(ScrapeJobModel.city).where(ScrapeJobModel.status == "running")
        running_result = await session.execute(running_stmt)
        running_cities = {row[0] for row in running_result}

        for market in markets:
            # Circuit breaker: skip after 3 consecutive failures
            if market.consecutive_failures >= 3:
                skipped.append({"market": market.id, "reason": "circuit_breaker"})
                continue

            # Check if scrape is due
            if market.last_scrape_at:
                from datetime import timedelta
                next_scrape = market.last_scrape_at + timedelta(hours=market.scrape_frequency_hours)
                if now < next_scrape:
                    skipped.append({"market": market.id, "reason": "not_due"})
                    continue

            # Check if already running
            if market.city in running_cities:
                skipped.append({"market": market.id, "reason": "already_running"})
                continue

            # Dispatch with random stagger (0-60s)
            delay = random.randint(0, 60)
            from app.tasks.scrape_tasks import scrape_city_task
            scrape_city_task.apply_async(
                kwargs={"market_id": market.id},
                countdown=delay,
                queue="scraping",
            )
            dispatched.append({"market": market.id, "delay_seconds": delay})

    logger.info(f"Dispatched {len(dispatched)} scrapes, skipped {len(skipped)}")
    return {
        "status": "completed",
        "dispatched": dispatched,
        "skipped": skipped,
        "timestamp": now.isoformat(),
    }
