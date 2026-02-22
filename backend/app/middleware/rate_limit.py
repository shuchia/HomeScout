"""Redis-based rate limiting middleware."""
import os
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
GLOBAL_LIMIT = 60       # requests per minute per user
EXPENSIVE_LIMIT = 10    # requests per minute for search/compare
ANON_LIMIT = 10         # requests per minute for anonymous

EXPENSIVE_PATHS = {"/api/search", "/api/apartments/compare"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        try:
            self.redis = redis.from_url(REDIS_URL)
        except Exception:
            self.redis = None

    async def dispatch(self, request: Request, call_next):
        if not self.redis or os.getenv("TESTING"):
            return await call_next(request)

        # Extract user identity
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            identity = f"user:{hash(auth)}"
            limit = GLOBAL_LIMIT
        else:
            identity = f"anon:{request.client.host if request.client else 'unknown'}"
            limit = ANON_LIMIT

        # Stricter limit for expensive endpoints
        path = request.url.path
        if path in EXPENSIVE_PATHS:
            limit = min(limit, EXPENSIVE_LIMIT)
            identity += ":expensive"

        # Sliding window counter
        key = f"ratelimit:{identity}:{int(time.time()) // 60}"
        try:
            current = self.redis.incr(key)
            if current == 1:
                self.redis.expire(key, 120)
            if current > limit:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please slow down."},
                )
        except Exception as e:
            logger.warning(f"Rate limit check failed: {e}")
            # Fail open

        return await call_next(request)
