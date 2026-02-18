"""
API endpoints for apartment detail and batch retrieval.
"""
import logging
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Body

from app.services.apartment_service import ApartmentService
from app.schemas import CompareRequest, CompareResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/apartments", tags=["Apartments"])

# Initialize the apartment service
_apartment_service = ApartmentService()


def _get_apartments_data() -> List[Dict]:
    """Get apartment data from the service."""
    # Access the cached JSON data directly for efficiency
    if _apartment_service._apartments_data is not None:
        return _apartment_service._apartments_data
    # Fallback: reload from JSON
    return _apartment_service._load_apartments_from_json()


@router.get("/{apartment_id}")
async def get_apartment(apartment_id: str) -> Dict[str, Any]:
    """
    Get a single apartment by its ID.

    Args:
        apartment_id: The unique identifier of the apartment

    Returns:
        The apartment data

    Raises:
        HTTPException: 404 if apartment not found
    """
    apartments = _get_apartments_data()

    for apt in apartments:
        if apt.get("id") == apartment_id:
            return apt

    raise HTTPException(status_code=404, detail=f"Apartment {apartment_id} not found")


@router.post("/batch")
async def get_apartments_batch(apartment_ids: List[str] = Body(..., max_length=50)) -> List[Dict[str, Any]]:
    """
    Get multiple apartments by their IDs.

    Args:
        apartment_ids: List of apartment IDs to retrieve

    Returns:
        List of apartments. For missing apartments, returns
        {"id": apartment_id, "is_available": False}
    """
    if not apartment_ids:
        return []

    apartments = _get_apartments_data()

    # Create a lookup map for efficiency
    apt_map = {apt.get("id"): apt for apt in apartments}

    result = []
    for aid in apartment_ids:
        if aid in apt_map:
            result.append(apt_map[aid])
        else:
            # Return a minimal object indicating the apartment is not available
            result.append({"id": aid, "is_available": False})

    return result


@router.post("/compare", response_model=CompareResponse)
async def compare_apartments(request: CompareRequest) -> CompareResponse:
    """
    Compare up to 3 apartments with optional preference scoring.

    Args:
        request: CompareRequest with apartment_ids and optional preferences

    Returns:
        CompareResponse with apartment data and comparison fields
    """
    comparison_fields = [
        "rent", "bedrooms", "bathrooms", "sqft",
        "property_type", "amenities", "available_date", "neighborhood"
    ]

    if not request.apartment_ids:
        return CompareResponse(apartments=[], comparison_fields=comparison_fields)

    # Fetch apartments
    apartments_data = _get_apartments_data()
    apt_map = {apt.get("id"): apt for apt in apartments_data}

    apartments = []
    for aid in request.apartment_ids:
        if aid in apt_map:
            apartments.append(apt_map[aid])

    # Note: Claude scoring for preferences is optional for now
    # Can be added when preferences are provided

    return CompareResponse(apartments=apartments, comparison_fields=comparison_fields)
