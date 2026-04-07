"""
FastAPI application for Snugd API.
"""
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import logging

import asyncio
import hashlib
import json

from app.schemas import (
    SearchRequest,
    SearchResponse,
    HealthResponse,
    ApartmentWithScore,
    ScoreBatchRequest,
)
from app.services.apartment_service import ApartmentService
from app.services.tier_service import TierService
from app.services.analytics_service import AnalyticsService
from app.auth import get_current_user, get_optional_user, UserContext
from app.routers.data_collection import router as data_collection_router
from app.routers.apartments import router as apartments_router
from app.routers.webhooks import router as webhooks_router
from app.routers.billing import router as billing_router
from app.routers.saved_searches import router as saved_searches_router
from app.routers.tours import router as tours_router
from app.routers.invite import router as invite_router
from app.routers.feedback import router as feedback_router
from app.routers.waitlist import router as waitlist_router
from app.database import is_database_enabled, init_db, close_db

# Configure logging
from app.logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info("Starting Snugd API...")

    if is_database_enabled():
        logger.info("Database enabled - initializing connection")
        try:
            await init_db()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.warning(f"Database initialization failed: {e}")
            logger.info("Continuing with JSON fallback mode")
    else:
        logger.info("Using JSON data fallback (DATABASE_URL not configured)")

    yield

    # Shutdown
    logger.info("Shutting down Snugd API...")
    if is_database_enabled():
        await close_db()


# Initialize FastAPI app
app = FastAPI(
    title="Snugd API",
    description="API for finding apartments tailored to young professionals",
    version="1.0.0",
    lifespan=lifespan
)

