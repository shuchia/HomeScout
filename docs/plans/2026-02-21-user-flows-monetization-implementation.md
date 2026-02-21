# User Flows & Monetization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add renter freemium monetization ($12/mo Pro tier) with Stripe payments, tier-gated features, usage tracking, and email alerts.

**Architecture:** Supabase manages auth and user data (profiles, favorites, saved searches). FastAPI backend verifies Supabase JWTs for tier-gated endpoints (search, compare). Stripe handles payments via hosted Checkout/Portal pages with webhook-driven tier updates. Redis meters daily search usage. Resend sends daily alert emails.

**Tech Stack:** Stripe (payments), PyJWT (JWT verification), Redis (rate limiting), Resend (email), Supabase (user data + RLS), Next.js (frontend pages)

---

## Phase 1: Backend Auth + Tier Foundation

### Task 1: Add tier columns to Supabase profiles

**Files:**
- Create: `supabase/migrations/002_add_tier_columns.sql`

**Step 1: Write the migration**

```sql
-- Add monetization columns to profiles
ALTER TABLE public.profiles ADD COLUMN user_tier TEXT NOT NULL DEFAULT 'free';
ALTER TABLE public.profiles ADD COLUMN stripe_customer_id TEXT;
ALTER TABLE public.profiles ADD COLUMN subscription_status TEXT;
ALTER TABLE public.profiles ADD COLUMN current_period_end TIMESTAMPTZ;

-- Index for quick tier lookups
CREATE INDEX idx_profiles_tier ON profiles(user_tier);
CREATE INDEX idx_profiles_stripe ON profiles(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;

-- Update RLS: allow service role to update tier (for Stripe webhooks)
CREATE POLICY "Service can update profiles" ON profiles
  FOR UPDATE USING (true) WITH CHECK (true);
```

**Step 2: Run the migration**

Run in Supabase SQL Editor (or via Supabase CLI: `supabase db push`).
Verify: `SELECT column_name FROM information_schema.columns WHERE table_name = 'profiles';`

**Step 3: Commit**

```bash
git add supabase/migrations/002_add_tier_columns.sql
git commit -m "feat: add tier and stripe columns to profiles table"
```

---

### Task 2: Add Supabase JWT verification to FastAPI

**Files:**
- Modify: `backend/requirements.txt` (add PyJWT)
- Create: `backend/app/auth.py`
- Create: `backend/tests/test_auth.py`

**Step 1: Add dependency**

Add to `backend/requirements.txt`:
```
PyJWT[crypto]==2.9.0
```

Run: `pip install PyJWT[crypto]`

**Step 2: Write failing tests**

```python
# backend/tests/test_auth.py
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

from app.auth import get_current_user, get_optional_user, UserContext


class TestGetCurrentUser:
    """Test mandatory auth dependency."""

    def test_missing_header_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                get_current_user(authorization=None)
            )
        assert exc_info.value.status_code == 401

    def test_invalid_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                get_current_user(authorization="Bearer invalid-token")
            )
        assert exc_info.value.status_code == 401

    @patch("app.auth._decode_supabase_jwt")
    def test_valid_token_returns_user_context(self, mock_decode):
        mock_decode.return_value = {
            "sub": "user-123",
            "email": "test@example.com"
        }
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            get_current_user(authorization="Bearer valid-token")
        )
        assert isinstance(result, UserContext)
        assert result.user_id == "user-123"


class TestGetOptionalUser:
    """Test optional auth dependency (returns None if no token)."""

    def test_no_header_returns_none(self):
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            get_optional_user(authorization=None)
        )
        assert result is None

    @patch("app.auth._decode_supabase_jwt")
    def test_valid_token_returns_user_context(self, mock_decode):
        mock_decode.return_value = {
            "sub": "user-456",
            "email": "pro@example.com"
        }
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            get_optional_user(authorization="Bearer valid-token")
        )
        assert result.user_id == "user-456"
```

**Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth'`

**Step 4: Implement auth module**

```python
# backend/app/auth.py
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
    """FastAPI dependency: requires valid Supabase JWT. Returns UserContext."""
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
    """FastAPI dependency: returns UserContext if token present, None otherwise."""
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
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: All 5 tests PASS

**Step 6: Add env var**

Add to `backend/.env`:
```
SUPABASE_JWT_SECRET=your-supabase-jwt-secret
```

(Find this in Supabase Dashboard -> Settings -> API -> JWT Secret)

**Step 7: Commit**

```bash
git add backend/requirements.txt backend/app/auth.py backend/tests/test_auth.py
git commit -m "feat: add Supabase JWT auth dependency for FastAPI"
```

---

### Task 3: Add tier-checking service with Redis usage metering

**Files:**
- Create: `backend/app/services/tier_service.py`
- Create: `backend/tests/test_tier_service.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_tier_service.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.tier_service import TierService


class TestGetUserTier:
    @pytest.mark.asyncio
    @patch("app.services.tier_service.supabase_admin")
    async def test_returns_free_for_default_user(self, mock_sb):
        mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"user_tier": "free"}
        )
        tier = await TierService.get_user_tier("user-123")
        assert tier == "free"

    @pytest.mark.asyncio
    @patch("app.services.tier_service.supabase_admin")
    async def test_returns_pro_for_upgraded_user(self, mock_sb):
        mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"user_tier": "pro"}
        )
        tier = await TierService.get_user_tier("user-456")
        assert tier == "pro"


