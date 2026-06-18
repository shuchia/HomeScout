# Auth & Billing

> Last verified: 2026-05-04 | Source of truth: this doc + the code it references
>
> Deeper diagrams of the OAuth/PKCE handshake live in `docs/auth-flow.md`. This doc is the working reference.

Supabase handles identity (Google OAuth → JWT). Backend verifies the JWT and gates features by tier. Stripe handles paid upgrades.

## Quick Commands

```bash
# Mock auth for E2E
# In browser console before navigating:
localStorage.__test_auth_user = JSON.stringify({id: "test-uuid", email: "test@snugd.ai"})
localStorage.__test_auth_profile = JSON.stringify({user_tier: "pro"})  # optional

# Verify a JWT manually
echo "$TOKEN" | cut -d. -f2 | base64 -d | jq .

# Stripe webhook test (CLI)
stripe listen --forward-to http://localhost:8000/api/webhooks/stripe
stripe trigger checkout.session.completed
```

## Architecture

```
Frontend                              Backend
─────────                             ────────
[Sign-In] ─Google OAuth (PKCE)─► Supabase Auth ─JWT─► AuthContext
                                                       │
                                                       ▼
                                                 auth-store (sync)
                                                       │
                                  Bearer ─────► [auth.py: get_*_user]
                                                       │
                                                       ▼
                                                 [tier_service]
                                                       │
                                                       ▼
                                                 Pro / Free / Anon paths
```

## Auth Flow

1. **Sign-in**: `signInWithGoogle()` → Supabase OAuth (PKCE) → Google consent → `/auth/callback?code=...`.
2. **Callback**: `app/auth/callback/page.tsx` calls `supabase.auth.exchangeCodeForSession(code)`. Session stored in localStorage by the Supabase client; `onAuthStateChange(SIGNED_IN)` fires.
3. **AuthContext applies session**: stores `session`/`user`, mirrors `access_token` to the synchronous `auth-store` module, fetches `profiles` row to populate `tier`/`isPro`.
4. **API calls**: `lib/api.ts::getAuthHeaders()` reads token synchronously from auth-store and sets `Authorization: Bearer <jwt>`.
5. **Refresh**: Supabase client auto-refreshes on a timer; `onAuthStateChange(TOKEN_REFRESHED)` propagates the new token via the same applySession path.
6. **Sign-out**: `signOut()` clears Supabase session + auth-store + comparison localStorage; `onAuthStateChange(SIGNED_OUT)` fires.

The 5-second safety timeout in `AuthContext` proceeds as anonymous if `getSession()` ever hangs.

**E2E bypass**: when `NODE_ENV !== 'production'`, `AuthContext` reads `localStorage.__test_auth_user` (and optional `__test_auth_profile`) and skips Supabase entirely.

## Backend JWT Verification

`backend/app/auth.py`:

- Audience: `"authenticated"`.
- **Algorithms**: ES256 verified via Supabase JWKS, with **HS256 fallback** using `SUPABASE_JWT_SECRET`. (Older docs that say HS256 only are stale.)
- `get_current_user(authorization)` → `UserContext(user_id, email)` or **401**.
- `get_optional_user(authorization)` → `UserContext | None` (never raises — used for optionally-gated endpoints).

Used by:

| Dependency | Endpoints |
|------------|-----------|
| `get_current_user` | `/api/billing/checkout`, `/api/billing/portal`, `/api/saved-searches`, `/api/tours/*`, `/api/search/score-batch` |
| `get_optional_user` | `/api/search`, `/api/apartments/compare` |

## Tier System

| Tier | Auth | Searches/day | AI scoring | Compare AI | Saved searches | Favorites | Tours AI |
|------|------|--------------|------------|------------|----------------|-----------|----------|
| anonymous | none | unlimited (no metering) | no | no | n/a | n/a | n/a |
| free | authed | **20** (`FREE_DAILY_SEARCH_LIMIT` in `tier_service.py`) | no | no | 403 | 5 max | no |
| pro | authed + paid | unlimited | yes | yes | unlimited | unlimited | yes |

Tier is stored in Supabase `profiles.user_tier`. Defaults to `"free"` if the row is missing or the column is null. `TierService.get_user_tier()` queries Supabase via the service-role client.

> Note: the older "3 searches/day" copy in some docs is stale. Code currently allows 20.

## TierService

`backend/app/services/tier_service.py`:

| Method | Notes |
|--------|-------|
| `get_user_tier(user_id)` | Reads `profiles.user_tier`; defaults to `"free"` |
| `check_search_limit(user_id)` | Redis key `search_count:{user_id}:{YYYY-MM-DD}`, TTL 48h. Returns `(allowed, remaining)` |
| `increment_search_count(user_id)` | Redis INCR on the same key |
| `update_user_tier(user_id, tier, **kwargs)` | Updates Supabase profile (called from Stripe webhook) |

**Fail-open**: if Redis or Supabase is unreachable, requests are allowed (better to over-serve than to lock everyone out).

## Stripe Integration

Endpoints in `backend/app/routers/billing.py`:

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/billing/checkout` | required | Create Stripe Checkout Session for the `STRIPE_PRICE_ID` ($12/mo Pro plan) |
| POST | `/api/billing/portal` | required | Create Stripe Customer Portal session for the user's `stripe_customer_id` |
| POST | `/api/webhooks/stripe` | Stripe sig | Webhook handler |

Webhook events handled:

| Event | Action |
|-------|--------|
| `checkout.session.completed` | Set `user_tier=pro`, store `stripe_customer_id`, set `current_period_end` |
| `customer.subscription.updated` | Update `subscription_status`, `current_period_end` |
| `customer.subscription.deleted` | Revert `user_tier=free` |
| `invoice.payment_failed` | Set `subscription_status=past_due` |

Required env: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID`.

