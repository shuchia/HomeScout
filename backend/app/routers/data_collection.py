"""
Admin API endpoints for data collection management.
"""
import os
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends, Body, Header
from pydantic import BaseModel, Field

from app.database import get_async_session, is_database_enabled, AsyncSession

logger = logging.getLogger(__name__)

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "homescout-dev-admin-key")

# How long a saved listing may sit unchecked before it counts as a backlog.
# A check takes 10-20s, so anything past a few minutes means the queue is
# stuck rather than merely busy.
CHECK_LAG_MINUTES = int(os.getenv("CHECK_LAG_MINUTES", "15"))


async def verify_admin_key(x_admin_key: str = Header(...)):
    """Require a valid X-Admin-Key header. Mirrors routers/invite.py so the
    same operator credential gates every admin surface. ADMIN_API_KEY is set
    per-env in AWS Secrets Manager (snugd/{env}/secrets)."""
    if x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin API key")
    return x_admin_key


router = APIRouter(
    prefix="/api/admin/data-collection",
    tags=["Data Collection"],
    dependencies=[Depends(verify_admin_key)],
)


# Request/Response Models
class TriggerJobRequest(BaseModel):
    """Request to trigger a manual scrape job."""
    source: str = Field(..., description="Data source (zillow, apartments_com, craigslist)")
    city: Optional[str] = Field(None, description="Specific city to scrape")
    state: Optional[str] = Field(None, description="State code (e.g., CA)")
    max_listings: int = Field(100, ge=1, le=1000, description="Maximum listings to scrape")


class JobResponse(BaseModel):
    """Response for job operations."""
    id: str
    source: str
    status: str
    city: Optional[str]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    metrics: Optional[dict]
    error_message: Optional[str]


class JobListResponse(BaseModel):
    """Response for job listing."""
    jobs: List[JobResponse]
    total: int
    page: int
    page_size: int


class SourceResponse(BaseModel):
    """Response for data source info."""
    id: str
    name: str
    is_enabled: bool
    is_healthy: bool
    provider: str
    rate_limits: dict
    schedule: dict
    metrics: dict


class SourceUpdateRequest(BaseModel):
    """Request to update data source configuration."""
    is_enabled: Optional[bool] = None
    scrape_frequency_hours: Optional[int] = Field(None, ge=1, le=168)
    rate_limit_per_hour: Optional[int] = Field(None, ge=1)
    rate_limit_per_day: Optional[int] = Field(None, ge=1)


class MetricsResponse(BaseModel):
    """Response for collection metrics.

    Every field compute_metrics_snapshot() produces has to be declared here.
    A response_model silently discards anything it does not know about, so an
    added metric shows up in the function, passes tests, deploys green — and
    is simply absent from the response.
    """
    total_listings: int
    active_listings: int
    listings_by_source: dict
    listings_by_city: dict
    avg_quality_score: float
    jobs_last_24h: int
    successful_jobs_last_24h: int
    timestamp: str
    floorplans: dict = Field(default_factory=dict)
    invariants: dict = Field(default_factory=dict)


class HealthCheckResponse(BaseModel):
    """Response for service health check."""
    database: dict
    redis: dict
    scrapers: dict
    overall_healthy: bool


# Endpoints

@router.post("/jobs", response_model=dict)
async def trigger_scrape_job(request: TriggerJobRequest):
    """
    Trigger a manual scrape job.

    Two modes:
    - With `city` + `state`: scrape that one market. Looks up the
      `market_id` from `market_configs` (the `scrape_city_task` signature
      switched from (source, city, state, max_listings) to (market_id) and
      this route's body shape was never updated — this resolves the
      mismatch).
    - Without city: full-source scrape across all configured cities.

    Returns:
        Job ID and Celery task ID.
    """
    job_id = str(uuid.uuid4())

    try:
        from app.tasks.scrape_tasks import scrape_source, scrape_city_task

        if request.city and request.state:
            # Resolve city+state to a market_id (case-insensitive). If no
            # matching market exists, surface a 400 so the operator knows
            # to create the market_config first, OR use the explicit
            # /markets/{id}/scrape endpoint.
            from sqlalchemy import select, func
            from app.models.market_config import MarketConfigModel
            from app.database import get_session_context

            async with get_session_context() as session:
                stmt = select(MarketConfigModel).where(
                    func.lower(MarketConfigModel.city) == request.city.lower(),
                    func.lower(MarketConfigModel.state) == request.state.lower(),
                )
                result = await session.execute(stmt)
                market = result.scalar_one_or_none()

            if not market:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"No market configured for {request.city}, {request.state}. "
                        f"Create it via POST /api/admin/data-collection/markets first, "
                        f"or call /api/admin/data-collection/markets/{{market_id}}/scrape "
                        f"with the market id directly."
                    ),
                )

            task = scrape_city_task.apply_async(
                kwargs={"market_id": market.id},
                queue="scraping",
            )
            return {
                "job_id": job_id,
                "task_id": task.id,
                "source": request.source,
                "market_id": market.id,
                "status": "queued",
                "message": (
                    f"Scrape job queued for market {market.id} "
                    f"({request.city}, {request.state})"
                ),
            }

        # Full source scrape — scrape_source signature still matches the
        # body shape, no remapping needed.
        task = scrape_source.delay(
            source=request.source,
            max_listings_per_city=request.max_listings,
        )
        return {
            "job_id": job_id,
            "task_id": task.id,
            "source": request.source,
            "status": "queued",
            "message": f"Full-source scrape job queued for {request.source}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to trigger scrape job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs", response_model=JobListResponse)
