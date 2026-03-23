from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import date, time


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
    match_score: Optional[int] = Field(None, ge=0, le=100)
    reasoning: Optional[str] = None
    highlights: List[str] = Field(default_factory=list)
    heuristic_score: Optional[int] = Field(None, ge=0, le=100)
    match_label: Optional[str] = None

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


class SearchContext(BaseModel):
    """Search criteria context for comparison scoring."""
    city: str
    budget: int
    bedrooms: int
    bathrooms: int
    property_type: str
    move_in_date: str


class CategoryScore(BaseModel):
    """Score and note for a single comparison category."""
    score: int = Field(..., ge=0, le=100)
    note: str


class ApartmentComparisonScore(BaseModel):
    """Detailed comparison scoring for one apartment."""
    apartment_id: str
    overall_score: int = Field(..., ge=0, le=100)
    reasoning: str
    highlights: List[str]
    category_scores: dict[str, CategoryScore]


class ComparisonWinner(BaseModel):
    """The winning apartment and why."""
    apartment_id: str
    reason: str


class ComparisonAnalysis(BaseModel):
    """Full comparison analysis returned by Claude."""
    winner: ComparisonWinner
    categories: List[str]
    apartment_scores: List[ApartmentComparisonScore]


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
                "message": "Snugd API is running"
            }
        }


class CompareRequest(BaseModel):
    """Request model for apartment comparison."""
    apartment_ids: List[str] = Field(..., max_length=3)
    preferences: Optional[str] = Field(None, description="User preferences for scoring")
    search_context: Optional[SearchContext] = Field(None, description="Original search criteria")

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
    comparison_analysis: Optional[ComparisonAnalysis] = None

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


# ── Tour Pipeline Schemas ─────────────────────────────────────────────

VALID_TOUR_STAGES = {"interested", "outreach_sent", "scheduled", "toured", "deciding"}
VALID_TOUR_DECISIONS = {"applied", "passed"}


class CreateTourRequest(BaseModel):
    """Request model to add an apartment to the tour pipeline."""
    apartment_id: str


class UpdateTourRequest(BaseModel):
    """Request model to update a tour pipeline entry."""
    stage: Optional[str] = None
    scheduled_date: Optional[date] = None
    scheduled_time: Optional[time] = None
    tour_rating: Optional[int] = None
    decision: Optional[str] = None
    decision_reason: Optional[str] = None

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_TOUR_STAGES:
            raise ValueError(f"Invalid stage '{v}'. Must be one of: {', '.join(sorted(VALID_TOUR_STAGES))}")
        return v

    @field_validator("tour_rating")
    @classmethod
    def validate_tour_rating(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 5):
            raise ValueError("tour_rating must be between 1 and 5")
        return v

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_TOUR_DECISIONS:
            raise ValueError(f"Invalid decision '{v}'. Must be one of: {', '.join(sorted(VALID_TOUR_DECISIONS))}")
        return v


class NoteResponse(BaseModel):
    """Response model for a tour note."""
    id: str
    content: Optional[str] = None
    source: str
    transcription_status: Optional[str] = None
    created_at: str


class PhotoResponse(BaseModel):
    """Response model for a tour photo."""
    id: str
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = None
    created_at: str


class TagResponse(BaseModel):
    """Response model for a tour tag."""
    id: str
    tag: str
    sentiment: str


class CreateNoteRequest(BaseModel):
    """Request model to add a typed note to a tour."""
    content: str = Field(..., min_length=1)


class CreatePhotoRequest(BaseModel):
    """Request model to add a photo entry to a tour."""
    s3_key: str
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = None


class UpdatePhotoRequest(BaseModel):
    """Request model to update a photo caption."""
    caption: str


class CreateTagRequest(BaseModel):
    """Request model to add a pro/con tag to a tour."""
    tag: str = Field(..., min_length=1, max_length=100)
    sentiment: str

    @field_validator("sentiment")
    @classmethod
    def validate_sentiment(cls, v: str) -> str:
        if v not in ("pro", "con"):
            raise ValueError("sentiment must be 'pro' or 'con'")
        return v


class TagSuggestion(BaseModel):
    """A suggested tag with usage count."""
    tag: str
    sentiment: str
    count: int


class InquiryEmailResponse(BaseModel):
    """Response model for a generated inquiry email."""
    subject: str
    body: str


class InquiryEmailRequest(BaseModel):
    """Optional request body for inquiry email generation."""
    name: Optional[str] = None
    move_in_date: Optional[str] = None
    budget: Optional[int] = None
    preferences: Optional[str] = None


class DayPlanRequest(BaseModel):
    """Request model for generating a day plan."""
    date: date
    tour_ids: List[str]


class DayPlanResponse(BaseModel):
    """Response model for a generated day plan."""
    tours_ordered: List[dict]
    travel_notes: List[str]
    tips: List[str]


class EnhanceNoteRequest(BaseModel):
    """Request model for enhancing a tour note."""
    note_id: str


class EnhanceNoteResponse(BaseModel):
    """Response model for an enhanced tour note."""
    enhanced_text: str
    suggested_tags: List[dict]


class DecisionApartment(BaseModel):
    """AI analysis for a single toured apartment."""
    apartment_id: str
    ai_take: str
    strengths: List[str]
    concerns: List[str]


class Recommendation(BaseModel):
    """AI recommendation for which apartment to choose."""
    apartment_id: str
    reasoning: str


class DecisionBriefResponse(BaseModel):
    """Response model for a decision brief."""
    apartments: List[DecisionApartment]
    recommendation: Recommendation


class TourResponse(BaseModel):
    """Response model for a single tour pipeline entry."""
    id: str
    apartment_id: str
    stage: str
    inquiry_email_draft: Optional[str] = None
    outreach_sent_at: Optional[str] = None
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None
    tour_rating: Optional[int] = None
    toured_at: Optional[str] = None
    notes: List[NoteResponse] = Field(default_factory=list)
    photos: List[PhotoResponse] = Field(default_factory=list)
    tags: List[TagResponse] = Field(default_factory=list)
    decision: Optional[str] = None
    decision_reason: Optional[str] = None
    created_at: str
    updated_at: str