## Invite Codes

`backend/app/routers/invite.py`:

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/invite/redeem` | required | Redeem a code; grants Pro for **90 days** |
| GET | `/api/invite/status` | required | Returns the user's invite-grant expiry and origin code |
| POST | `/api/admin/invite-codes` | `X-Admin-Key` | Mint new codes |

Atomic `times_used` increment avoids TOCTOU; redemption sets `user_tier=pro` and `current_period_end` 90 days out. UI surface: `frontend/components/InviteCodeBanner.tsx`. Tables defined in `supabase/migrations/006_beta_launch.sql`.

**Minting** (`POST /api/admin/invite-codes`): `count` (1–50), `max_uses` (1–100, per-code redemption cap — each user can redeem a given code only once), `prefix` (default `BETA`), optional `expires_at` (ISO8601). A **shared** code is just one code with `max_uses` set to the group size. Pass `code` (e.g. `"BETA-GIRLHACKS"`) to mint a single **vanity** code with that exact value — it overrides `prefix`/`count`, is uppercased to match redemption, and returns 409 if the code already exists.

## Rate Limiting

`backend/app/middleware/rate_limit.py`. Redis sliding window per minute. Identity: authed users keyed by token hash, anonymous by IP. Fail-open. Skipped when `TESTING=1`.

| Constant | Limit | Applies to |
|----------|-------|-----------|
| `GLOBAL_LIMIT` | **120/min** | Authenticated users |
| `ANON_LIMIT` | **30/min** | Anonymous (IP) |
| `EXPENSIVE_LIMIT` | **20/min** | `/api/search`, `/api/apartments/compare` regardless of auth |

Returns `429` with `{"detail": "Rate limit exceeded. Please slow down."}`.

## Frontend Auth State

`AuthContext` exposes:

- `user`, `session`, `accessToken`
- `profile` (Supabase `profiles` row), `tier`, `isPro`
- `signInWithGoogle()`, `signOut()`, `refreshProfile()`

The 5-second safety timeout: if Supabase doesn't respond to `getSession()` in time, AuthContext continues with `user=null` so the UI doesn't hang. API calls then go out anonymous.

`auth-store.ts` is a **module-level synchronous** token store — `getAccessToken()` returns the current token without `await`, used in API client hot paths.

## Frontend Tier Gating

| Surface | Gate |
|---------|------|
| Search results | Anonymous gets filtered results, no metering; free gets 20/day metering and no AI; Pro unlimited + AI |
| Favorites | Free capped at 5 (UI shows upgrade prompt) |
| Saved searches button | Pro only — backend returns 403 for free |
| AI match badge | Hidden for free/anon |
| Comparison AI panel | Hidden for free/anon, shows `UpgradePrompt` |
| Tours AI tabs (email, day plan, decision brief, note enhance) | Pro only via `UpgradePrompt` |

## Supabase Schema

Migrations in `supabase/migrations/` (001 → 008):

| Migration | Purpose |
|-----------|---------|
| `001_initial_schema.sql` | profiles, favorites, saved_searches, notifications + RLS |
| `002_add_tier_columns.sql` | `user_tier`, `stripe_customer_id`, `subscription_status`, `current_period_end` on profiles |
| `003_add_analytics_events.sql` | `analytics_events` (event_type, metadata JSONB, user_id FK) |
| `004_update_saved_searches.sql` | `last_alerted_at`, `is_active` on saved_searches + service update policy |
| `005_tour_pipeline.sql` | `tour_pipeline`, `tour_notes`, `tour_photos`, `tour_tags` |
| `006_beta_launch.sql` | invite codes, redemption table |
| `007_waitlist.sql` | waitlist signups |
| `008_tour_contact_info.sql` | landlord contact fields on `tour_pipeline` |

## Common Issues

| Issue | Fix |
|-------|-----|
| 401 on backend with valid-looking token | JWT signed with the wrong key; verify `SUPABASE_JWT_SECRET` matches the project, or that JWKS endpoint is reachable for ES256 |
| "Session expired" loop | Token expired and refresh failed (network or refresh-token revoked); user must sign back in |
| Stripe webhook signature failure | `STRIPE_WEBHOOK_SECRET` mismatch between env and the webhook endpoint config in Stripe dashboard |
| Free user sees Pro features briefly | `AuthContext` populates `tier` after profile fetch; gate UI on `tier !== 'free'` not on `user` alone |
| Test bypass not working in prod build | E2E bypass is dev-only by design (`NODE_ENV !== 'production'`) |
| Invite code "already redeemed" | Atomic increment on `times_used` enforces single-use per code |

## File Reference

| File | Role |
|------|------|
| `backend/app/auth.py` | JWT verification, dependencies |
| `backend/app/services/tier_service.py` | Tier lookup, search metering, tier updates |
| `backend/app/routers/billing.py` | Stripe checkout, portal |
| `backend/app/routers/webhooks.py` | Stripe + Supabase webhook handlers |
| `backend/app/routers/invite.py` | Invite redemption + admin |
| `backend/app/middleware/rate_limit.py` | Redis sliding window |
| `frontend/contexts/AuthContext.tsx` | React auth state + 5s timeout |
| `frontend/lib/auth-store.ts` | Synchronous token mirror |
| `frontend/lib/supabase.ts` | Supabase client init |
| `frontend/app/auth/callback/page.tsx` | OAuth code exchange |
| `frontend/components/InviteCodeBanner.tsx` | Invite redemption UI |