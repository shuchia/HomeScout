"""Waitlist signup endpoint (no auth required)."""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.tier_service import supabase_admin

logger = logging.getLogger(__name__)
router = APIRouter()


class WaitlistRequest(BaseModel):
    email: str
    name: str | None = None
    referral_source: str | None = None


@router.post("/api/waitlist", status_code=201)
async def join_waitlist(body: WaitlistRequest):
    """Add email to the waitlist. No auth required."""
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Service unavailable")

    try:
        result = supabase_admin.table("waitlist").insert({
            "email": body.email.lower().strip(),
            "name": body.name,
            "referral_source": body.referral_source,
        }).execute()

        return {"message": "You're on the list!", "email": body.email}
    except Exception as e:
        error_msg = str(e)
        if "duplicate" in error_msg.lower() or "unique" in error_msg.lower():
            return {"message": "You're already on the list!", "email": body.email}
        logger.error(f"Waitlist signup failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to join waitlist")


@router.get("/api/admin/waitlist")
async def list_waitlist():
    """List all waitlist signups. Admin only (relies on network-level auth for now)."""
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Service unavailable")

    result = supabase_admin.table("waitlist") \
        .select("*") \
        .order("created_at", desc=True) \
        .execute()

    return {"signups": result.data or [], "total": len(result.data or [])}
