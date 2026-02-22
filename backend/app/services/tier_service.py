"""Tier checking and usage metering."""
import os
import logging
from datetime import date

import redis.asyncio as aioredis
from supabase import create_client

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

FREE_DAILY_SEARCH_LIMIT = 3

# Supabase admin client (service role - bypasses RLS)
supabase_admin = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


class TierService:

    @staticmethod
    async def _get_redis() -> aioredis.Redis:
        return aioredis.from_url(REDIS_URL, decode_responses=False)

    @staticmethod
    async def get_user_tier(user_id: str) -> str:
        """Get user tier from Supabase profiles. Returns 'free' if lookup fails."""
        try:
            if not supabase_admin:
                return "free"
            result = (
                supabase_admin.table("profiles")
                .select("user_tier")
                .eq("id", user_id)
                .single()
                .execute()
            )
            return result.data.get("user_tier", "free") if result.data else "free"
        except Exception as e:
            logger.warning(f"Failed to get user tier: {e}")
            return "free"

    @staticmethod
    async def check_search_limit(user_id: str) -> tuple[bool, int]:
        """Check if user is within daily search limit.
        Returns (allowed, remaining_searches).
        Fails open if Redis is unavailable.
        """
        try:
            r = await TierService._get_redis()
            key = f"search_count:{user_id}:{date.today().isoformat()}"
            count = await r.get(key)
            current = int(count) if count else 0
            remaining = max(0, FREE_DAILY_SEARCH_LIMIT - current)
            return (current < FREE_DAILY_SEARCH_LIMIT, remaining)
        except Exception as e:
            logger.warning(f"Redis error in check_search_limit: {e}")
            return (True, FREE_DAILY_SEARCH_LIMIT)  # Fail open

    @staticmethod
    async def increment_search_count(user_id: str) -> None:
        """Increment daily search counter. TTL 48h."""
        try:
            r = await TierService._get_redis()
            key = f"search_count:{user_id}:{date.today().isoformat()}"
            await r.incr(key)
            await r.expire(key, 48 * 3600)
        except Exception as e:
            logger.warning(f"Redis error in increment_search_count: {e}")

    @staticmethod
    async def update_user_tier(user_id: str, tier: str, **kwargs) -> None:
        """Update user tier in Supabase profiles. Called from Stripe webhooks."""
        try:
            if not supabase_admin:
                logger.error("Supabase admin client not configured")
                return
            update_data = {"user_tier": tier, **kwargs}
            supabase_admin.table("profiles").update(update_data).eq("id", user_id).execute()
        except Exception as e:
            logger.error(f"Failed to update user tier: {e}")
            raise
