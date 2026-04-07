"""
API endpoints for apartment detail and batch retrieval.
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Body, Query

from app.auth import get_optional_user, UserContext
from app.services.apartment_service import ApartmentService
from app.services.tier_service import TierService
from app.services.analytics_service import AnalyticsService
from app.schemas import CompareRequest, CompareResponse
from app.database import is_database_enabled, get_session_context
from app.services.cost_estimator import CostEstimator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/apartments", tags=["Apartments"])

# Initialize the apartment service
_apartment_service = ApartmentService()

_cost_estimator = CostEstimator()

# Lazy singleton for ClaudeService — avoids re-creating Anthropic client per request
_claude_service = None

def _get_claude_service():
    global _claude_service
    if _claude_service is None:
        from app.services.claude_service import ClaudeService
        _claude_service = ClaudeService()
    return _claude_service


def _add_cost_breakdown(apartment: dict, include_breakdown: bool) -> dict:
    """Add true cost fields to apartment dict. Full breakdown only if include_breakdown=True."""
    if apartment.get("true_cost_monthly") is None and apartment.get("rent"):
        breakdown = _cost_estimator.compute_true_cost(
            rent=apartment["rent"],
            zip_code=apartment.get("zip_code"),
            bedrooms=apartment.get("bedrooms", 1),
            amenities=apartment.get("amenities", []),
            scraped_fees={
                "pet_rent": apartment.get("pet_rent"),
                "parking_fee": apartment.get("parking_fee"),
                "amenity_fee": apartment.get("amenity_fee"),
                "application_fee": apartment.get("application_fee"),
                "admin_fee": apartment.get("admin_fee"),
                "security_deposit": apartment.get("security_deposit"),
                "other_monthly_fees": apartment.get("other_monthly_fees"),
            },
        )
        apartment["true_cost_monthly"] = breakdown["true_cost_monthly"]
        apartment["true_cost_move_in"] = breakdown["true_cost_move_in"]
        if include_breakdown:
            apartment["cost_breakdown"] = breakdown
    elif include_breakdown and apartment.get("true_cost_monthly"):
        apartment["cost_breakdown"] = {
            "base_rent": apartment["rent"],
            "pet_rent": apartment.get("pet_rent") or 0,
            "parking_fee": apartment.get("parking_fee") or 0,
            "amenity_fee": apartment.get("amenity_fee") or 0,
            "other_monthly_fees": apartment.get("other_monthly_fees") or 0,
            "est_electric": apartment.get("est_electric") or 0,
            "est_gas": apartment.get("est_gas") or 0,
            "est_water": apartment.get("est_water") or 0,
            "est_internet": apartment.get("est_internet") or 0,
            "est_renters_insurance": apartment.get("est_renters_insurance") or 0,
            "est_laundry": apartment.get("est_laundry") or 0,
            "application_fee": apartment.get("application_fee") or 0,
            "admin_fee": apartment.get("admin_fee") or 0,
            "security_deposit": apartment.get("security_deposit") or 0,
            "sources": _build_sources(apartment),
        }
    return apartment


def _build_sources(apartment: dict) -> dict:
    scraped = [k for k in ("pet_rent", "parking_fee", "amenity_fee", "other_monthly_fees",
                           "application_fee", "admin_fee", "security_deposit") if apartment.get(k)]
    estimated = [
        f"est_{k}" for k in ("electric", "gas", "water", "internet", "renters_insurance", "laundry")
        if apartment.get(f"est_{k}")
    ]
    included_map = apartment.get("utilities_included") or {}
    included = [k for k, v in included_map.items() if v]
    return {"scraped": scraped, "estimated": estimated, "included": included}


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
            conditions = [ApartmentModel.is_active == 1, ApartmentModel.freshness_confidence >= 40]

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
            apartments = [apt.to_summary_dict() for apt in result.scalars()]

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
    if is_database_enabled():
        from sqlalchemy import select
        from app.models.apartment import ApartmentModel
        async with get_session_context() as session:
            result = await session.execute(
                select(ApartmentModel).where(ApartmentModel.id == apartment_id)
            )
            apt = result.scalar_one_or_none()
            if apt:
                return apt.to_dict()
            raise HTTPException(status_code=404, detail=f"Apartment {apartment_id} not found")

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

    if is_database_enabled():
        from sqlalchemy import select
        from app.models.apartment import ApartmentModel
        async with get_session_context() as session:
            stmt = select(ApartmentModel).where(ApartmentModel.id.in_(apartment_ids))
            db_result = await session.execute(stmt)
            apt_map = {apt.id: apt.to_dict() for apt in db_result.scalars()}
            result = []
            for aid in apartment_ids:
                if aid in apt_map:
                    result.append(apt_map[aid])
                else:
                    result.append({"id": aid, "is_available": False})
            return result

    apartments = _get_apartments_data()
    apt_map = {apt.get("id"): apt for apt in apartments}
    result = []
    for aid in apartment_ids:
        if aid in apt_map:
            result.append(apt_map[aid])
        else:
            result.append({"id": aid, "is_available": False})
    return result


@router.post("/compare")
async def compare_apartments(
    request: CompareRequest,
    user: UserContext | None = Depends(get_optional_user),
):
    """
    Compare up to 3 apartments with optional preference scoring.
    When preferences are provided, Claude performs a deep head-to-head analysis.
    Claude analysis is only available for pro-tier users.
    """
    comparison_fields = [
        "rent", "bedrooms", "bathrooms", "sqft",
        "property_type", "amenities", "available_date", "neighborhood"
    ]

    if not request.apartment_ids:
        if not user:
            tier = "anonymous"
        else:
            tier = await TierService.get_user_tier(user.user_id)
        return {
            "apartments": [],
            "comparison_fields": comparison_fields,
            "comparison_analysis": None,
            "tier": tier,
        }

    # Determine user tier
    tier = "anonymous"
    if user:
        tier = await TierService.get_user_tier(user.user_id)

    # Fetch apartments from database or JSON
    apartments = []
    if is_database_enabled():
        from sqlalchemy import select
        from app.models.apartment import ApartmentModel
        async with get_session_context() as session:
            stmt = select(ApartmentModel).where(ApartmentModel.id.in_(request.apartment_ids))
            db_result = await session.execute(stmt)
            apt_map = {apt.id: apt.to_dict() for apt in db_result.scalars()}
            for aid in request.apartment_ids:
                if aid in apt_map:
                    apartments.append(apt_map[aid])
    else:
        apartments_data = _get_apartments_data()
        apt_map = {apt.get("id"): apt for apt in apartments_data}
        for aid in request.apartment_ids:
            if aid in apt_map:
                apartments.append(apt_map[aid])

    # Run Claude comparison analysis only for pro-tier users with at least 2 apartments
    comparison_analysis = None
    if tier == "pro" and len(apartments) >= 2:
        from app.services.claude_service import ClaudeService

        claude = _get_claude_service()
        search_ctx = request.search_context.model_dump() if request.search_context else None
        prefs = request.preferences.strip() if request.preferences else "general comparison"

        try:
            from app.services.apartment_service import _claude_semaphore
            async with _claude_semaphore:
                raw_analysis = await asyncio.wait_for(
                    asyncio.to_thread(
                        claude.compare_apartments_with_analysis,
                        apartments=apartments,
                        preferences=prefs,
                        search_context=search_ctx,
                    ),
                    timeout=45.0,
                )
            from app.schemas import ComparisonAnalysis
            comparison_analysis = ComparisonAnalysis(**raw_analysis)
        except asyncio.TimeoutError:
            logger.warning("Claude comparison timed out after 25s")
        except Exception as e:
            logger.error(f"Claude comparison analysis failed: {e}")

    # Add true cost data to apartments
    is_pro = tier == "pro"
    for i, apt in enumerate(apartments):
        apartments[i] = _add_cost_breakdown(apt, include_breakdown=is_pro)

    await AnalyticsService.log_event(
        "compare",
        user_id=user.user_id if user else None,
        metadata={"apartment_count": len(request.apartment_ids), "used_ai": tier == "pro"},
    )

    return {
        "apartments": apartments,
        "comparison_fields": comparison_fields,
        "comparison_analysis": comparison_analysis,
        "tier": tier,
    }
