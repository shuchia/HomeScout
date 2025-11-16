from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

from app.models import (
    SearchRequest,
    SearchResponse,
    HealthResponse,
    ApartmentWithScore
)
from app.services.apartment_service import ApartmentService

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="HomeScout API",
    description="API for finding apartments tailored to young professionals",
    version="1.0.0"
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
        print(f"Error in search endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while searching for apartments: {str(e)}"
        )


# Optional: Add a test endpoint for development
@app.post("/api/test")
async def test_endpoint(data: dict):
    """Test endpoint for development - echoes back the request"""
    return {
        "received": data,
        "message": "Test endpoint working"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
