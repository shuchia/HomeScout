"""Invite code endpoints for beta access."""
import logging
import secrets
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, UserContext
from app.services.tier_service import supabase_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class RedeemRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)


class RedeemResponse(BaseModel):
    success: bool
    message: str
    expires_at: str | None = None


class InviteStatus(BaseModel):
    has_invite: bool
    expires_at: str | None = None


class GenerateCodesRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=50)
    max_uses: int = Field(default=1, ge=1, le=100)
    prefix: str = Field(default="BETA")
    expires_at: str | None = None


def _ensure_supabase():
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")


@router.post("/api/invite/redeem", response_model=RedeemResponse)
async def redeem_invite_code(
    body: RedeemRequest,
    user: UserContext = Depends(get_current_user),
):
    """Redeem an invite code to get Pro access for 90 days."""
    _ensure_supabase()
    code = body.code.strip().upper()

    result = supabase_admin.table("invite_codes").select("*").eq("code", code).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Invalid invite code")

    invite = result.data[0]

    if invite.get("expires_at"):
        expires = datetime.fromisoformat(invite["expires_at"].replace("Z", "+00:00"))
        if expires < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="This invite code has expired")

    if invite["times_used"] >= invite["max_uses"]:
        raise HTTPException(status_code=400, detail="This invite code has been fully used")

    existing = (
        supabase_admin.table("invite_redemptions")
        .select("id")
        .eq("code", code)
        .eq("user_id", user.user_id)
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=400, detail="You have already redeemed this code")

    pro_expires = datetime.now(timezone.utc) + timedelta(days=90)

    try:
        supabase_admin.table("profiles").update({
            "user_tier": "pro",
            "pro_expires_at": pro_expires.isoformat(),
        }).eq("id", user.user_id).execute()

        supabase_admin.table("invite_codes").update({
            "times_used": invite["times_used"] + 1,
        }).eq("code", code).execute()

        supabase_admin.table("invite_redemptions").insert({
            "code": code,
            "user_id": user.user_id,
        }).execute()

        logger.info(f"User {user.user_id} redeemed invite code {code}")
        return RedeemResponse(
            success=True,
            message="Welcome to Pro! Your access expires in 90 days.",
            expires_at=pro_expires.isoformat(),
        )
    except Exception as e:
        logger.error(f"Failed to redeem invite code: {e}")
        raise HTTPException(status_code=500, detail="Failed to redeem code")


@router.get("/api/invite/status", response_model=InviteStatus)
async def get_invite_status(
    user: UserContext = Depends(get_current_user),
):
    """Check if current user has an active invite-based Pro subscription."""
    _ensure_supabase()

    result = (
        supabase_admin.table("profiles")
        .select("user_tier, pro_expires_at")
        .eq("id", user.user_id)
        .single()
        .execute()
    )

    if not result.data:
        return InviteStatus(has_invite=False)

    profile = result.data
    if profile.get("pro_expires_at"):
        expires = datetime.fromisoformat(
            profile["pro_expires_at"].replace("Z", "+00:00")
        )
        if expires > datetime.now(timezone.utc) and profile.get("user_tier") == "pro":
            return InviteStatus(has_invite=True, expires_at=profile["pro_expires_at"])

    return InviteStatus(has_invite=False)


@router.post("/api/admin/invite-codes")
async def generate_invite_codes(body: GenerateCodesRequest):
    """Generate invite codes. No auth for now (admin-only by obscurity during beta)."""
    _ensure_supabase()

    codes = []
    for _ in range(body.count):
        code = f"{body.prefix}-{secrets.token_hex(3).upper()}"
        data = {
            "code": code,
            "max_uses": body.max_uses,
        }
        if body.expires_at:
            data["expires_at"] = body.expires_at
        supabase_admin.table("invite_codes").insert(data).execute()
        codes.append(code)

    return {"codes": codes}
