from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


class SearchRequest(BaseModel):
    """Request model for apartment search"""
    city: str = Field(..., description="City to search in (e.g., 'San Francisco, CA')")
    budget: int = Field(..., gt=0, description="Maximum monthly rent budget")
    bedrooms: int = Field(..., ge=0, description="Number of bedrooms needed")
    bathrooms: int = Field(..., ge=0, description="Number of bathrooms needed")
    property_type: str = Field(..., description="Comma-separated property types (e.g., 'Apartment, Condo')")
    move_in_date: str = Field(..., description="Desired move-in date (YYYY-MM-DD format)")
    other_preferences: Optional[str] = Field(None, description="Additional preferences and requirements")

    class Config:
        json_schema_extra = {
            "example": {
                "city": "San Francisco, CA",
                "budget": 3500,
                "bedrooms": 2,
                "bathrooms": 2,
                "property_type": "Apartment, Condo",
                "move_in_date": "2025-12-01",
                "other_preferences": "Must have in-unit washer/dryer, parking, pet-friendly for a small dog"
            }
        }


class Apartment(BaseModel):
    """Model for apartment listing"""
    id: str
    address: str
    rent: int
    bedrooms: int
    bathrooms: int
    sqft: int
    property_type: str
    available_date: str
    amenities: List[str]
    neighborhood: str
    description: str
    images: List[str]

    class Config:
        json_schema_extra = {
            "example": {
                "id": "apt-001",
                "address": "123 Market St, San Francisco, CA 94103",
                "rent": 3400,
                "bedrooms": 2,
                "bathrooms": 2,
                "sqft": 1100,
                "property_type": "Apartment",
                "available_date": "2025-11-15",
                "amenities": ["In-unit laundry", "Parking", "Pet-friendly", "Gym"],
                "neighborhood": "SoMa",
                "description": "Modern luxury apartment in the heart of SoMa",
                "images": ["https://example.com/image1.jpg"]
            }
        }


class ApartmentScore(BaseModel):
    """Model for Claude AI's apartment scoring response"""
    apartment_id: str
    match_score: int = Field(..., ge=0, le=100, description="Match score from 0-100")
    reasoning: str = Field(..., description="1-2 sentence explanation of the score")
    highlights: List[str] = Field(..., description="2-3 key features that match preferences")

    class Config:
        json_schema_extra = {
            "example": {
                "apartment_id": "apt-001",
                "match_score": 92,
                "reasoning": "Nearly perfect match with rent under budget, all must-have amenities including in-unit laundry and parking.",
                "highlights": ["Under budget by $100/month", "All must-have amenities", "Modern building with gym"]
            }
        }


class ApartmentWithScore(Apartment):
    """Model combining apartment data with its match score"""
    match_score: int = Field(..., ge=0, le=100)
    reasoning: str
    highlights: List[str]

    class Config:
        json_schema_extra = {
            "example": {
                "id": "apt-001",
                "address": "123 Market St, San Francisco, CA 94103",
                "rent": 3400,
                "bedrooms": 2,
                "bathrooms": 2,
                "sqft": 1100,
                "property_type": "Apartment",
                "available_date": "2025-11-15",
                "amenities": ["In-unit laundry", "Parking", "Pet-friendly"],
                "neighborhood": "SoMa",
                "description": "Modern luxury apartment",
                "images": ["https://example.com/image1.jpg"],
                "match_score": 92,
                "reasoning": "Excellent match with all key requirements",
                "highlights": ["Under budget", "All amenities", "Great location"]
            }
        }


class SearchResponse(BaseModel):
    """Response model for apartment search"""
    apartments: List[ApartmentWithScore]
    total_results: int = Field(..., description="Total number of apartments returned")

    class Config:
        json_schema_extra = {
            "example": {
                "apartments": [],
                "total_results": 10
            }
        }


class HealthResponse(BaseModel):
    """Response model for health check endpoint"""
    status: str
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "message": "HomeScout API is running"
            }
        }


class CompareRequest(BaseModel):
    """Request model for apartment comparison."""
    apartment_ids: List[str] = Field(..., max_length=3)
    preferences: Optional[str] = Field(None, description="User preferences for scoring")

    class Config:
        json_schema_extra = {
            "example": {
                "apartment_ids": ["apt-001", "apt-002", "apt-003"],
                "preferences": "Looking for pet-friendly with in-unit laundry"
            }
        }


class CompareResponse(BaseModel):
    """Response model for apartment comparison."""
    apartments: List[Apartment]
    comparison_fields: List[str]

    class Config:
        json_schema_extra = {
            "example": {
                "apartments": [
                    {"id": "apt-001", "rent": 3400, "bedrooms": 2},
                    {"id": "apt-002", "rent": 3200, "bedrooms": 2}
                ],
                "comparison_fields": ["rent", "bedrooms", "bathrooms", "sqft", "property_type", "amenities", "available_date", "neighborhood"]
            }
        }