class TestCheckSearchLimit:
    @pytest.mark.asyncio
    @patch("app.services.tier_service.TierService._get_redis")
    async def test_free_user_under_limit_allowed(self, mock_redis):
        r = AsyncMock()
        r.get.return_value = b"2"  # 2 of 3 used
        mock_redis.return_value = r
        allowed, remaining = await TierService.check_search_limit("user-123")
        assert allowed is True
        assert remaining == 1

    @pytest.mark.asyncio
    @patch("app.services.tier_service.TierService._get_redis")
    async def test_free_user_at_limit_blocked(self, mock_redis):
        r = AsyncMock()
        r.get.return_value = b"3"  # 3 of 3 used
        mock_redis.return_value = r
        allowed, remaining = await TierService.check_search_limit("user-123")
        assert allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    @patch("app.services.tier_service.TierService._get_redis")
    async def test_no_redis_fails_open(self, mock_redis):
        mock_redis.side_effect = Exception("Redis down")
        allowed, remaining = await TierService.check_search_limit("user-123")
        assert allowed is True  # Fail open
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_tier_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement tier service**

```python
# backend/app/services/tier_service.py
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
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_tier_service.py -v`
Expected: All 5 tests PASS

**Step 5: Add supabase dependency and env vars**

Add to `backend/requirements.txt`:
```
supabase==2.11.0
```

Run: `pip install supabase`

Add to `backend/.env`:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

**Step 6: Commit**

```bash
git add backend/app/services/tier_service.py backend/tests/test_tier_service.py backend/requirements.txt
git commit -m "feat: add tier service with Redis usage metering"
```

---

## Phase 2: Stripe Payments

### Task 4: Create Stripe billing router

**Files:**
- Modify: `backend/requirements.txt` (add stripe)
- Create: `backend/app/routers/billing.py`
- Create: `backend/tests/test_billing.py`
- Modify: `backend/app/main.py` (register router)

**Step 1: Add dependency**

Add to `backend/requirements.txt`:
```
stripe==11.4.1
```

Run: `pip install stripe`

**Step 2: Write failing tests**

```python
# backend/tests/test_billing.py
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestCheckoutEndpoint:
    @patch("app.routers.billing.get_current_user")
    @patch("app.routers.billing.stripe")
    def test_creates_checkout_session(self, mock_stripe, mock_auth):
        from app.auth import UserContext
        mock_auth.return_value = UserContext(user_id="user-123", email="test@test.com")
        mock_stripe.checkout.Session.create.return_value = MagicMock(url="https://checkout.stripe.com/123")

        response = client.post(
            "/api/billing/checkout",
            headers={"Authorization": "Bearer fake-token"}
        )
        assert response.status_code == 200
        assert "url" in response.json()

    def test_requires_auth(self):
        response = client.post("/api/billing/checkout")
        assert response.status_code == 401


class TestStripeWebhook:
    @patch("app.routers.billing.stripe")
    @patch("app.routers.billing.TierService")
    def test_handles_checkout_completed(self, mock_tier, mock_stripe):
        mock_stripe.Webhook.construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": "user-123",
                    "customer": "cus_abc",
                    "subscription": "sub_xyz"
                }
            }
        }

        response = client.post(
            "/api/webhooks/stripe",
            content=b"raw-body",
            headers={
                "stripe-signature": "fake-sig",
                "content-type": "application/json"
            }
        )
        assert response.status_code == 200
```

**Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_billing.py -v`
Expected: FAIL — import errors

**Step 4: Implement billing router**

```python
# backend/app/routers/billing.py
"""Stripe billing endpoints."""
import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
import stripe

from app.auth import get_current_user, UserContext
from app.services.tier_service import TierService

logger = logging.getLogger(__name__)

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


@router.post("/api/billing/checkout")
async def create_checkout_session(
    user: UserContext = Depends(get_current_user),
):
    """Create Stripe Checkout Session for Pro upgrade."""
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            client_reference_id=user.user_id,
            customer_email=user.email,
            success_url=f"{FRONTEND_URL}/settings?upgrade=success",
            cancel_url=f"{FRONTEND_URL}/pricing",
        )
        return {"url": session.url}
    except stripe.StripeError as e:
        logger.error(f"Stripe checkout error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")


@router.post("/api/billing/portal")
async def create_portal_session(
    user: UserContext = Depends(get_current_user),
):
    """Create Stripe Customer Portal session for billing management."""
    try:
        from app.services.tier_service import supabase_admin
        if not supabase_admin:
            raise HTTPException(status_code=500, detail="Supabase not configured")
        result = (
            supabase_admin.table("profiles")
            .select("stripe_customer_id")
            .eq("id", user.user_id)
            .single()
            .execute()
        )
        customer_id = result.data.get("stripe_customer_id") if result.data else None
        if not customer_id:
            raise HTTPException(status_code=400, detail="No active subscription found")

        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{FRONTEND_URL}/settings",
        )
        return {"url": session.url}
    except stripe.StripeError as e:
        logger.error(f"Stripe portal error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create portal session")