# GZip compression for responses > 1KB
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Rate limiting (added first so CORS wraps it — Starlette runs middleware
# in reverse order of addition, so the last-added middleware runs first)
from app.middleware.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# Configure CORS (added last = runs first = wraps all responses with CORS headers)
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
cors_origins = [frontend_url]
if "localhost" not in frontend_url:
    # In deployed environments, also allow localhost for development
    cors_origins.append("http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers (apartments_router registered later to avoid route conflicts)
app.include_router(data_collection_router)
app.include_router(webhooks_router)
app.include_router(billing_router)
app.include_router(saved_searches_router)
app.include_router(tours_router)
app.include_router(invite_router)
app.include_router(feedback_router)
app.include_router(waitlist_router)

# Initialize services
apartment_service = ApartmentService()


@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint - basic health check"""
    return HealthResponse(
        status="healthy",
        message="Snugd API is running. Visit /docs for API documentation."
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        message="Snugd API is healthy and ready to serve requests"
    )


@app.get("/api/apartments/count")
async def get_apartment_count():
    """Get total number of apartments in the database"""
    count = await apartment_service.get_apartment_count_async()
    return {
        "total_apartments": count,
        "message": f"Currently tracking {count} apartments across multiple cities"
    }


@app.get("/api/apartments/stats")
async def get_apartment_stats():
    """Get apartment listing statistics"""
    try:
        stats = await apartment_service.get_listing_stats_async()
        return {
            "status": "success",
            "stats": stats
        }
    except Exception as e:
        logger.exception(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search")
async def search_apartments(
    request: SearchRequest,
    user: UserContext | None = Depends(get_optional_user),
):
    """
    Search for apartments based on user preferences.

    Behaviour varies by user tier:
    - **pro** (authenticated + paid): full Claude AI-scored results.
    - **free** (authenticated, no subscription): filtered results without AI
      scoring, limited to FREE_DAILY_SEARCH_LIMIT searches per day.
    - **anonymous** (no auth token): filtered results without AI scoring,
      no daily limit tracking.

    Returns a dict with apartments, total_results, tier, and
    searches_remaining (null for pro/anonymous).
    """
    # ── Determine tier ──────────────────────────────────────────────
    if user is None:
        tier = "anonymous"
    else:
        tier = await TierService.get_user_tier(user.user_id)

    # ── Enforce daily limit for free users ──────────────────────────
    searches_remaining: int | None = None
    if tier == "free":
        allowed, remaining = await TierService.check_search_limit(user.user_id)
        searches_remaining = remaining
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Daily search limit reached. Upgrade to Pro for unlimited searches.",
            )

    try:
        page_results, total_count, has_more = await apartment_service.get_apartments_paginated(
            city=request.city,
            budget=request.budget,
            bedrooms=request.bedrooms,
            bathrooms=request.bathrooms,
            property_type=request.property_type,
            move_in_date=request.move_in_date,
            other_preferences=request.other_preferences,
            page=request.page,
            page_size=request.page_size,
        )

        # Set heuristic scores, null out AI fields (AI backfilled by score-batch)
        apartments_out = [
            {
                **apt,
                "match_score": None,
                "reasoning": None,
                "highlights": [],
            }
            for apt in page_results
        ]

        # Increment counter for free users (only on page 1)
        if tier == "free" and request.page == 1:
            await TierService.increment_search_count(user.user_id)
            searches_remaining = max(0, searches_remaining - 1)

        # Apply proximity distances
        from app.services.distance import add_distances

        if request.near_lat is not None and request.near_lng is not None:
            result_dicts = []
            for apt in apartments_out:
                if isinstance(apt, dict):
                    result_dicts.append(apt)
                elif hasattr(apt, 'model_dump'):
                    result_dicts.append(apt.model_dump())
                else:
                    result_dicts.append(apt.__dict__)

            max_dist = request.max_distance_miles if tier == "pro" else None
            result_dicts = add_distances(result_dicts, request.near_lat, request.near_lng, max_dist)
            apartments_out = result_dicts
            if max_dist:
                total_count = len(result_dicts)
                has_more = False

        # Add true cost data (breakdown sent to all users — fee data is public)
        from app.routers.apartments import _add_cost_breakdown
        final_apartments = []
        for apt in apartments_out:
            apt_dict = apt if isinstance(apt, dict) else apt.model_dump() if hasattr(apt, 'model_dump') else apt.__dict__
            apt_dict = _add_cost_breakdown(apt_dict, include_breakdown=True)
            final_apartments.append(apt_dict)
        apartments_out = final_apartments

        await AnalyticsService.log_event(
            "search",
            user_id=user.user_id if user else None,
            metadata={"city": request.city, "tier": tier, "result_count": len(apartments_out)},
        )

        return {
            "apartments": apartments_out,
            "total_results": total_count,
            "page": request.page,
            "has_more": has_more,
            "tier": tier,
            "searches_remaining": searches_remaining,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Error in search endpoint: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while searching for apartments: {str(e)}",
        )


@app.post("/api/search/score-batch")
async def score_batch(
    request: ScoreBatchRequest,
    user: UserContext = Depends(get_current_user),
):
    """Score a batch of apartments using Claude AI. Pro only."""
    tier = await TierService.get_user_tier(user.user_id)
    if tier != "pro":
        raise HTTPException(status_code=403, detail="AI scoring requires a Pro subscription.")

    if len(request.apartment_ids) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 apartments per batch.")

    try:
        # Fetch apartment data by IDs
        apartments = await apartment_service.get_apartments_by_ids(request.apartment_ids)
        if not apartments:
            return {"scores": []}

        # Check cache
        ids_key = ",".join(sorted(request.apartment_ids))
        ctx = request.search_context
        raw = f"{ids_key}:{ctx.city}:{ctx.budget}:{ctx.bedrooms}:{ctx.bathrooms}:{ctx.property_type}:{ctx.move_in_date}"
        cache_key = f"score_batch:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

        if apartment_service._redis:
            try:
                cached = await apartment_service._redis.get(cache_key)
                if cached:
                    return {"scores": json.loads(cached)}
            except Exception:
                pass

        # Call Claude
        from app.services.claude_service import ClaudeService
        claude = ClaudeService()

        scores = await asyncio.to_thread(
            claude.score_apartments,
            city=ctx.city,
            budget=ctx.budget,
            bedrooms=ctx.bedrooms,
            bathrooms=ctx.bathrooms,
            property_type=ctx.property_type,
            move_in_date=ctx.move_in_date,
            other_preferences="",
            apartments=apartments,
        )

        # Cache for 1 hour
        if apartment_service._redis:
            try:
                await apartment_service._redis.setex(cache_key, 3600, json.dumps(scores))
            except Exception:
                pass

        return {"scores": scores}

    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"Score batch failed: {e}")
        return {"scores": []}


@app.get("/metrics")
async def get_metrics():
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus text format.
    """
    try:
        from app.services.monitoring.metrics import get_metrics_service

        metrics_service = get_metrics_service()
        metrics_data = metrics_service.get_metrics()

        if metrics_data:
            return Response(
                content=metrics_data,
                media_type=metrics_service.get_content_type()
            )
        else:
            return Response(
                content="# Metrics not available\n",
                media_type="text/plain"
            )

    except Exception as e:
        logger.warning(f"Error getting metrics: {e}")
        return Response(
            content=f"# Error: {e}\n",
            media_type="text/plain"
        )


# Optional: Add a test endpoint for development
@app.post("/api/test")
async def test_endpoint(data: dict):
    """Test endpoint for development - echoes back the request"""
    return {
        "received": data,
        "message": "Test endpoint working",
        "database_enabled": is_database_enabled()
    }


# Register apartments router AFTER specific routes to avoid /{apartment_id} capturing /count and /stats
app.include_router(apartments_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
