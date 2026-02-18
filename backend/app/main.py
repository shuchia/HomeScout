"""
FastAPI application for HomeScout API.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Response
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
from app.routers.data_collection import router as data_collection_router
from app.routers.apartments import router as apartments_router
from app.routers.webhooks import router as webhooks_router
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

# Configure CORS
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
    count = apartment_service.get_apartment_count()
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


@app.post("/api/search", response_model=SearchResponse)
async def search_apartments(request: SearchRequest):
    """
    Search for apartments based on user preferences.

    This endpoint:
    1. Filters apartments by basic criteria (city, budget, beds, baths, type, date)
    2. Uses Claude AI to score apartments based on preferences
    3. Returns top 10 matches ranked by score

    Returns:
        SearchResponse with top 10 apartment recommendations
    """
    try:
        # Get top apartments using the service
        top_apartments, total_count = apartment_service.get_top_apartments(
            city=request.city,
            budget=request.budget,
            bedrooms=request.bedrooms,
            bathrooms=request.bathrooms,
            property_type=request.property_type,
            move_in_date=request.move_in_date,
            other_preferences=request.other_preferences,
            top_n=10
        )

        # Convert to response models
        apartments_with_scores = [
            ApartmentWithScore(**apt) for apt in top_apartments
        ]

        return SearchResponse(
            apartments=apartments_with_scores,
            total_results=total_count
        )

    except ValueError as e:
        # Handle validation errors from services
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        # Handle unexpected errors
        logger.exception(f"Error in search endpoint: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while searching for apartments: {str(e)}"
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
