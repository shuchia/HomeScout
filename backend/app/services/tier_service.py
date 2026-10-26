"""Tier checking and usage metering."""
import os
import logging
from datetime import date

import redis.asyncio as aioredis
from fastapi import HTTPException
from supabase import create_client

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# There is no paid tier any more (2026-10): every signed-in user gets AI and
# every feature that used to be Pro. What stands between a request and Claude
# is sign-in, the user's consent to send their data to AI providers, and a
# daily cap. The caps bound spend and abuse; they are not an upsell, so they
# sit well above what a real apartment hunt uses in a day.
DAILY_SEARCH_LIMIT = int(os.getenv("DAILY_SEARCH_LIMIT", "100"))
DAILY_AI_LIMIT = int(os.getenv("DAILY_AI_LIMIT", "100"))

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
        """Check if a signed-in user is within the daily search limit.
        Returns (allowed, remaining_searches).
        Fails open if Redis is unavailable.
        """
        try:
            r = await TierService._get_redis()
            key = f"search_count:{user_id}:{date.today().isoformat()}"
            count = await r.get(key)
            current = int(count) if count else 0
            remaining = max(0, DAILY_SEARCH_LIMIT - current)
            return (current < DAILY_SEARCH_LIMIT, remaining)
        except Exception as e:
            logger.warning(f"Redis error in check_search_limit: {e}")
            return (True, DAILY_SEARCH_LIMIT)  # Fail open

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
    async def has_ai_consent(user_id: str) -> bool:
        """Whether the user agreed to send their data to AI providers.

        Fails closed: a lookup error means no AI for this request, the same
        outcome the old tier lookup produced when it fell back to "free".
        """
        try:
            if not supabase_admin:
                return False
            result = (
                supabase_admin.table("profiles")
                .select("ai_consent_at")
                .eq("id", user_id)
                .single()
                .execute()
            )
            return bool(result.data and result.data.get("ai_consent_at"))
        except Exception as e:
            logger.warning(f"Failed to read AI consent: {e}")
            return False

    @staticmethod
    async def consume_ai_call(user_id: str) -> bool:
        """Count one AI call against today's cap. False once it is spent.

        Fails open on Redis errors, like the search limit — a Redis outage
        should not switch AI off for everyone.
        """
        try:
            r = await TierService._get_redis()
            key = f"ai_calls:{user_id}:{date.today().isoformat()}"
            count = await r.incr(key)
            await r.expire(key, 48 * 3600)
            return count <= DAILY_AI_LIMIT
        except Exception as e:
            logger.warning(f"Redis error in consume_ai_call: {e}")
            return True

    @staticmethod
    async def ai_denial(user_id: str) -> HTTPException | None:
        """The error to return instead of an AI call, or None to proceed.

        Consent is checked first so a user who never agreed doesn't spend
        their cap on calls that were going to be refused anyway.
        """
        if not await TierService.has_ai_consent(user_id):
            return HTTPException(
                status_code=403,
                detail="Turn on AI features in Settings to use this.",
            )
        if not await TierService.consume_ai_call(user_id):
            return HTTPException(
                status_code=429,
                detail="Daily AI limit reached. It resets tomorrow.",
            )
        return None

    @staticmethod
    async def require_ai(user_id: str) -> None:
        """Raise unless this user may make an AI call right now."""
        denial = await TierService.ai_denial(user_id)
        if denial:
            raise denial

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
