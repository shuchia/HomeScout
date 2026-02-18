"""Webhook endpoints for Supabase Edge Functions."""
import hmac
import logging
import os
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Body, Request

from app.services.apartment_service import ApartmentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

WEBHOOK_SECRET = os.getenv("SUPABASE_WEBHOOK_SECRET", "test-secret")

_apartment_service = ApartmentService()


def verify_webhook(request: Request):
    """Verify webhook came from Supabase."""
    secret = request.headers.get("x-webhook-secret", "")
    if not hmac.compare_digest(secret, WEBHOOK_SECRET):
        logger.warning(
            "Webhook authentication failed: invalid secret from %s",
            request.client.host if request.client else "unknown"
        )
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


@router.post("/supabase/check-matches")
async def check_new_matches(
    request: Request,
    saved_search: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """
    Called by Supabase Edge Function to check for new apartment matches.

    Args:
        request: FastAPI request object for header access
        saved_search: Search criteria dict with fields:
            - city: City name to search
            - budget: Maximum rent
            - bedrooms: Number of bedrooms
            - bathrooms: Minimum bathrooms
            - last_checked_at: ISO timestamp to filter new listings

    Returns:
        Dict with "matches" (list of apartments) and "count" (number of matches)
    """
    verify_webhook(request)

    city = saved_search.get("city", "")
    budget = saved_search.get("budget")
    bedrooms = saved_search.get("bedrooms")
    bathrooms = saved_search.get("bathrooms")

    # Load apartments from JSON (database mode not implemented for MVP)
    apartments = _apartment_service._load_apartments_from_json()

    matches = []
    for apt in apartments:
        # City filter (partial match on address)
        if city.lower() not in apt.get("address", "").lower():
            continue
        # Budget filter
        if budget and apt.get("rent", 0) > budget:
            continue
        # Bedrooms filter (exact match)
        if bedrooms is not None and apt.get("bedrooms") != bedrooms:
            continue
        # Bathrooms filter (at least)
        if bathrooms is not None and apt.get("bathrooms", 0) < bathrooms:
            continue
        matches.append(apt)

    return {"matches": matches, "count": len(matches)}
