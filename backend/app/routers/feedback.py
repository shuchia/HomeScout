"""Beta feedback endpoint."""
import logging
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, UserContext
from app.services.tier_service import supabase_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class FeedbackRequest(BaseModel):
    type: str = Field(..., pattern="^(bug|suggestion|general)$")
    message: str = Field(..., min_length=1, max_length=5000)
    screenshot_url: str | None = None
    page_url: str | None = None


class FeedbackResponse(BaseModel):
    success: bool
    message: str


@router.post("/api/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    user: UserContext = Depends(get_current_user),
):
    """Submit beta feedback."""
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        supabase_admin.table("beta_feedback").insert({
            "user_id": user.user_id,
            "type": body.type,
            "message": body.message,
            "screenshot_url": body.screenshot_url,
            "page_url": body.page_url,
            "metadata": {
                "email": user.email,
            },
        }).execute()

        logger.info(f"Feedback submitted by {user.user_id}: {body.type}")
        return FeedbackResponse(success=True, message="Thanks for your feedback!")
    except Exception as e:
        logger.error(f"Failed to submit feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit feedback")
