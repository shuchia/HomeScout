"""Supabase JWT verification for FastAPI."""
import os
import jwt
import logging
import requests
from jwt import PyJWKClient
from dataclasses import dataclass
from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

# JWKS client for ES256 tokens (caches keys automatically)
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient | None:
    global _jwks_client
    if _jwks_client is None and SUPABASE_URL:
        jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        try:
            _jwks_client = PyJWKClient(jwks_url)
        except Exception as e:
            logger.error(f"Failed to initialize JWKS client: {e}")
    return _jwks_client


@dataclass
class UserContext:
    """Authenticated user context extracted from a Supabase JWT."""
    user_id: str
    email: str | None = None


def _decode_supabase_jwt(token: str) -> dict:
    """Decode and verify a Supabase JWT.

    Supports both:
    - ES256 tokens (signed with ECDSA key pair, verified via JWKS)
    - HS256 tokens (signed with JWT secret, legacy/fallback)
    """
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "")

    if alg == "ES256":
        # Use JWKS public key for ES256 verification
        client = _get_jwks_client()
        if not client:
            raise jwt.InvalidTokenError("JWKS client not configured")
        signing_key = client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
        )
    else:
        # Fallback to HS256 with JWT secret
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
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired. Please sign out and sign back in.")
    except (jwt.InvalidTokenError, KeyError) as e:
        logger.warning(f"JWT verification failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_optional_user(
    authorization: str | None = Header(None),
) -> UserContext | None:
    """FastAPI dependency: returns UserContext if token present, None otherwise.

    Never raises on invalid tokens — returns None instead.
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
