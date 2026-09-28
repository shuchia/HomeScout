"""Redis-based rate limiting middleware using async Redis."""
import os
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
GLOBAL_LIMIT = 120      # requests per minute per user
EXPENSIVE_LIMIT = 20    # requests per minute for search/compare
ANON_LIMIT = 30         # requests per minute for anonymous

EXPENSIVE_PATHS = {"/api/search", "/api/apartments/compare", "/api/apartments/commute"}

# Infrastructure endpoints are never rate limited. Throttling a health check
# turns load into an outage: the ALB polls /health every 30s, and once the
# anonymous bucket is full those polls start returning 429 too. Sustain that
# past the unhealthy threshold and ECS kills tasks that were serving fine.
EXEMPT_PATHS = {"/health", "/metrics"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis | None:
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(REDIS_URL)
            except Exception:
                return None
        return self._redis

    @staticmethod
    def _client_ip(request: Request) -> str:
        """The caller's IP, not the load balancer's.

        Behind an ALB, request.client.host is the balancer's own address, so
        every anonymous request in the world shares one bucket — roughly
        ANON_LIMIT per ALB node for the entire anonymous population, rather
        than per caller.

        The ALB *appends* the address it observed to X-Forwarded-For, so the
        rightmost entry is the one it actually saw. Entries to its left were
        supplied by the caller and can be forged; reading the leftmost would
        let anyone dodge the limit with a header.
        """
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            parts = [p.strip() for p in forwarded.split(",") if p.strip()]
            if parts:
                return parts[-1]
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for preflight requests and when disabled
        if request.method == "OPTIONS" or os.getenv("TESTING"):
            return await call_next(request)

        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        r = await self._get_redis()
        if not r:
            return await call_next(request)

        # Extract user identity
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            identity = f"user:{hash(auth)}"
            limit = GLOBAL_LIMIT
        else:
            identity = f"anon:{self._client_ip(request)}"
            limit = ANON_LIMIT

        # Stricter limit for expensive endpoints
        path = request.url.path
        if path in EXPENSIVE_PATHS:
            limit = min(limit, EXPENSIVE_LIMIT)
            identity += ":expensive"

        # Sliding window counter
        key = f"ratelimit:{identity}:{int(time.time()) // 60}"
        try:
            current = await r.incr(key)
            if current == 1:
                await r.expire(key, 120)
            if current > limit:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please slow down."},
                )
        except Exception as e:
            logger.warning(f"Rate limit check failed: {e}")
            # Fail open

        return await call_next(request)
