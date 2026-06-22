"""Lightweight bridge for client-side actions to log analytics events.

Server-side actions (tour-add, message-generated, redeem, compare, search)
already call AnalyticsService.log_event() at the relevant route. This
endpoint exists only for actions that happen entirely client-side
(favorites, future compare-add) where there's no other backend hook.

Event types are whitelisted to prevent the endpoint from becoming a
free-form analytics dump that anyone can pollute. Add to ALLOWED_EVENT_TYPES
when wiring a new client-side action.
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_user, UserContext
from app.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)

router = APIRouter()

# Whitelist. Server-side events (redeem, tour-add, message-generated,
# compare, search) are intentionally NOT here — they log at the route that
# performs the action, not through this bridge.
ALLOWED_EVENT_TYPES = {
    "favorite-add",
    "favorite-remove",
}


class EventRequest(BaseModel):
    event_type: str
    metadata: Optional[Dict[str, Any]] = None


@router.post("/api/analytics/event", status_code=202)
async def log_event(
    body: EventRequest,
    user: UserContext = Depends(get_current_user),
):
    """Log a client-originated analytics event. Fire-and-forget — never
    blocks the user's primary action. Returns 202 Accepted with no body."""
    if body.event_type not in ALLOWED_EVENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported event_type. Allowed: {sorted(ALLOWED_EVENT_TYPES)}",
        )

    await AnalyticsService.log_event(
        event_type=body.event_type,
        user_id=user.user_id,
        metadata=body.metadata or {},
    )
    return None
