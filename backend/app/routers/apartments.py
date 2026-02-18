"""
API endpoints for apartment detail and batch retrieval.
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Body, Query

from app.services.apartment_service import ApartmentService
from app.schemas import CompareRequest, CompareResponse
from app.database import is_database_enabled, get_session_context

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


@router.get("/list")
async def list_apartments(
    city: Optional[str] = Query(None, description="Filter by city name (case-insensitive)"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    min_rent: Optional[int] = Query(None, ge=0, description="Minimum rent"),
    max_rent: Optional[int] = Query(None, ge=0, description="Maximum rent"),
    bedrooms: Optional[int] = Query(None, ge=0, description="Number of bedrooms"),
) -> Dict[str, Any]:
    """
    List apartments with optional filtering.

    Args:
        city: Filter by city name (case-insensitive partial match)
        limit: Maximum results to return (default 100, max 500)
        offset: Number of results to skip for pagination
        min_rent: Minimum rent filter
        max_rent: Maximum rent filter
        bedrooms: Filter by number of bedrooms

    Returns:
        Dict with apartments list and pagination info
    """
    if is_database_enabled():
        return await _list_from_database(city, limit, offset, min_rent, max_rent, bedrooms)
    else:
        return _list_from_json(city, limit, offset, min_rent, max_rent, bedrooms)


async def _list_from_database(
    city: Optional[str],
    limit: int,
    offset: int,
    min_rent: Optional[int],
    max_rent: Optional[int],
    bedrooms: Optional[int],
) -> Dict[str, Any]:
    """List apartments from PostgreSQL database."""
    from sqlalchemy import select, func
    from app.models.apartment import ApartmentModel

    try:
        async with get_session_context() as session:
            # Build base query
            conditions = [ApartmentModel.is_active == 1]

            if city:
                conditions.append(ApartmentModel.city.ilike(f"%{city}%"))
            if min_rent is not None:
                conditions.append(ApartmentModel.rent >= min_rent)
            if max_rent is not None:
                conditions.append(ApartmentModel.rent <= max_rent)
            if bedrooms is not None:
                conditions.append(ApartmentModel.bedrooms == bedrooms)

            # Get total count
            count_stmt = select(func.count(ApartmentModel.id)).where(*conditions)
            total_result = await session.execute(count_stmt)
            total = total_result.scalar()

            # Get apartments with pagination
            stmt = (
                select(ApartmentModel)
                .where(*conditions)
                .order_by(ApartmentModel.city, ApartmentModel.rent)
                .offset(offset)
                .limit(limit)
            )

            result = await session.execute(stmt)
            apartments = [apt.to_dict() for apt in result.scalars()]

            return {
                "apartments": apartments,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + len(apartments) < total,
            }

    except Exception as e:
        logger.exception(f"Error listing apartments from database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _list_from_json(
    city: Optional[str],
    limit: int,
    offset: int,
    min_rent: Optional[int],
    max_rent: Optional[int],
    bedrooms: Optional[int],
) -> Dict[str, Any]:
    """List apartments from JSON file (fallback mode)."""
    apartments = _get_apartments_data()

    # Apply filters
    filtered = []
    for apt in apartments:
        if city and city.lower() not in apt.get("city", "").lower():
            continue
        if min_rent is not None and apt.get("rent", 0) < min_rent:
            continue
        if max_rent is not None and apt.get("rent", 0) > max_rent:
            continue
        if bedrooms is not None and apt.get("bedrooms") != bedrooms:
            continue
        filtered.append(apt)

    # Sort by city and rent
    filtered.sort(key=lambda x: (x.get("city", ""), x.get("rent", 0)))

    total = len(filtered)
    paginated = filtered[offset : offset + limit]

    return {
        "apartments": paginated,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(paginated) < total,
    }


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
    When preferences are provided, Claude performs a deep head-to-head analysis.
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

    # If preferences provided, run Claude comparison analysis
    comparison_analysis = None
    if request.preferences and request.preferences.strip() and len(apartments) >= 2:
        from app.services.claude_service import ClaudeService

        claude = ClaudeService()
        search_ctx = request.search_context.model_dump() if request.search_context else None

        try:
            raw_analysis = await asyncio.to_thread(
                claude.compare_apartments_with_analysis,
                apartments=apartments,
                preferences=request.preferences,
                search_context=search_ctx,
            )
            from app.schemas import ComparisonAnalysis
            comparison_analysis = ComparisonAnalysis(**raw_analysis)
        except Exception as e:
            logger.error(f"Claude comparison analysis failed: {e}")
            # Return apartments without analysis on failure

    return CompareResponse(
        apartments=apartments,
        comparison_fields=comparison_fields,
        comparison_analysis=comparison_analysis,
    )