@router.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events. Verifies signature."""
    body = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(body, sig, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError) as e:
        logger.warning(f"Stripe webhook verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id")
        customer_id = data.get("customer")
        if user_id:
            await TierService.update_user_tier(
                user_id, "pro",
                stripe_customer_id=customer_id,
                subscription_status="active",
            )
            logger.info(f"User {user_id} upgraded to pro")

    elif event_type == "customer.subscription.updated":
        customer_id = data.get("customer")
        status = data.get("status")
        cancel_at = data.get("cancel_at_period_end")
        current_period_end = data.get("current_period_end")
        user_id = await _lookup_user_by_customer(customer_id)
        if user_id:
            await TierService.update_user_tier(
                user_id, "pro" if status == "active" else "free",
                subscription_status="canceled" if cancel_at else status,
                current_period_end=current_period_end,
            )

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        user_id = await _lookup_user_by_customer(customer_id)
        if user_id:
            await TierService.update_user_tier(
                user_id, "free",
                subscription_status="canceled",
            )
            logger.info(f"User {user_id} downgraded to free")

    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer")
        user_id = await _lookup_user_by_customer(customer_id)
        if user_id:
            await TierService.update_user_tier(
                user_id, "pro",  # keep pro during retry period
                subscription_status="past_due",
            )

    return {"status": "ok"}


async def _lookup_user_by_customer(customer_id: str) -> str | None:
    """Look up user_id by Stripe customer ID."""
    from app.services.tier_service import supabase_admin
    if not supabase_admin or not customer_id:
        return None
    try:
        result = (
            supabase_admin.table("profiles")
            .select("id")
            .eq("stripe_customer_id", customer_id)
            .single()
            .execute()
        )
        return result.data.get("id") if result.data else None
    except Exception as e:
        logger.error(f"Failed to look up user by customer: {e}")
        return None
```

**Step 5: Register router in main.py**

Add to `backend/app/main.py` after the existing router imports (~line 20):
```python
from app.routers.billing import router as billing_router
```

And after existing `app.include_router` calls (~line 76):
```python
app.include_router(billing_router)
```

**Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_billing.py -v`
Expected: PASS

**Step 7: Add env vars to .env**

```bash
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
```

**Step 8: Commit**

```bash
git add backend/requirements.txt backend/app/routers/billing.py backend/tests/test_billing.py backend/app/main.py
git commit -m "feat: add Stripe billing router with checkout, portal, and webhooks"
```

---

## Phase 3: Backend Tier Gating

### Task 5: Gate the search endpoint

**Files:**
- Modify: `backend/app/main.py` (search endpoint, ~line 80-140)
- Create: `backend/tests/test_search_gating.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_search_gating.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

SEARCH_BODY = {
    "city": "Pittsburgh",
    "budget": 2000,
    "bedrooms": 2,
    "bathrooms": 1,
}


class TestSearchGating:
    @patch("app.main.get_optional_user")
    @patch("app.main.ApartmentService")
    def test_anonymous_user_gets_results_without_scores(self, mock_svc, mock_auth):
        """Anonymous users get apartment results but no AI scoring."""
        mock_auth.return_value = None
        mock_svc_instance = MagicMock()
        mock_svc_instance.search_apartments.return_value = [
            {"id": "apt-1", "address": "123 Main", "rent": 1500, "bedrooms": 2, "bathrooms": 1}
        ]
        mock_svc.return_value = mock_svc_instance

        response = client.post("/api/search", json=SEARCH_BODY)
        assert response.status_code == 200
        data = response.json()
        assert "results" in data

    @patch("app.main.get_optional_user")
    @patch("app.main.TierService")
    def test_free_user_at_limit_gets_429(self, mock_tier, mock_auth):
        """Free user who has used 3 searches today gets 429."""
        from app.auth import UserContext
        mock_auth.return_value = UserContext(user_id="user-123")
        mock_tier.get_user_tier = AsyncMock(return_value="free")
        mock_tier.check_search_limit = AsyncMock(return_value=(False, 0))

        response = client.post(
            "/api/search",
            json=SEARCH_BODY,
            headers={"Authorization": "Bearer fake"}
        )
        assert response.status_code == 429
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_search_gating.py -v`
Expected: FAIL

**Step 3: Modify search endpoint in main.py**

The current search endpoint at `POST /api/search` (~line 80) needs these changes:
- Accept optional auth via `get_optional_user`
- If user is free: check daily search limit, skip Claude scoring
- If user is pro: full Claude scoring, no limit
- If anonymous: return filtered results without scoring

Change the endpoint signature and body. Key imports to add at top of `main.py`:
```python
from app.auth import get_optional_user, UserContext
from app.services.tier_service import TierService
```

Change the endpoint:
```python
@app.post("/api/search")
async def search_apartments(
    request: SearchRequest,
    user: UserContext | None = Depends(get_optional_user),
):
    # Determine tier
    tier = "anonymous"
    if user:
        tier = await TierService.get_user_tier(user.user_id)

    # Check search limit for free users
    if tier == "free":
        allowed, remaining = await TierService.check_search_limit(user.user_id)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={"message": "Daily search limit reached", "remaining": 0}
            )

    service = ApartmentService()
    if tier == "pro":
        # Full AI-scored search
        results = await service.get_top_apartments(
            city=request.city, budget=request.budget,
            bedrooms=request.bedrooms, bathrooms=request.bathrooms,
            property_type=request.property_type, move_in_date=request.move_in_date,
            other_preferences=request.other_preferences,
        )
    else:
        # Free/anonymous: filtered results without Claude scoring
        results = service.search_apartments(
            city=request.city, budget=request.budget,
            bedrooms=request.bedrooms, bathrooms=request.bathrooms,
            property_type=request.property_type, move_in_date=request.move_in_date,
        )
        results = [
            {**apt, "match_score": None, "reasoning": None, "highlights": []}
            for apt in (results if isinstance(results, list) else [])
        ]

    # Increment counter for free users
    if tier == "free" and user:
        await TierService.increment_search_count(user.user_id)

    remaining = None
    if tier == "free" and user:
        _, remaining = await TierService.check_search_limit(user.user_id)

    return {
        "results": results[:10],
        "total_count": len(results),
        "tier": tier,
        "searches_remaining": remaining,
    }
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_search_gating.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_search_gating.py
git commit -m "feat: gate search endpoint by tier with daily limit for free users"
```

---

### Task 6: Gate the compare endpoint

**Files:**
- Modify: `backend/app/routers/apartments.py` (compare endpoint, ~line 229-288)
- Create: `backend/tests/test_compare_gating.py`

**Step 1: Write failing test**

```python
# backend/tests/test_compare_gating.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestCompareGating:
    @patch("app.routers.apartments.get_optional_user")
    def test_free_user_gets_table_data_no_analysis(self, mock_auth):
        """Free users get side-by-side data but no Claude analysis."""
        from app.auth import UserContext
        mock_auth.return_value = UserContext(user_id="user-123")

        response = client.post(
            "/api/apartments/compare",
            json={"apartment_ids": ["apt-1", "apt-2"]},
            headers={"Authorization": "Bearer fake"}
        )
        if response.status_code == 200:
            data = response.json()
            assert data.get("comparison_analysis") is None
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_compare_gating.py -v`
Expected: FAIL

**Step 3: Modify compare endpoint in apartments.py**

Add imports at top of `backend/app/routers/apartments.py`:
```python
from app.auth import get_optional_user, UserContext
from app.services.tier_service import TierService
```

Modify the compare endpoint to accept optional auth and gate the Claude call:
```python
@router.post("/api/apartments/compare")
async def compare_apartments(
    request: CompareRequest,
    user: UserContext | None = Depends(get_optional_user),
):
    # ... existing apartment fetching logic stays the same ...

    # Tier check before Claude call
    tier = "anonymous"
    if user:
        tier = await TierService.get_user_tier(user.user_id)

    comparison_analysis = None
    if tier == "pro" and len(apartments_data) >= 2:
        # Existing Claude call
        comparison_analysis = await asyncio.to_thread(
            claude_service.compare_apartments_with_analysis,
            apartments_data,
            request.preferences or "general comparison",
            request.search_context.model_dump() if request.search_context else None,
        )

    return {
        "apartments": apartments_data,
        "comparison_fields": ["rent", "bedrooms", "bathrooms", "sqft", "amenities"],
        "comparison_analysis": comparison_analysis,
        "tier": tier,
    }
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_compare_gating.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/routers/apartments.py backend/tests/test_compare_gating.py
git commit -m "feat: gate compare Claude analysis to pro tier only"
```

---

## Phase 4: Frontend Tier System

### Task 7: Extend frontend types and AuthContext with tier

**Files:**
- Modify: `frontend/lib/supabase.ts:10-16` (Profile type)
- Modify: `frontend/contexts/AuthContext.tsx` (expose tier)
- Modify: `frontend/lib/api.ts` (send auth header)

**Step 1: Update Profile type in `frontend/lib/supabase.ts`**

Add tier fields to the Profile interface (currently lines 10-16):
```typescript
export interface Profile {
  id: string
  email: string
  name: string | null
  avatar_url: string | null
  email_notifications: boolean
  user_tier: 'free' | 'pro'              // NEW
  subscription_status: string | null      // NEW
  current_period_end: string | null       // NEW
}
```

**Step 2: Update AuthContext in `frontend/contexts/AuthContext.tsx`**

Add to interface (lines 6-13):
```typescript
interface AuthContextType {
  user: User | null
  profile: Profile | null
  loading: boolean
  isPro: boolean                          // NEW
  tier: 'free' | 'pro' | 'anonymous'     // NEW
  signInWithGoogle: () => Promise<void>
  signInWithApple: () => Promise<void>
  signOut: () => Promise<void>
  refreshProfile: () => Promise<void>     // NEW
}
```

Add computed values inside `AuthProvider`:
```typescript
const tier = user ? (profile?.user_tier || 'free') : 'anonymous'
const isPro = tier === 'pro'

const refreshProfile = useCallback(async () => {
  if (user) await fetchProfile(user.id)
}, [user, fetchProfile])
```

Update signOut to clear stores:
```typescript
async function signOut() {
  await supabase.auth.signOut()
  setProfile(null)
  if (typeof window !== 'undefined') {
    localStorage.removeItem('comparison-storage')
  }
}
```

Update provider value:
```typescript
value={{ user, profile, loading, isPro, tier, signInWithGoogle, signInWithApple, signOut, refreshProfile }}
```

**Step 3: Update API client in `frontend/lib/api.ts`**

Add auth header helper at top:
```typescript
import { supabase } from './supabase'

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data: { session } } = await supabase.auth.getSession()
  if (session?.access_token) {
    return { Authorization: `Bearer ${session.access_token}` }
  }
  return {}
}
```

Then in each API call (`searchApartments`, `compareApartments`, etc.), spread auth headers into the fetch call:
```typescript
const authHeaders = await getAuthHeaders()
const response = await fetch(`${API_BASE}/api/search`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', ...authHeaders },
  body: JSON.stringify(params),
})
```

**Step 4: Commit**

```bash
git add frontend/lib/supabase.ts frontend/contexts/AuthContext.tsx frontend/lib/api.ts
git commit -m "feat: extend auth context with tier and send JWT to backend"
```

---

### Task 8: Create reusable UpgradePrompt component

**Files:**
- Create: `frontend/components/UpgradePrompt.tsx`

**Step 1: Create component**

```typescript
// frontend/components/UpgradePrompt.tsx
'use client'
import Link from 'next/link'

interface UpgradePromptProps {
  feature: string
  inline?: boolean
  className?: string
}

export default function UpgradePrompt({ feature, inline = false, className = '' }: UpgradePromptProps) {
  if (inline) {
    return (
      <div className={`flex items-center gap-2 text-sm text-gray-500 ${className}`}>
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
        <span>Upgrade to Pro for {feature}</span>
        <Link href="/pricing" className="text-blue-600 hover:underline font-medium">
          Upgrade
        </Link>
      </div>
    )
  }

  return (
    <div className={`bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-6 text-center ${className}`}>
      <h3 className="text-lg font-semibold text-gray-900 mb-1">Pro Feature</h3>
      <p className="text-gray-600 mb-4">Upgrade to unlock {feature}</p>
      <Link
        href="/pricing"
        className="inline-block bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition-colors font-medium"
      >
        Upgrade to Pro - $12/mo
      </Link>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/components/UpgradePrompt.tsx
git commit -m "feat: add reusable UpgradePrompt component"
```

---

### Task 9: Gate search page for free users

**Files:**
- Modify: `frontend/app/page.tsx` (search page)
- Modify: `frontend/components/ApartmentCard.tsx` (locked scores)

**Step 1: Update search page to handle tier response**

In `frontend/app/page.tsx`:

Add state and read tier from auth:
```typescript
const { isPro, tier } = useAuth()
const [searchesRemaining, setSearchesRemaining] = useState<number | null>(null)
```

In the search handler, read new fields from response:
```typescript
const data = await searchApartments(params)
setSearchesRemaining(data.searches_remaining ?? null)
```

Below the search form, show counter for free users:
```tsx
{tier === 'free' && searchesRemaining !== null && (
  <p className="text-sm text-gray-500 mt-2">
    {searchesRemaining} of 3 free searches remaining today
  </p>
)}
```

When `searchesRemaining === 0`, disable submit and show upgrade CTA.

**Step 2: Update ApartmentCard for locked scores**

In `frontend/components/ApartmentCard.tsx`, when `match_score` is null, show a locked badge:
```tsx
{apartment.match_score != null ? (
  <span className="...">{apartment.match_score}</span>
) : (
  <span className="bg-gray-200 text-gray-500 px-2 py-1 rounded text-xs">
    Pro only
  </span>
)}
```

Also hide `reasoning` and `highlights` when score is null.

**Step 3: Commit**

```bash
git add frontend/app/page.tsx frontend/components/ApartmentCard.tsx
git commit -m "feat: gate search results by tier, show remaining searches"
```

---

### Task 10: Gate compare page for free users

**Files:**
- Modify: `frontend/app/compare/page.tsx`

**Step 1: Gate the Score button**

Import and use auth + UpgradePrompt:
```typescript
import { useAuth } from '@/contexts/AuthContext'
import UpgradePrompt from '@/components/UpgradePrompt'

const { isPro } = useAuth()
```

Replace the "Score" button section (~lines 212-252):
```tsx
{isPro ? (
  <button onClick={handleScore} disabled={scoring} className="...">
    {scoring ? 'Analyzing...' : 'Score with AI'}
  </button>
) : (
  <UpgradePrompt feature="AI comparison analysis" />
)}
```

**Step 2: Handle null analysis in response**

The compare API now returns `comparison_analysis: null` for free users. Add a fallback:
```tsx
{analysis ? (
  // Existing winner + category breakdown UI
) : !isPro ? (
  <UpgradePrompt feature="detailed AI analysis with winner picks and category scoring" />
) : null}
```

The side-by-side table (rent, beds, baths, amenities) continues to render for all users.

**Step 3: Commit**

```bash
git add frontend/app/compare/page.tsx
git commit -m "feat: gate compare AI analysis to pro users"
```

---

### Task 11: Gate favorites for free users

**Files:**
- Modify: `frontend/hooks/useFavorites.ts`
- Modify: `frontend/components/FavoriteButton.tsx`

**Step 1: Add limit check to useFavorites hook**

In `frontend/hooks/useFavorites.ts`, import auth and enforce limit:
```typescript
import { useAuth } from '@/contexts/AuthContext'

// Inside the hook:
const { isPro } = useAuth()

const addFavorite = async (apartmentId: string): Promise<boolean> => {
  if (!isPro && favorites.length >= 5) {
    return false  // Caller handles the UI feedback
  }
  // ... existing optimistic update logic
}

// Add to return value:
return {
  favorites, loading, addFavorite, removeFavorite, isFavorite, refresh,
  atLimit: !isPro && favorites.length >= 5,
}
```

**Step 2: Update FavoriteButton**

When `atLimit` is true and apartment is not already favorited, show a message. The button should call `addFavorite` and, if it returns `false`, display: "Free limit reached (5/5). Upgrade for unlimited favorites."

**Step 3: Commit**

```bash
git add frontend/hooks/useFavorites.ts frontend/components/FavoriteButton.tsx
git commit -m "feat: enforce 5 favorite limit for free tier"
```

---

### Task 12: Create /pricing page

**Files:**
- Create: `frontend/app/pricing/page.tsx`
- Modify: `frontend/components/Header.tsx` (add nav link)

**Step 1: Create pricing page**

```typescript
// frontend/app/pricing/page.tsx
'use client'
import { useAuth } from '@/contexts/AuthContext'
import Header from '@/components/Header'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function PricingPage() {
  const { user, isPro, loading } = useAuth()

  async function handleUpgrade() {
    const { data: { session } } = await (await import('@/lib/supabase')).supabase.auth.getSession()
    const res = await fetch(`${API_BASE}/api/billing/checkout`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}),
      },
    })
    const { url } = await res.json()
    if (url) window.location.href = url
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="max-w-4xl mx-auto px-4 py-16">
        <h1 className="text-3xl font-bold text-center mb-2">Choose Your Plan</h1>
        <p className="text-gray-600 text-center mb-12">Unlock AI-powered apartment matching</p>

        <div className="grid md:grid-cols-2 gap-8">
          {/* Free Plan */}
          <div className="bg-white rounded-xl border border-gray-200 p-8">
            <h2 className="text-xl font-semibold mb-1">Free</h2>
            <p className="text-3xl font-bold mb-6">$0<span className="text-base font-normal text-gray-500">/mo</span></p>
            <ul className="space-y-3 text-sm text-gray-600 mb-8">
              <li>3 searches per day</li>
              <li>Side-by-side comparison</li>
              <li>5 favorites</li>
              <li className="text-gray-400 line-through">AI match scoring</li>
              <li className="text-gray-400 line-through">AI comparison analysis</li>
              <li className="text-gray-400 line-through">Saved searches and alerts</li>
            </ul>
            {!user && (
              <p className="text-sm text-gray-500 text-center">Sign in to get started</p>
            )}
          </div>

          {/* Pro Plan */}
          <div className="bg-white rounded-xl border-2 border-blue-600 p-8 relative">
            <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-blue-600 text-white text-xs px-3 py-1 rounded-full">
              Recommended
            </span>
            <h2 className="text-xl font-semibold mb-1">Pro</h2>
            <p className="text-3xl font-bold mb-6">$12<span className="text-base font-normal text-gray-500">/mo</span></p>
            <ul className="space-y-3 text-sm text-gray-700 mb-8">
              <li>Unlimited searches</li>
              <li>AI match scoring (0-100)</li>
              <li>AI comparison analysis with winner picks</li>
              <li>Unlimited favorites</li>
              <li>Saved searches</li>
              <li>Daily email alerts for new matches</li>
            </ul>
            {isPro ? (
              <p className="text-center text-green-600 font-medium">Your current plan</p>
            ) : (
              <button
                onClick={handleUpgrade}
                disabled={!user || loading}
                className="w-full bg-blue-600 text-white py-3 rounded-lg hover:bg-blue-700 transition-colors font-medium disabled:opacity-50"
              >
                {user ? 'Upgrade to Pro' : 'Sign in to upgrade'}
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
```

**Step 2: Add Pricing link to Header**

In `frontend/components/Header.tsx`, add a "Pricing" nav link visible to all users, next to the existing navigation links.

**Step 3: Commit**

```bash
git add frontend/app/pricing/page.tsx frontend/components/Header.tsx
git commit -m "feat: add pricing page with free vs pro comparison"
```

---

### Task 13: Create /settings page

**Files:**
- Create: `frontend/app/settings/page.tsx`
- Modify: `frontend/components/UserMenu.tsx` (add Settings link)

**Step 1: Create settings page**

```typescript
// frontend/app/settings/page.tsx
'use client'
import { useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import Header from '@/components/Header'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function SettingsPage() {
  const { user, profile, loading, isPro, tier, signOut, refreshProfile } = useAuth()
  const searchParams = useSearchParams()

  useEffect(() => {
    if (searchParams.get('upgrade') === 'success') {
      refreshProfile()
    }
  }, [searchParams, refreshProfile])

  if (loading) return <div className="min-h-screen flex items-center justify-center">Loading...</div>
  if (!user) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <div className="flex items-center justify-center pt-32">
          <p className="text-gray-600">Please sign in to view settings.</p>
        </div>
      </div>
    )
  }

  async function handleManageBilling() {
    const { data: { session } } = await (await import('@/lib/supabase')).supabase.auth.getSession()
    const res = await fetch(`${API_BASE}/api/billing/portal`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}),
      },
    })
    const { url } = await res.json()
    if (url) window.location.href = url
  }

  async function handleDeleteAccount() {
    if (!confirm('This will permanently delete your account, favorites, and saved searches. This cannot be undone.')) return
    await signOut()
    window.location.href = '/'
  }

  async function handleExportData() {
    const { supabase } = await import('@/lib/supabase')
    const [favs, searches] = await Promise.all([
      supabase.from('favorites').select('*').eq('user_id', user!.id),
      supabase.from('saved_searches').select('*').eq('user_id', user!.id),
    ])
    const blob = new Blob(
      [JSON.stringify({ favorites: favs.data, saved_searches: searches.data }, null, 2)],
      { type: 'application/json' }
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'homescout-data.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="max-w-2xl mx-auto px-4 py-12">
        <h1 className="text-2xl font-bold mb-8">Settings</h1>

        {searchParams.get('upgrade') === 'success' && (
          <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg mb-6">
            Welcome to Pro! You now have full access to all features.
          </div>
        )}

        {/* Profile Section */}
        <section className="bg-white rounded-lg border p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Profile</h2>
          <div className="flex items-center gap-4">
            {profile?.avatar_url && (
              <img src={profile.avatar_url} alt="" className="w-12 h-12 rounded-full" />
            )}
            <div>
              <p className="font-medium">{profile?.name || 'No name'}</p>
              <p className="text-sm text-gray-500">{profile?.email}</p>
            </div>
          </div>
        </section>

        {/* Subscription Section */}
        <section className="bg-white rounded-lg border p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Subscription</h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium capitalize">{tier} Plan</p>
              <p className="text-sm text-gray-500">
                {isPro ? 'Full access to all features' : 'Limited features'}
              </p>
            </div>
            {isPro ? (
              <button
                onClick={handleManageBilling}
                className="text-sm text-blue-600 hover:underline"
              >
                Manage Billing
              </button>
            ) : (
              <a href="/pricing" className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700">
                Upgrade to Pro
              </a>
            )}
          </div>
        </section>

        {/* Data Section */}
        <section className="bg-white rounded-lg border p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Your Data</h2>
          <button
            onClick={handleExportData}
            className="text-sm text-blue-600 hover:underline"
          >
            Export my data (JSON)
          </button>
        </section>

        {/* Danger Zone */}
        <section className="bg-white rounded-lg border border-red-200 p-6">
          <h2 className="text-lg font-semibold text-red-600 mb-4">Danger Zone</h2>
          <button
            onClick={handleDeleteAccount}
            className="text-sm text-red-600 hover:underline"
          >
            Delete my account
          </button>
        </section>
      </main>
    </div>
  )
}
```

**Step 2: Add Settings link to UserMenu**

In `frontend/components/UserMenu.tsx`, add a "Settings" link pointing to `/settings` alongside the existing "My Favorites" and "Saved Searches" links.

**Step 3: Commit**

```bash
git add frontend/app/settings/page.tsx frontend/components/UserMenu.tsx
git commit -m "feat: add settings page with profile, billing, and data export"
```

---

## Phase 5: Analytics

### Task 14: Create analytics events table and backend logging

**Files:**
- Create: `supabase/migrations/003_add_analytics_events.sql`
- Create: `backend/app/services/analytics_service.py`
- Modify: `backend/app/main.py` (log search events)
- Modify: `backend/app/routers/apartments.py` (log compare events)

**Step 1: Write migration**

```sql
-- supabase/migrations/003_add_analytics_events.sql
CREATE TABLE public.analytics_events (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_events_type_date ON analytics_events(event_type, created_at);
CREATE INDEX idx_events_user ON analytics_events(user_id);

ALTER TABLE analytics_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service can insert events" ON analytics_events FOR INSERT WITH CHECK (true);
CREATE POLICY "Service can read events" ON analytics_events FOR SELECT USING (true);
```

**Step 2: Run migration in Supabase SQL Editor**

**Step 3: Create analytics service**

```python
# backend/app/services/analytics_service.py
"""Lightweight event logging to Supabase."""
import logging
from app.services.tier_service import supabase_admin

logger = logging.getLogger(__name__)


class AnalyticsService:

    @staticmethod
    async def log_event(
        event_type: str,
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Fire-and-forget event logging. Never raises."""
        try:
            if not supabase_admin:
                return
            supabase_admin.table("analytics_events").insert({
                "event_type": event_type,
                "user_id": user_id,
                "metadata": metadata or {},
            }).execute()
        except Exception as e:
            logger.warning(f"Failed to log analytics event: {e}")
