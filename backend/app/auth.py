"""Supabase JWT verification for FastAPI."""
import os
import jwt
import logging
from dataclasses import dataclass
from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")


@dataclass
class UserContext:
    """Authenticated user context extracted from a Supabase JWT."""
    user_id: str
    email: str | None = None


def _decode_supabase_jwt(token: str) -> dict:
    """Decode and verify a Supabase JWT using the project's JWT secret."""
    return jwt.decode(
        token,
        SUPABASE_JWT_SECRET,
        algorithms=["HS256"],
        audience="authenticated",
    )


async def get_current_user(
    authorization: str | None = Header(None),
) -> UserContext:
    """FastAPI dependency: requires valid Supabase JWT. Returns UserContext.

    Use this as a dependency on endpoints that require authentication.
    Raises HTTP 401 if the token is missing, invalid, or expired.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = authorization.removeprefix("Bearer ")
    try:
        payload = _decode_supabase_jwt(token)
        return UserContext(
            user_id=payload["sub"],
            email=payload.get("email"),
        )
    except (jwt.InvalidTokenError, KeyError) as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_optional_user(
    authorization: str | None = Header(None),
) -> UserContext | None:
    """FastAPI dependency: returns UserContext if token present, None otherwise.

    Use this as a dependency on endpoints where auth is optional (e.g.,
    free-tier users get limited results, authenticated users get full results).
    Never raises on invalid tokens -- returns None instead.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ")
    try:
        payload = _decode_supabase_jwt(token)
        return UserContext(
            user_id=payload["sub"],
            email=payload.get("email"),
        )
    except (jwt.InvalidTokenError, KeyError):
        return None