async def list_scrape_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source: Optional[str] = None,
    status: Optional[str] = None,
):
    """
    List scrape jobs with pagination and filtering.

    Args:
        page: Page number
        page_size: Items per page
        source: Filter by source
        status: Filter by status

    Returns:
        Paginated list of jobs
    """
    if not is_database_enabled():
        return JobListResponse(jobs=[], total=0, page=page, page_size=page_size)

    try:
        from sqlalchemy import select, func, desc
        from app.models.scrape_job import ScrapeJobModel
        from app.database import get_session_context

        async with get_session_context() as session:
            # Build query
            query = select(ScrapeJobModel)

            if source:
                query = query.where(ScrapeJobModel.source == source)
            if status:
                query = query.where(ScrapeJobModel.status == status)

            # Count total
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(count_query)
            total = total_result.scalar() or 0

            # Get page
            query = query.order_by(desc(ScrapeJobModel.created_at))
            query = query.offset((page - 1) * page_size).limit(page_size)
            result = await session.execute(query)

            jobs = []
            for job in result.scalars():
                jobs.append(JobResponse(
                    id=job.id,
                    source=job.source,
                    status=job.status,
                    city=job.city,
                    created_at=job.created_at.isoformat() if job.created_at else "",
                    started_at=job.started_at.isoformat() if job.started_at else None,
                    completed_at=job.completed_at.isoformat() if job.completed_at else None,
                    metrics={
                        "listings_found": job.listings_found,
                        "listings_new": job.listings_new,
                        "listings_duplicates": job.listings_duplicates,
                        "listings_errors": job.listings_errors,
                    },
                    error_message=job.error_message,
                ))

            return JobListResponse(
                jobs=jobs,
                total=total,
                page=page,
                page_size=page_size,
            )

    except Exception as e:
        logger.exception(f"Failed to list jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    """
    Get status of a specific scrape job.

    Args:
        job_id: Job ID

    Returns:
        Job details and status
    """
    if not is_database_enabled():
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        from sqlalchemy import select
        from app.models.scrape_job import ScrapeJobModel
        from app.database import get_session_context

        async with get_session_context() as session:
            stmt = select(ScrapeJobModel).where(ScrapeJobModel.id == job_id)
            result = await session.execute(stmt)
            job = result.scalar_one_or_none()

            if not job:
                raise HTTPException(status_code=404, detail="Job not found")

            return JobResponse(
                id=job.id,
                source=job.source,
                status=job.status,
                city=job.city,
                created_at=job.created_at.isoformat() if job.created_at else "",
                started_at=job.started_at.isoformat() if job.started_at else None,
                completed_at=job.completed_at.isoformat() if job.completed_at else None,
                metrics={
                    "listings_found": job.listings_found,
                    "listings_new": job.listings_new,
                    "listings_duplicates": job.listings_duplicates,
                    "listings_errors": job.listings_errors,
                },
                error_message=job.error_message,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources", response_model=List[SourceResponse])
async def list_data_sources():
    """
    List all configured data sources.

    Returns:
        List of data sources with configuration
    """
    # Return default sources if database not enabled
    default_sources = [
        SourceResponse(
            id="zillow",
            name="Zillow",
            is_enabled=True,
            is_healthy=True,
            provider="apify",
            rate_limits={"per_hour": 100, "per_day": 1000},
            schedule={"frequency_hours": 6},
            metrics={"total_listings_scraped": 0},
        ),
        SourceResponse(
            id="apartments_com",
            name="Apartments.com",
            is_enabled=True,
            is_healthy=True,
            provider="apify",
            rate_limits={"per_hour": 100, "per_day": 1000},
            schedule={"frequency_hours": 6},
            metrics={"total_listings_scraped": 0},
        ),
        SourceResponse(
            id="craigslist",
            name="Craigslist",
            is_enabled=True,
            is_healthy=True,
            provider="scrapingbee",
            rate_limits={"per_hour": 50, "per_day": 500},
            schedule={"frequency_hours": 24},
            metrics={"total_listings_scraped": 0},
        ),
    ]

    if not is_database_enabled():
        return default_sources

    try:
        from sqlalchemy import select
        from app.models.data_source import DataSourceModel
        from app.database import get_session_context

        async with get_session_context() as session:
            stmt = select(DataSourceModel)
            result = await session.execute(stmt)
            sources = []

            for source in result.scalars():
                sources.append(SourceResponse(**source.to_dict()))

            return sources if sources else default_sources

    except Exception as e:
        logger.exception(f"Failed to list sources: {e}")
        return default_sources


@router.put("/sources/{source_id}", response_model=SourceResponse)
async def update_data_source(source_id: str, request: SourceUpdateRequest):
    """
    Update data source configuration.

    Args:
        source_id: Source ID to update
        request: Fields to update

    Returns:
        Updated source configuration
    """
    if not is_database_enabled():
        raise HTTPException(
            status_code=503,
            detail="Database not enabled - cannot update source configuration"
        )

    try:
        from sqlalchemy import select
        from app.models.data_source import DataSourceModel
        from app.database import get_session_context

        async with get_session_context() as session:
            stmt = select(DataSourceModel).where(DataSourceModel.id == source_id)
            result = await session.execute(stmt)
            source = result.scalar_one_or_none()

            if not source:
                raise HTTPException(status_code=404, detail="Source not found")

            # Update fields
            if request.is_enabled is not None:
                source.is_enabled = request.is_enabled
            if request.scrape_frequency_hours is not None:
                source.scrape_frequency_hours = request.scrape_frequency_hours
            if request.rate_limit_per_hour is not None:
                source.rate_limit_per_hour = request.rate_limit_per_hour
            if request.rate_limit_per_day is not None:
                source.rate_limit_per_day = request.rate_limit_per_day

            await session.commit()

            return SourceResponse(**source.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update source: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics", response_model=MetricsResponse)
async def get_collection_metrics():
    """Get data collection metrics.

    Calls the async compute function directly. Going through the Celery task
    wrapper from within a FastAPI handler used to silently return zeros — the
    wrapper spawns a fresh event loop via `run_async`, which collides with the
    request's running loop and raises a RuntimeError that the handler's
    `except` then swallowed.
    """
    if not is_database_enabled():
        return MetricsResponse(
            total_listings=0,
            active_listings=0,
            listings_by_source={},
            listings_by_city={},
            avg_quality_score=0.0,
            jobs_last_24h=0,
            successful_jobs_last_24h=0,
            timestamp=datetime.utcnow().isoformat(),
        )

    from app.tasks.maintenance_tasks import compute_metrics_snapshot
    metrics = await compute_metrics_snapshot()
    return MetricsResponse(**metrics)


@router.get("/health", response_model=HealthCheckResponse)
async def check_service_health():
    """
    Check health of all data collection services.

    Returns:
        Health status of each component
    """
    health = {
        "database": {"healthy": False, "message": "Not configured"},
        "redis": {"healthy": False, "message": "Not configured"},
        "scrapers": {},
        "overall_healthy": False,
    }

    # Check database
    if is_database_enabled():
        try:
            from sqlalchemy import text
            from app.database import get_session_context

            async with get_session_context() as session:
                await session.execute(text("SELECT 1"))
                health["database"] = {"healthy": True, "message": "Connected"}
        except Exception as e:
            health["database"] = {"healthy": False, "message": str(e)}
    else:
        health["database"] = {"healthy": True, "message": "Using JSON fallback"}

    # Check Redis/Celery
    try:
        from app.celery_app import celery_app
        celery_app.control.ping(timeout=1)
        health["redis"] = {"healthy": True, "message": "Connected"}
    except Exception as e:
        health["redis"] = {"healthy": False, "message": str(e)}

    # Check scrapers
    try:
        from app.services.scrapers.apify_service import ApifyService
        from app.services.scrapers.scrapingbee_service import ScrapingBeeService

        # Check Apify
        apify = ApifyService("zillow")
        apify_health = await apify.health_check()
        health["scrapers"]["apify"] = apify_health
        await apify.close()

        # Check ScrapingBee
        scrapingbee = ScrapingBeeService("craigslist")
        scrapingbee_health = await scrapingbee.health_check()
        health["scrapers"]["scrapingbee"] = scrapingbee_health
        await scrapingbee.close()

    except Exception as e:
        health["scrapers"]["error"] = str(e)

    # Overall health
    db_healthy = health["database"].get("healthy", False)
    health["overall_healthy"] = db_healthy

    return HealthCheckResponse(**health)


# A pct_ invariant moving this many points from the blessed baseline is
# reported. Chosen so the faults actually seen would have tripped it — the
# availability gap was ~56 points of the corpus and the rentLabel change took
# price-on-request buckets to 18% — while ordinary week-to-week market
# movement (a point or two) does not.
INVARIANT_STEP_PCT = 5.0

_INVARIANT_BASELINE_KEY = "invariants:baseline"


async def _invariant_redis():
    """Redis handle, or None. Never raises: a missing baseline must degrade to
    'no drift reported', never to a failed health check.

    Builds its own client rather than borrowing ApartmentService's. There is
    no module-level instance to borrow — main.py and the routers each
    construct their own — so the import failed, the bare except swallowed the
    ImportError, and the baseline endpoint reported "Redis not available"
    while Redis was perfectly healthy. The exception is logged now; a handler
    that hides why it failed is worse than one that fails loudly.
    """
    try:
        import redis.asyncio as aioredis

        return aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    except Exception as e:
        logger.warning(f"Invariant baseline store unavailable: {e}")
        return None


async def _get_invariant_baseline() -> Optional[Dict[str, Any]]:
    r = await _invariant_redis()
    if not r:
        return None
    try:
        raw = await r.get(_INVARIANT_BASELINE_KEY)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _compare_invariants(
    current: Dict[str, Any], baseline: Dict[str, Any], problems: List[str]
) -> tuple:
    """Compare current ratios to the blessed baseline, overall and per city.

    Per city matters: a global ratio cannot survive the corpus growing. Adding
    one market with a different character shifts every global number at once,
    which raises a false alarm and masks a real regression elsewhere at the
    same time. A city with no baseline is reported as unblessed rather than
    compared against nothing.
    """
    drift: Dict[str, Any] = {}

    def _diff(scope: str, now: Dict[str, Any], was: Dict[str, Any]) -> Dict[str, Any]:
        out = {}
        for field, now_val in (now or {}).items():
            if not field.startswith("pct_"):
                continue
            prev = (was or {}).get(field)
            if prev is None or not isinstance(now_val, (int, float)):
                continue
            delta = round(now_val - prev, 2)
            out[field] = {"baseline": prev, "now": now_val, "delta": delta}
            if abs(delta) >= INVARIANT_STEP_PCT:
                problems.append(
                    f"[{scope}] {field} moved {delta:+.1f} points "
                    f"({prev}% → {now_val}%) — check the parser before the data"
                )
        return out

    drift["overall"] = _diff(
        "overall", current.get("overall", {}), baseline.get("overall", {})
    )

    base_cities = baseline.get("by_city", {}) or {}
    now_cities = current.get("by_city", {}) or {}
    per_city = {}
    unblessed = []
    for city, now in now_cities.items():
        was = base_cities.get(city)
        if not was:
            unblessed.append(city)
            continue
        # Ignore a city too small for a ratio to mean anything.
        if (now.get("active_listings") or 0) < 25:
            continue
        per_city[city] = _diff(city, now, was)
    drift["by_city"] = per_city
    return drift, unblessed


@router.post("/backfill-pricing-model")
async def backfill_pricing_model_endpoint(
    apply: bool = Query(False),
    batch_size: int = Query(500, ge=1, le=1000),
):
    """Re-run pricing-model detection over the stored corpus.

    The detector had no vocabulary for renting one room in a shared house and
    never read the listing URL, whose slug is often the most explicit signal
    there is. 5 Linden St, Boston was published as a whole 4-bed house for
    $1,130; 90 listings across five markets were wrong the same way, every one
    of them in the too-good-to-be-true direction.

    Reads from Postgres — no Apify cost. Dry run by default. Follow with
    backfill-floorplans so per-bucket pricing_model picks it up.
    """
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from app.tasks.maintenance_tasks import backfill_pricing_model
    task = backfill_pricing_model.apply_async(
        kwargs={"apply": apply, "batch_size": batch_size}, queue="maintenance"
    )
    return {"status": "dispatched", "task_id": task.id, "apply": apply}


@router.post("/reset-circuit-breakers")
async def reset_circuit_breakers(market_id: Optional[str] = Query(None)):
    """Clear consecutive_failures so the scheduled dispatcher resumes.

    dispatcher.py skips any market with 3+ consecutive failures. That is the
    right behaviour while a fault is live, but the counter does not clear
    itself: once the cause is fixed, scraping stays blocked until
    cleanup_maintenance runs at 3 AM UTC.

    After the 2026-10-09 ingestion break every market sat at 4 failures with
    no way to resume them, because consecutive_failures is not an updatable
    field on the market endpoint and cleanup_maintenance has no HTTP trigger.
    Waiting a day with scraping down is not a reasonable recovery path.

    Fix the cause first, then verify with a manual scrape — that route
    bypasses the breaker — and only then reset.
    """
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from sqlalchemy import update, select
    from app.models.market_config import MarketConfigModel
    from app.database import get_session_context

    async with get_session_context() as session:
        stmt = update(MarketConfigModel).where(
            MarketConfigModel.consecutive_failures > 0
        )
        if market_id:
            stmt = stmt.where(MarketConfigModel.id == market_id)
        result = await session.execute(stmt.values(consecutive_failures=0))
        await session.commit()

        remaining = (
            await session.execute(
                select(MarketConfigModel.id).where(
                    MarketConfigModel.consecutive_failures >= 3
                )
            )
        ).scalars().all()

    return {
        "status": "reset",
        "markets_cleared": result.rowcount,
        "still_tripped": list(remaining),
    }


@router.post("/corpus-audit")
async def corpus_audit_endpoint(
    sample_size: int = Query(40, ge=5, le=300),
    city: Optional[str] = Query(None),
):
    """Check a random sample of the corpus against its source.

    The honest answer to "does the corpus look right". Re-fetches each sampled
    listing through the same scrape_url() the saved-listing check uses and
    reports a per-field agreement rate.

    Read the shape, not just the number. A parser that stopped reading a field
    disagrees on nearly *every* listing; a market where prices genuinely moved
    disagrees on a few, in both directions.

    ~$0.0005 per listing — 40 listings is about two cents. Budget ~30s per
    listing: 40 is roughly 20 minutes, 300 is two and a half hours. Costs real
    money and real time, so it is a deliberate action, not a cron.

    Each disagreement is logged as its own line ("corpus_audit diff | field |
    from -> to | city | address"), because Celery truncates a long result
    repr and the direction and magnitude are the whole signal.
    """
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from app.tasks.maintenance_tasks import corpus_audit
    task = corpus_audit.apply_async(
        kwargs={"sample_size": sample_size, "city": city}, queue="maintenance"
    )
    return {
        "status": "dispatched",
        "task_id": task.id,
        "sample_size": sample_size,
        "city": city,
        "estimated_cost_usd": round(sample_size * 0.0005, 4),
    }


@router.post("/invariants/baseline")
async def set_invariant_baseline(city: Optional[str] = Query(None)):
    """Bless the current ingestion ratios as the reference point.

    Drift is measured against a baseline a human set, not against the previous
    run. A self-updating baseline tracks whatever the pipeline is doing,
    including the thing that has quietly broken — which is how the
    availability gap went unnoticed for months.

    Pass `city` to bless one market only. That is the normal case when adding
    a market: its ratios are new and unmeasured, while every existing market
    already has a baseline that may be actively catching something. Blessing
    everything would overwrite those.

    Without `city`, the overall ratios and every city are blessed at once —
    use that for a first run, or after a fix you have verified.

    Verify before blessing: run `corpus-audit` to check a sample of listings
    against their source. Blessing an already-broken corpus pins the breakage
    as normal and the check will never fire.
    """
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from datetime import datetime, timezone
    from app.tasks.maintenance_tasks import compute_metrics_snapshot

    r = await _invariant_redis()
    if not r:
        raise HTTPException(status_code=503, detail="Redis not available")

    snap = await compute_metrics_snapshot()
    inv = snap.get("invariants", {}) or {}
    now = datetime.now(timezone.utc).isoformat()

    if city:
        by_city = (inv.get("by_city") or {})
        if city not in by_city:
            raise HTTPException(
                status_code=404,
                detail=f"No active listings for city '{city}' — nothing to bless",
            )
        existing = await _get_invariant_baseline() or {}
        existing.setdefault("by_city", {})[city] = by_city[city]
        existing["_set_at"] = now
        await r.set(_INVARIANT_BASELINE_KEY, json.dumps(existing))
        return {"status": "baseline set", "scope": city, "baseline": by_city[city]}

    blessed = {
        "overall": inv.get("overall", {}),
        "by_city": inv.get("by_city", {}),
        "_set_at": now,
    }
    # No TTL: a baseline that silently expires takes the alerting with it.
    await r.set(_INVARIANT_BASELINE_KEY, json.dumps(blessed))
    return {
        "status": "baseline set",
        "scope": "all",
        "cities": sorted(blessed["by_city"]),
        "overall": blessed["overall"],
    }


@router.get("/pipeline-health")
async def check_pipeline_health():
    """
    Is the scraping pipeline actually doing its job?

    /health answers "can we reach our dependencies", which stayed green through
    two multi-week outages. This answers "is work happening", which is the
    question that was going unasked: scrape tasks were dying before they
    created a scrape_jobs row, so they recorded no failure, tripped no circuit
    breaker, and left last_scrape_at untouched — and the hourly decay task had
    failed every single run for weeks without anyone noticing, which in turn
    masked the scraper by freezing every listing's freshness score.

    Anything in `problems` is worth an alert.
    """
    if not is_database_enabled():
        return {"healthy": True, "message": "Database not enabled", "problems": []}

    from datetime import datetime, timezone
    from sqlalchemy import select, func
    from app.models.market_config import MarketConfigModel
    from app.models.apartment import ApartmentModel
    from app.models.scrape_job import ScrapeJobModel
    from app.database import get_session_context

    now = datetime.now(timezone.utc)
    problems: List[str] = []
    markets_out = []

    try:
        async with get_session_context() as session:
            result = await session.execute(
                select(MarketConfigModel).where(MarketConfigModel.is_enabled == True)
            )
            for m in result.scalars():
                if m.last_scrape_at:
                    age_hours = (now - m.last_scrape_at).total_seconds() / 3600
                    # One full missed cycle is noise; two is a signal.
                    overdue = age_hours > (m.scrape_frequency_hours * 2)
                else:
                    age_hours = None
                    overdue = True

                if overdue:
                    problems.append(
                        f"market '{m.id}' has not scraped in "
                        f"{'ever' if age_hours is None else f'{age_hours:.0f}h'} "
                        f"(frequency {m.scrape_frequency_hours}h)"
                    )
                if m.consecutive_failures >= 3:
                    problems.append(f"market '{m.id}' circuit breaker is open")

                markets_out.append({
                    "id": m.id,
                    "tier": m.tier,
                    "frequency_hours": m.scrape_frequency_hours,
                    "last_scrape_at": m.last_scrape_at.isoformat() if m.last_scrape_at else None,
                    "hours_since_scrape": round(age_hours, 1) if age_hours is not None else None,
                    "last_scrape_status": m.last_scrape_status,
                    "consecutive_failures": m.consecutive_failures,
                    "overdue": overdue,
                })

            # The decay task writes confidence_updated_at on every listing it
            # touches, so the freshest one is a proxy for "when did decay last
            # succeed" without needing a task-run table.
            last_decay = (
                await session.execute(select(func.max(ApartmentModel.confidence_updated_at)))
            ).scalar()

            # The window has to span the slowest market's cadence, or the
            # check fires constantly: at weekly sweeps a normal day has zero
            # jobs, and a fixed 24h window reads that as an outage.
            slowest = max((m["frequency_hours"] for m in markets_out), default=24)
            window_hours = max(48, slowest * 2)
            jobs_in_window = (
                await session.execute(
                    select(func.count()).select_from(ScrapeJobModel).where(
                        ScrapeJobModel.created_at >= now - timedelta(hours=window_hours)
                    )
                )
            ).scalar() or 0

        decay_age_hours = None
        if last_decay:
            if last_decay.tzinfo is None:
                last_decay = last_decay.replace(tzinfo=timezone.utc)
            decay_age_hours = (now - last_decay).total_seconds() / 3600
            # Scheduled hourly; 3h means it has missed several in a row.
            if decay_age_hours > 3:
                problems.append(f"decay task has not succeeded in {decay_age_hours:.0f}h")
        else:
            problems.append("decay task has never succeeded")

        # Expected scrapes/day across enabled markets. Tasks that die before
        # creating their job row are invisible here by definition, which is
        # exactly why this compares against the schedule rather than trusting
        # the job table to be complete.
        expected_in_window = (
            sum(window_hours / m["frequency_hours"] for m in markets_out)
            if markets_out else 0
        )
        if expected_in_window and jobs_in_window < expected_in_window * 0.5:
            problems.append(
                f"only {jobs_in_window} scrape jobs in {window_hours}h, "
                f"expected ~{expected_in_window:.0f}"
            )

        # Listing checks run on the worker, so if it is unhealthy they simply
        # stop and every saved listing quietly keeps its corpus copy. Nothing
        # above would notice — the scrape and decay signals watch different
        # tasks — and the user-visible symptom is silent staleness rather than
        # an error. A check is queued the moment a row is created, so a row
        # created well over the 10-20s a check takes and still never checked
        # means the queue is not draining.
        #
        # Guarded separately: saved_listings lives in Supabase, not RDS, so a
        # Supabase outage must not take down the rest of this endpoint.
        checks = {"unchecked_backlog": None, "threshold_minutes": CHECK_LAG_MINUTES}
        try:
            from app.services.tier_service import supabase_admin

            if supabase_admin:
                cutoff = (now - timedelta(minutes=CHECK_LAG_MINUTES)).isoformat()
                stale = (
                    supabase_admin.table("saved_listings")
                    .select("id")
                    .is_("listing_checked_at", "null")
                    .lt("created_at", cutoff)
                    .limit(100)
                    .execute()
                )
                backlog = len(stale.data or [])
                checks["unchecked_backlog"] = backlog
                if backlog:
                    problems.append(
                        f"{backlog}{'+' if backlog >= 100 else ''} saved listings "
                        f"never checked after {CHECK_LAG_MINUTES}min — "
                        f"listing checks are not draining"
                    )
        except Exception as e:
            logger.warning(f"Could not measure listing-check lag: {e}")
            checks["error"] = str(e)

        # Buildings with no floorplan bucket are invisible to search while
        # USE_FLOORPLAN_SEARCH is on, so this is coverage debt rather than
        # trivia. backfill_floorplans is the remedy.
        floorplans: Dict[str, Any] = {}
        try:
            from app.models.apartment_floorplan import ApartmentFloorplanModel

            async with get_session_context() as session:
                with_buckets = (
                    await session.execute(
                        select(func.count(func.distinct(ApartmentFloorplanModel.apartment_id)))
                        .select_from(ApartmentFloorplanModel)
                        .join(ApartmentModel, ApartmentModel.id == ApartmentFloorplanModel.apartment_id)
                        .where(ApartmentModel.is_active == 1)
                    )
                ).scalar() or 0
                active_total = (
                    await session.execute(
                        select(func.count()).select_from(ApartmentModel).where(
                            ApartmentModel.is_active == 1
                        )
                    )
                ).scalar() or 0
            missing = max(0, active_total - with_buckets)
            floorplans = {
                "active_buildings_with_buckets": with_buckets,
                "active_buildings_without_buckets": missing,
            }
            # Flagged again as of 2026-10-01, because zero is now the real
            # steady state.
            #
            # This alert was added, then removed the same day: at the time,
            # build_floorplan_buckets emitted nothing for a fully-leased
            # building, so 124 listings had no buckets by design and the check
            # sat permanently red. Those buildings now get buckets marked
            # available_units = 0, which took the count to 0 and leaves only
            # genuine faults behind it — a building with no floorplan array and
            # no bedroom value, or one whose floorplans are all unparseable.
            #
            # Worth knowing if this fires: a weekly sweep rebuilds buckets
            # inline for every listing it touches, so a handful appearing
            # mid-sweep may simply be rows not yet re-scraped. A count that
            # persists across a full sweep is the one to chase.
            if missing:
                problems.append(
                    f"{missing} active listings have no floorplan buckets — "
                    f"invisible to search; run backfill-floorplans"
                )
        except Exception as e:
            logger.warning(f"Could not measure floorplan coverage: {e}")

        # --- Ingestion invariants -----------------------------------------
        #
        # Does the data still look like data? Every fault found in 2026 was a
        # parser or config problem that produced plausible output rather than
        # an error, so none of the signals above would have moved. These
        # ratios would have: a field the normalizer stops reading moves one of
        # them hard and immediately.
        #
        # Compared against a baseline a human blessed, not against the last
        # run — a baseline that updates itself drifts along with the fault it
        # is supposed to catch.
        invariants: Dict[str, Any] = {}
        try:
            from app.tasks.maintenance_tasks import compute_metrics_snapshot

            snap = await compute_metrics_snapshot()
            invariants = snap.get("invariants", {}) or {}
            baseline = await _get_invariant_baseline()

            if baseline:
                drift, unblessed = _compare_invariants(invariants, baseline, problems)
                invariants["drift"] = drift
                invariants["baseline_set_at"] = baseline.get("_set_at")
                if unblessed:
                    # Informational, not a problem: a newly added market has no
                    # baseline yet and that is the expected state, not a fault.
                    invariants["cities_without_baseline"] = sorted(unblessed)
            else:
                invariants["drift"] = None
                invariants["note"] = (
                    "no baseline set — run a corpus audit, then "
                    "POST /invariants/baseline to bless the current ratios"
                )
        except Exception as e:
            # Reported as a problem, not just logged. An empty invariants dict
            # reads as "nothing to report", which is precisely the failure
            # shape this check exists to catch — and it already happened: a
            # jsonb_array_length over a non-array row 500'd /metrics while
            # pipeline-health stayed green because it swallowed the exception
            # here.
            logger.warning(f"Could not evaluate ingestion invariants: {e}")
            problems.append(f"ingestion invariants could not be computed: {e}")
            invariants = {"error": str(e)}

        return {
            "healthy": not problems,
            "problems": problems,
            "invariants": invariants,
            "floorplans": floorplans,
            "listing_checks": checks,
            "checked_at": now.isoformat(),
            "markets": markets_out,
            "decay": {
                "last_success_at": last_decay.isoformat() if last_decay else None,
                "hours_since": round(decay_age_hours, 1) if decay_age_hours is not None else None,
            },
            "scrape_jobs": {
                "window_hours": window_hours,
                "actual": jobs_in_window,
                "expected": round(expected_in_window, 1),
            },
        }

    except Exception as e:
        logger.exception(f"Pipeline health check failed: {e}")
        return {"healthy": False, "problems": [f"health check itself failed: {e}"]}


# --- Market Configuration Endpoints ---

@router.get("/markets")
async def list_markets():
    """List all market configurations."""
    if not is_database_enabled():
        return {"markets": [], "message": "Database not enabled"}

    from sqlalchemy import select
    from app.models.market_config import MarketConfigModel
    from app.database import get_session_context

    async with get_session_context() as session:
        result = await session.execute(
            select(MarketConfigModel).order_by(MarketConfigModel.tier, MarketConfigModel.display_name)
        )
        markets = []
        for m in result.scalars():
            markets.append({
                "id": m.id,
                "display_name": m.display_name,
                "city": m.city,
                "state": m.state,
                "tier": m.tier,
                "is_enabled": m.is_enabled,
                "scrape_frequency_hours": m.scrape_frequency_hours,
                "max_listings_per_scrape": m.max_listings_per_scrape,
                "last_scrape_at": m.last_scrape_at.isoformat() if m.last_scrape_at else None,
                "last_scrape_status": m.last_scrape_status,
                "consecutive_failures": m.consecutive_failures,
            })
        return {"markets": markets, "total": len(markets)}


@router.post("/markets")
async def create_market(market: dict = Body(...)):
    """Add a new market. Required: id, display_name, city, state. Optional: tier, scrape_frequency_hours."""
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from app.models.market_config import MarketConfigModel
    from app.database import get_session_context

    async with get_session_context() as session:
        m = MarketConfigModel(
            id=market["id"],
            display_name=market["display_name"],
            city=market["city"],
            state=market["state"],
            tier=market.get("tier", "cool"),
            scrape_frequency_hours=market.get("scrape_frequency_hours", 24),
            max_listings_per_scrape=market.get("max_listings_per_scrape", 100),
        )
        session.add(m)
        await session.commit()
        return {"status": "created", "market_id": m.id}


@router.put("/markets/{market_id}")
async def update_market(market_id: str, updates: dict = Body(...)):
    """Update market config. Supports: tier, is_enabled, scrape_frequency_hours, max_listings_per_scrape."""
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from sqlalchemy import update, select
    from app.models.market_config import MarketConfigModel
    from app.database import get_session_context

    allowed = {"tier", "is_enabled", "scrape_frequency_hours", "max_listings_per_scrape"}
    values = {k: v for k, v in updates.items() if k in allowed}

    if not values:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    async with get_session_context() as session:
        await session.execute(
            update(MarketConfigModel).where(MarketConfigModel.id == market_id).values(**values)
        )
        await session.commit()
        return {"status": "updated", "market_id": market_id, "updated_fields": list(values.keys())}


@router.post("/markets/{market_id}/scrape")
async def trigger_market_scrape(market_id: str):
    """Trigger an immediate scrape for a specific market."""
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from sqlalchemy import select
    from app.models.market_config import MarketConfigModel
    from app.database import get_session_context

    async with get_session_context() as session:
        result = await session.execute(
            select(MarketConfigModel).where(MarketConfigModel.id == market_id)
        )
        market = result.scalar_one_or_none()
        if not market:
            raise HTTPException(status_code=404, detail=f"Market {market_id} not found")

    from app.tasks.scrape_tasks import scrape_city_task
    task = scrape_city_task.apply_async(kwargs={"market_id": market_id}, queue="scraping")

    return {"status": "dispatched", "market_id": market_id, "task_id": task.id}


@router.post("/backfill-fees")
async def backfill_fees():
    """Dispatch a Celery task to recompute fees from raw_data for all active listings."""
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from app.tasks.true_cost_tasks import backfill_fees_task
    task = backfill_fees_task.apply_async(queue="maintenance")

    return {"status": "dispatched", "task_id": task.id, "message": "Backfill running in background"}


@router.post("/normalize-nyc-cities")
async def normalize_nyc_cities():
    """One-shot fix for existing rows where the apartments.com city
    is a borough or NYC neighborhood (Brooklyn, Bronx, Astoria, etc.)
    instead of "New York". Mirrors the on-write normalization in
    apify_service.py that catches all future scrapes.
    """
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from app.tasks.maintenance_tasks import backfill_nyc_city_normalization
    task = backfill_nyc_city_normalization.apply_async(queue="maintenance")
    return {"status": "dispatched", "task_id": task.id}


@router.post("/backfill-extended-fields")
async def backfill_extended_fields_endpoint(only_missing: bool = True, batch_size: int = 200):
    """Populate the nearby_schools + floor_plans columns from existing
    apartments.raw_data. No Apify call — pure-backend extraction added
    in task #27. Idempotent when only_missing=True.
    """
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from app.tasks.maintenance_tasks import backfill_extended_fields as task
    dispatched = task.apply_async(
        kwargs={"only_missing": only_missing, "batch_size": batch_size},
        queue="maintenance",
    )
    return {
        "status": "dispatched",
        "task_id": dispatched.id,
        "only_missing": only_missing,
        "batch_size": batch_size,
    }


@router.post("/backfill-enrichment")
async def backfill_enrichment(only_missing: bool = True, batch_size: int = 200):
    """Populate the enrichment columns (specials, walk_score, transit_score,
    apartments_com_rating, available_units, transit_options, virtual_tour_urls,
    contact_name, property_website) from existing apartments.raw_data.

    Idempotent — by default only touches rows whose enrichment fields are
    still NULL. Pass ``only_missing=false`` to force re-extraction.
    """
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from app.tasks.maintenance_tasks import backfill_enrichment as backfill_enrichment_task
    task = backfill_enrichment_task.apply_async(
        kwargs={"only_missing": only_missing, "batch_size": batch_size},
        queue="maintenance",
    )

    return {
        "status": "dispatched",
        "task_id": task.id,
        "only_missing": only_missing,
        "batch_size": batch_size,
    }


@router.post("/backfill-floorplans")
async def backfill_floorplans_endpoint(
    only_missing: bool = Query(True),
    batch_size: int = Query(200, ge=1, le=1000),
):
    """Build floorplan buckets for listings that lack them.

    An active listing with no bucket is invisible to search while
    USE_FLOORPLAN_SEARCH is on — the join has nothing to match. pipeline-health
    reports the count as `floorplans.active_buildings_without_buckets`; this is
    the remedy.

    Buckets are normally built inline during a scrape, so a gap means listings
    that predate that behaviour, or whose scrape failed partway.

    only_missing=True (the default) only touches listings with no buckets at
    all. Pass false to rebuild everything, which is far more expensive.
    """
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from app.tasks.maintenance_tasks import backfill_floorplans
    task = backfill_floorplans.apply_async(
        kwargs={"only_missing": only_missing, "batch_size": batch_size},
        queue="maintenance",
    )
    return {"status": "dispatched", "task_id": task.id, "only_missing": only_missing}


@router.post("/backfill-available-dates")
async def backfill_available_dates_endpoint(
    apply: bool = Query(False),
    batch_size: int = Query(500, ge=1, le=1000),
):
    """Recover availability dates already sitting in `available_units`.

    The scrape stored the rentals array verbatim but the extraction was gated
    on `models` being non-empty. Single-unit and by-the-room listings publish
    no models and key their rentals by `key` rather than `modelId`, so their
    dates were dropped — 9 Hancock St held availableDate 2026-11-01 while the
    card said availability could not be found.

    Reads from Postgres only, so there is no Apify cost. Dry run by default:
    it reports how many rows are recoverable without writing. Pass apply=true
    to persist. Rows that already carry a date are never touched.

    Run `backfill-floorplans?only_missing=false` afterwards so the rebuilt
    buckets pick the recovered dates up.
    """
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from app.tasks.maintenance_tasks import backfill_available_dates
    task = backfill_available_dates.apply_async(
        kwargs={"apply": apply, "batch_size": batch_size},
        queue="maintenance",
    )
    return {"status": "dispatched", "task_id": task.id, "apply": apply}


@router.post("/merge-duplicate-properties")
async def merge_duplicate_properties_endpoint(apply: bool = Query(False)):
    """Collapse rows that are repeat captures of one source listing.

    Measured on QA 2026-10-03: 583 of 3,737 rows (15.6%) were duplicates of a
    property already held, accumulating over a median 50 days because both the
    content hash and the fuzzy matcher key on rent. Ingestion now dedupes on
    the source id, so this is a one-off backlog clear.

    Losers are **deactivated, not deleted** — `saved_listings.apartment_id`
    lives in Supabase and points at these ids across a database boundary, so
    deleting would orphan favourites and tours. Deactivating removes them from
    search and is reversible.

    Dry run by default; the response lists what would change. Pass apply=true
    to write.
    """
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from app.tasks.maintenance_tasks import merge_duplicate_properties
    task = merge_duplicate_properties.apply_async(
        kwargs={"apply": apply}, queue="maintenance"
    )
    return {"status": "dispatched", "task_id": task.id, "apply": apply}


@router.post("/normalize-city-names")
async def normalize_city_names_endpoint(
    apply: bool = Query(False),
    batch_size: int = Query(500, ge=1, le=1000),
):
    """Bring stored city names to their canonical spelling.

    Distinct from the NYC and Boston folds, which decide *which market* a
    listing belongs to. This decides whether two rows are using the same
    string for the same place: SAN FRANCISCO/San Francisco,
    Mc Kees Rocks/McKees Rocks, Mt Lebanon/Mount Lebanon, The Bronx/Bronx.

    Ingestion canonicalizes from now on; this clears what is already stored.
    Dry run by default, and the response lists every rename it would make.
    """
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from app.tasks.maintenance_tasks import normalize_city_names
    task = normalize_city_names.apply_async(
        kwargs={"apply": apply, "batch_size": batch_size}, queue="maintenance"
    )
    return {"status": "dispatched", "task_id": task.id, "apply": apply}


@router.post("/normalize-boston-cities")
async def normalize_boston_cities():
    """One-shot fix for Boston listings tagged with a neighbourhood name.

    apartments.com labels Boston listings Allston, Brighton, Dorchester, East
    Boston, Jamaica Plain and so on — all legally City of Boston. Unlike NYC
    this can't be keyed on zip, because 021xx also covers Brookline, Cambridge
    and Somerville, which are separate cities with different rents. Keyed on the
    neighbourhood name instead; the scraper does the same on write.

    Comps keyed on `city` otherwise compute a separate median for Allston as
    though it were its own market.
    """
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from app.tasks.maintenance_tasks import backfill_boston_city_normalization
    task = backfill_boston_city_normalization.apply_async(queue="maintenance")
    return {"status": "dispatched", "task_id": task.id}


@router.post("/reset-false-verifications")
async def reset_false_verifications(apply: bool = Query(False)):
    """One-shot cleanup for listings marked verified by the old verify logic.

    `_verify_listing` used to treat any response that wasn't a 404 or a
    200-with-removal-text as proof the listing was live. apartments.com is
    Akamai-fenced and 403s automated requests, so that certified rows alive
    *because* we were blocked. The deactivation guard skips anything marked
    "verified", which left those rows permanently immune to expiry — they sit
    at is_active=1 with freshness_confidence=0, invisible to search but counted
    in /stats, forever.

    The verify logic is fixed going forward; this clears the bad rows it left
    behind. Setting verification_status back to NULL does not deactivate
    anything — it only makes those listings eligible to expire normally again,
    which under current decay rates takes 12-23 days of not being re-seen.

    Defaults to a dry run. Pass ?apply=true to write.
    """
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from sqlalchemy import select, func, update
    from app.models.apartment import ApartmentModel
    from app.database import get_session_context

    try:
        async with get_session_context() as session:
            affected = (
                await session.execute(
                    select(func.count()).select_from(ApartmentModel).where(
                        ApartmentModel.verification_status == "verified"
                    )
                )
            ).scalar() or 0

            # These are the ones the bug was actively protecting: verified, yet
            # decayed to nothing. A genuinely re-seen listing sits at 100.
            immune = (
                await session.execute(
                    select(func.count()).select_from(ApartmentModel).where(
                        ApartmentModel.verification_status == "verified",
                        ApartmentModel.freshness_confidence == 0,
                        ApartmentModel.is_active == 1,
                    )
                )
            ).scalar() or 0

            if not apply:
                return {
                    "status": "dry_run",
                    "would_reset": affected,
                    "of_which_immune_to_expiry": immune,
                    "hint": "re-run with ?apply=true to write",
                }

            await session.execute(
                update(ApartmentModel)
                .where(ApartmentModel.verification_status == "verified")
                .values(verification_status=None, verified_at=None)
            )
            await session.commit()

        logger.info(f"Reset {affected} false verification_status rows")
        return {
            "status": "applied",
            "reset": affected,
            "of_which_immune_to_expiry": immune,
        }

    except Exception as e:
        logger.exception(f"reset-false-verifications failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/listings")
async def delete_all_listings():
    """Delete all apartment listings. Use with caution — dev/testing only."""
    if not is_database_enabled():
        raise HTTPException(status_code=503, detail="Database not enabled")

    from sqlalchemy import text
    from app.database import get_session_context

    async with get_session_context() as session:
        r = await session.execute(text("SELECT COUNT(*) FROM apartments"))
        count = r.scalar()
        await session.execute(text("DELETE FROM apartments"))
        await session.commit()

    return {"status": "deleted", "count": count}
