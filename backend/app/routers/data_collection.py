"""
Admin API endpoints for data collection management.
"""
import uuid
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends, Body
from pydantic import BaseModel, Field

from app.database import get_async_session, is_database_enabled, AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/data-collection", tags=["Data Collection"])


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
    """Response for collection metrics."""
    total_listings: int
    active_listings: int
    listings_by_source: dict
    listings_by_city: dict
    avg_quality_score: float
    jobs_last_24h: int
    successful_jobs_last_24h: int
    timestamp: str


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

    Args:
        request: Job configuration

    Returns:
        Job ID and status
    """
    job_id = str(uuid.uuid4())

    try:
        # Import celery task
        from app.tasks.scrape_tasks import scrape_source, scrape_city_task

        if request.city and request.state:
            # Single city scrape
            task = scrape_city_task.delay(
                source=request.source,
                city=request.city,
                state=request.state,
                max_listings=request.max_listings,
            )
        else:
            # Full source scrape
            task = scrape_source.delay(
                source=request.source,
                max_listings_per_city=request.max_listings,
            )

        return {
            "job_id": job_id,
            "task_id": task.id,
            "source": request.source,
            "status": "queued",
            "message": f"Scrape job queued for {request.source}",
        }

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
    """
    Get data collection metrics.

    Returns:
        Current metrics for data collection
    """
    default_metrics = MetricsResponse(
        total_listings=0,
        active_listings=0,
        listings_by_source={},
        listings_by_city={},
        avg_quality_score=0.0,
        jobs_last_24h=0,
        successful_jobs_last_24h=0,
        timestamp=datetime.utcnow().isoformat(),
    )

    if not is_database_enabled():
        return default_metrics

    try:
        from app.tasks.maintenance_tasks import generate_metrics_snapshot

        # Get metrics from task (sync call)
        result = generate_metrics_snapshot()

        if result.get("status") == "completed":
            metrics = result["metrics"]
            return MetricsResponse(**metrics)

        return default_metrics

    except Exception as e:
        logger.exception(f"Failed to get metrics: {e}")
        return default_metrics


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
