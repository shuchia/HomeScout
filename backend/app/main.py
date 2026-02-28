"""
FastAPI application for HomeScout API.
"""
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import logging

from app.schemas import (
    SearchRequest,
    SearchResponse,
    HealthResponse,
    ApartmentWithScore
)
from app.services.apartment_service import ApartmentService
from app.services.tier_service import TierService
from app.services.analytics_service import AnalyticsService
from app.auth import get_optional_user, UserContext
from app.routers.data_collection import router as data_collection_router
from app.routers.apartments import router as apartments_router
from app.routers.webhooks import router as webhooks_router
from app.routers.billing import router as billing_router
from app.routers.saved_searches import router as saved_searches_router
from app.database import is_database_enabled, init_db, close_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info("Starting HomeScout API...")

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
    logger.info("Shutting down HomeScout API...")
    if is_database_enabled():
        await close_db()


# Initialize FastAPI app
app = FastAPI(
    title="HomeScout API",
    description="API for finding apartments tailored to young professionals",
    version="1.0.0",
    lifespan=lifespan
)

# Rate limiting (added first so CORS wraps it — Starlette runs middleware
# in reverse order of addition, so the last-added middleware runs first)
from app.middleware.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# Configure CORS (added last = runs first = wraps all responses with CORS headers)
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers (apartments_router registered later to avoid route conflicts)
app.include_router(data_collection_router)
app.include_router(webhooks_router)
app.include_router(billing_router)
app.include_router(saved_searches_router)

# Initialize services
apartment_service = ApartmentService()


@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint - basic health check"""
    return HealthResponse(
        status="healthy",
        message="HomeScout API is running. Visit /docs for API documentation."
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        message="HomeScout API is healthy and ready to serve requests"
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
        if tier == "pro":
            # Full Claude AI-scored search
            top_apartments, total_count = await apartment_service.get_top_apartments(
                city=request.city,
                budget=request.budget,
                bedrooms=request.bedrooms,
                bathrooms=request.bathrooms,
                property_type=request.property_type,
                move_in_date=request.move_in_date,
                other_preferences=request.other_preferences,
                top_n=10,
            )
            apartments_out = [
                ApartmentWithScore(**apt) for apt in top_apartments
            ]
        else:
            # Free / anonymous: heuristic score and rank
            from app.services.scoring_service import ScoringService

            filtered = await apartment_service.search_apartments(
                city=request.city,
                budget=request.budget,
                bedrooms=request.bedrooms,
                bathrooms=request.bathrooms,
                property_type=request.property_type,
                move_in_date=request.move_in_date,
            )
            scored = ScoringService.score_apartments_list(
                apartments=filtered,
                budget=request.budget,
                bedrooms=request.bedrooms,
                bathrooms=request.bathrooms,
                other_preferences=request.other_preferences,
            )
            total_count = len(scored)
            apartments_out = [
                {
                    **apt,
                    "match_score": None,
                    "reasoning": None,
                    "highlights": [],
                }
                for apt in scored[:10]
            ]

        # ── Increment counter for free users (after successful search) ──
        if tier == "free":
            await TierService.increment_search_count(user.user_id)
            # remaining decreases by 1 after this search
            searches_remaining = max(0, searches_remaining - 1)

        await AnalyticsService.log_event(
            "search",
            user_id=user.user_id if user else None,
            metadata={"city": request.city, "tier": tier, "result_count": len(apartments_out)},
        )

        return {
            "apartments": apartments_out,
            "total_results": total_count,
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