```

**Step 4: Add logging to search endpoint**

In `backend/app/main.py` search endpoint, add before the return statement:
```python
from app.services.analytics_service import AnalyticsService

await AnalyticsService.log_event(
    "search",
    user_id=user.user_id if user else None,
    metadata={"city": request.city, "tier": tier, "result_count": len(results)},
)
```

**Step 5: Add logging to compare endpoint**

In `backend/app/routers/apartments.py` compare endpoint, add before the return:
```python
from app.services.analytics_service import AnalyticsService

await AnalyticsService.log_event(
    "compare",
    user_id=user.user_id if user else None,
    metadata={"apartment_count": len(request.apartment_ids), "used_ai": tier == "pro"},
)
```

**Step 6: Commit**

```bash
git add supabase/migrations/003_add_analytics_events.sql backend/app/services/analytics_service.py backend/app/main.py backend/app/routers/apartments.py
git commit -m "feat: add analytics event logging for search and compare"
```

---

## Phase 6: Saved Searches & Email Alerts

### Task 15: Add saved search backend endpoints

**Files:**
- Create: `supabase/migrations/004_update_saved_searches.sql`
- Create: `backend/app/routers/saved_searches.py`
- Modify: `backend/app/main.py` (register router)

**Step 1: Write migration for saved_searches additions**

```sql
-- supabase/migrations/004_update_saved_searches.sql
ALTER TABLE public.saved_searches ADD COLUMN IF NOT EXISTS last_alerted_at TIMESTAMPTZ;
ALTER TABLE public.saved_searches ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;
```

**Step 2: Run migration in Supabase SQL Editor**

**Step 3: Create saved searches router**

```python
# backend/app/routers/saved_searches.py
"""Saved search endpoints (Pro only)."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_user, UserContext
from app.services.tier_service import TierService, supabase_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/saved-searches", tags=["saved-searches"])


class SaveSearchRequest(BaseModel):
    name: str
    city: str
    budget: int | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    property_type: str | None = None
    preferences: str | None = None


@router.get("")
async def list_saved_searches(user: UserContext = Depends(get_current_user)):
    """List user's saved searches."""
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    result = (
        supabase_admin.table("saved_searches")
        .select("*")
        .eq("user_id", user.user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return {"saved_searches": result.data or []}


@router.post("")
async def create_saved_search(
    request: SaveSearchRequest,
    user: UserContext = Depends(get_current_user),
):
    """Create a saved search (Pro only)."""
    tier = await TierService.get_user_tier(user.user_id)
    if tier != "pro":
        raise HTTPException(status_code=403, detail="Saved searches require Pro plan")
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    result = (
        supabase_admin.table("saved_searches")
        .insert({
            "user_id": user.user_id,
            "name": request.name,
            "city": request.city,
            "budget": request.budget,
            "bedrooms": request.bedrooms,
            "bathrooms": request.bathrooms,
            "property_type": request.property_type,
            "preferences": request.preferences,
        })
        .execute()
    )
    return {"saved_search": result.data[0] if result.data else None}


@router.delete("/{search_id}")
async def delete_saved_search(
    search_id: str,
    user: UserContext = Depends(get_current_user),
):
    """Delete a saved search."""
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    supabase_admin.table("saved_searches").delete().eq("id", search_id).eq("user_id", user.user_id).execute()
    return {"status": "deleted"}
```

**Step 4: Register router in main.py**

Add to `backend/app/main.py`:
```python
from app.routers.saved_searches import router as saved_searches_router
app.include_router(saved_searches_router)
```

**Step 5: Commit**

```bash
git add supabase/migrations/004_update_saved_searches.sql backend/app/routers/saved_searches.py backend/app/main.py
git commit -m "feat: add saved search CRUD endpoints (pro only)"
```

---

### Task 16: Add daily email alerts with Resend

**Files:**
- Modify: `backend/requirements.txt` (add resend)
- Create: `backend/app/tasks/alert_tasks.py`
- Modify: `backend/app/celery_app.py` (add beat schedule)

**Step 1: Add dependency**

Add to `backend/requirements.txt`:
```
resend==2.5.0
```

Run: `pip install resend`

**Step 2: Create alert task**

```python
# backend/app/tasks/alert_tasks.py
"""Daily email alert task for Pro users with saved searches."""
import os
import logging
from datetime import datetime, timezone

import resend
from celery import shared_task

logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("ALERT_FROM_EMAIL", "alerts@homescout.app")


@shared_task(name="app.tasks.alert_tasks.send_daily_alerts")
def send_daily_alerts():
    """Find Pro users with active saved searches, check for new listings, send emails."""
    from app.services.tier_service import supabase_admin
    if not supabase_admin:
        logger.error("Supabase admin client not configured")
        return

    # Get all active saved searches for pro users
    result = (
        supabase_admin.table("saved_searches")
        .select("*, profiles!inner(user_tier, email, name)")
        .eq("is_active", True)
        .eq("notify_new_matches", True)
        .eq("profiles.user_tier", "pro")
        .execute()
    )

    if not result.data:
        logger.info("No active saved searches to process")
        return

    from app.services.apartment_service import ApartmentService
    service = ApartmentService()
    sent_count = 0

    for search in result.data:
        profile = search.get("profiles", {})
        email = profile.get("email")
        if not email:
            continue

        last_alerted = search.get("last_alerted_at")

        # Find apartments matching this search
        apartments = service.search_apartments(
            city=search["city"],
            budget=search.get("budget"),
            bedrooms=search.get("bedrooms"),
            bathrooms=search.get("bathrooms"),
            property_type=search.get("property_type"),
        )

        # Filter to only new listings since last alert
        if last_alerted:
            apartments = [
                apt for apt in apartments
                if apt.get("first_seen_at") and apt["first_seen_at"] > last_alerted
            ]

        if not apartments:
            continue

        # Build and send email
        try:
            apartment_lines = []
            for apt in apartments[:10]:
                apartment_lines.append(
                    f"- {apt.get('address', 'Unknown')} - ${apt.get('rent', '?')}/mo, "
                    f"{apt.get('bedrooms', '?')}bd/{apt.get('bathrooms', '?')}ba"
                )

            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
            body = (
                f"Hi {profile.get('name', 'there')},\n\n"
                f"We found {len(apartments)} new apartment(s) matching your "
                f"\"{search['name']}\" search in {search['city']}:\n\n"
                + "\n".join(apartment_lines)
                + f"\n\nView them on HomeScout: {frontend_url}"
                + f"\n\nManage your alerts: {frontend_url}/settings"
            )

            resend.Emails.send({
                "from": FROM_EMAIL,
                "to": email,
                "subject": f"{len(apartments)} new apartment(s) in {search['city']} match your search",
                "text": body,
            })
            sent_count += 1

            # Update last_alerted_at
            supabase_admin.table("saved_searches").update({
                "last_alerted_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", search["id"]).execute()

        except Exception as e:
            logger.error(f"Failed to send alert for search {search['id']}: {e}")

    logger.info(f"Sent {sent_count} alert emails")
    return {"sent": sent_count}
```

**Step 3: Add to Celery beat schedule**

In `backend/app/celery_app.py`, add to `beat_schedule` dict:
```python
"send-daily-alerts": {
    "task": "app.tasks.alert_tasks.send_daily_alerts",
    "schedule": crontab(hour=13, minute=0),  # 8 AM ET = 13:00 UTC
},
```

And add to `include` list:
```python
"app.tasks.alert_tasks",
```

**Step 4: Add env vars**

```bash
RESEND_API_KEY=re_...
ALERT_FROM_EMAIL=alerts@homescout.app
```

**Step 5: Commit**

```bash
git add backend/requirements.txt backend/app/tasks/alert_tasks.py backend/app/celery_app.py
git commit -m "feat: add daily email alerts for pro users via Resend"
```

---

### Task 17: Add rate limiting middleware

**Files:**
- Create: `backend/app/middleware/rate_limit.py`
- Modify: `backend/app/main.py` (add middleware)

**Step 1: Create rate limiter**

```python
# backend/app/middleware/rate_limit.py
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
        if not self.redis:
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
```

**Step 2: Add middleware to main.py**

In `backend/app/main.py`, after CORS middleware (~line 72):
```python
from app.middleware.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)
```

**Step 3: Commit**

```bash
git add backend/app/middleware/rate_limit.py backend/app/main.py
git commit -m "feat: add Redis-based rate limiting middleware"
```

---

## Summary

| Phase | Tasks | Focus |
|-------|-------|-------|
| 1 | Tasks 1-3 | Backend auth + tier foundation |
| 2 | Task 4 | Stripe payments |
| 3 | Tasks 5-6 | Backend tier gating |
| 4 | Tasks 7-13 | Frontend tier system + pages |
| 5 | Task 14 | Analytics |
| 6 | Tasks 15-17 | Saved searches, alerts, rate limiting |

**Total: 17 tasks across 6 phases.**

**Dependencies:**
- Phase 1 must complete before all other phases
- Phase 2 can run in parallel with Phase 3 (after Phase 1)
- Phase 4 depends on Phase 1 (tier types) and Phase 2 (checkout URL)
- Phases 5-6 are independent of Phase 4

**New env vars needed:**
```bash
# backend/.env additions
SUPABASE_JWT_SECRET=...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
RESEND_API_KEY=re_...
ALERT_FROM_EMAIL=alerts@homescout.app
```

**New dependencies:**
```
# backend/requirements.txt additions
PyJWT[crypto]==2.9.0
supabase==2.11.0
stripe==11.4.1
resend==2.5.0
```