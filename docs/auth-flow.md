# HomeScout Authentication & Session Flow

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                            │
│                                                                      │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────┐              │
│  │ AuthButton / │───>│ Supabase     │───>│ Google /   │              │
│  │ UserMenu     │    │ OAuth Client │    │ Apple IdP  │              │
│  └─────────────┘    └──────────────┘    └────────────┘              │
│         │                                      │                     │
│         ▼                                      ▼                     │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │                    AuthContext                           │        │
│  │  • Tracks Session (user, token) in React state          │        │
│  │  • Listens to onAuthStateChange for token refresh       │        │
│  │  • Pushes token to auth-store on every change           │        │
│  │  • Fetches profile (tier, subscription) from Supabase   │        │
│  └─────────────────────────────────────────────────────────┘        │
│         │                                                            │
│         ▼                                                            │
│  ┌──────────────┐    ┌──────────────┐                               │
│  │ auth-store   │───>│ lib/api.ts   │──── Bearer token ────┐       │
│  │ (sync token) │    │ (sync read)  │                      │       │
│  └──────────────┘    └──────────────┘                      │       │
│                                                             │       │
└─────────────────────────────────────────────────────────────│───────┘
                                                              │
                                                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       Backend (FastAPI)                               │
│                                                                      │
│  ┌──────────────────┐    ┌─────────────────┐                        │
│  │ auth.py           │    │ tier_service.py  │                       │
│  │ • Decode JWT      │───>│ • Check user_tier│                       │
│  │ • Verify HS256    │    │ • Enforce limits │                       │
│  │ • Extract user_id │    └─────────────────┘                        │
│  └──────────────────┘                                                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 1. Sign-In Flow

```
User clicks "Sign in with Google"
        │
        ▼
AuthButton.tsx ──> useAuth().signInWithGoogle()
        │
        ▼
supabase.auth.signInWithOAuth({
  provider: 'google',
  redirectTo: '/auth/callback'
})
        │
        ▼
Browser redirects to Google consent screen
        │
        ▼
Google redirects back to /auth/callback?code=<auth_code>
        │
        ▼
auth/callback/page.tsx:
  • Extracts `code` from URL search params
  • Calls supabase.auth.exchangeCodeForSession(code)   ← PKCE flow
  • Supabase client stores session (access_token + refresh_token) in cookies
  • Redirects to /
        │
        ▼
AuthContext picks up session via onAuthStateChange(SIGNED_IN, session)
  • Stores Session in React state
  • Pushes access_token to auth-store module
  • Fetches user profile from Supabase `profiles` table
  • Sets tier (free/pro) and isPro flag
```

---

## 2. Token Storage & Access (The Key Design)

**Problem solved:** The `@supabase/ssr` `createBrowserClient` stores sessions in cookies and requires Next.js middleware to refresh them. Without middleware, tokens go stale and `getSession()` hangs.

**Solution:** Use the standard `@supabase/supabase-js` `createClient` with localStorage storage (reliable auto-refresh, no middleware needed). API requests read from a sync token store — never call `getSession()`:

```
┌─────────────────────────────┐
│  Supabase Client            │
│  (auto-refresh via cookies) │
│         │                   │
│  fires onAuthStateChange    │
│  on SIGNED_IN,              │
│     SIGNED_OUT,             │
│     TOKEN_REFRESHED         │
└─────────┬───────────────────┘
          │
          ▼
┌─────────────────────────────┐
│  AuthContext.applySession() │
│  • setSession(s)            │
│  • setUser(s.user)          │
│  • setAccessToken(s.token)  │──────> auth-store.ts (module-level variable)
└─────────────────────────────┘
                                            │
                                            ▼ (synchronous read)
                                    ┌───────────────────┐
                                    │  lib/api.ts        │
                                    │  getAuthHeaders()  │
                                    │  → { Authorization: │
                                    │    Bearer <token> } │
                                    └───────────────────┘
```

**Key files:**

| File | Role |
|------|------|
| `lib/auth-store.ts` | Module-level `_accessToken` variable. `setAccessToken()` / `getAccessToken()` — purely synchronous. |
| `contexts/AuthContext.tsx` | Writes to auth-store on every session change. Exposes `accessToken` prop to React components. |
| `lib/api.ts` | `getAuthHeaders()` reads synchronously from auth-store. Zero async, zero hanging. |

---

## 3. Token Refresh

Supabase access tokens expire after **1 hour**. The refresh flow:

```
Supabase client internal timer (automatic)
        │
        ▼
Detects access_token is near expiry
        │
        ▼
Uses refresh_token to get new access_token from Supabase Auth API
        │
        ▼
Fires onAuthStateChange(TOKEN_REFRESHED, newSession)
        │
        ▼
AuthContext.applySession(newSession)
        │
        ▼
auth-store updated with fresh token
        │
        ▼
Next API call automatically uses new token
```

**No manual refresh logic needed.** The Supabase client handles the refresh interval internally, and `onAuthStateChange` propagates it.

---

## 4. Sign-Out Flow

```
User clicks "Sign Out" in UserMenu
        │
        ▼
useAuth().signOut()
        │
        ▼
supabase.auth.signOut()
  • Clears cookies / local storage
  • Fires onAuthStateChange(SIGNED_OUT, null)
        │
        ▼
AuthContext.applySession(null)
  • session = null, user = null
  • auth-store token = null
  • profile = null
  • Clears comparison localStorage
        │
        ▼
UI re-renders: shows AuthButton instead of UserMenu
API calls go out without Authorization header (anonymous)
```

---

## 5. Backend JWT Verification

```
Incoming request with header:
  Authorization: Bearer <supabase_access_token>
        │
        ▼
auth.py: get_current_user() or get_optional_user()
        │
        ▼
jwt.decode(
  token,
  SUPABASE_JWT_SECRET,     ← from .env
  algorithms=["HS256"],
  audience="authenticated"
)
        │
        ├── Success → UserContext(user_id=payload["sub"], email=payload["email"])
        │
        └── Failure (expired, bad signature, missing) →
              get_current_user:  raises HTTP 401
              get_optional_user: returns None (anonymous access)
```

**Two dependency variants:**

| Dependency | Used on | Behavior if no/bad token |
|------------|---------|--------------------------|
| `get_current_user` | `/api/billing/checkout`, `/api/billing/portal` | 401 Unauthorized |
| `get_optional_user` | `/api/search`, `/api/apartments/compare` | Returns `None` → anonymous tier |

---

## 6. Tier System Integration

```
AuthContext fetches profile after sign-in:
  supabase.from('profiles').select('*').eq('id', userId)
        │
        ▼
profile.user_tier → 'free' | 'pro'
        │
        ▼
tier = user ? profile.user_tier : 'anonymous'
isPro = tier === 'pro'
        │
        ├── Frontend: gates UI features (favorites limit, AI scoring, saved searches)
        │
        └── Backend: TierService checks tier for rate limits and feature access
```

**Tier upgrades via Stripe:**
```
Pricing page → POST /api/billing/checkout (with Bearer token)
  → Stripe Checkout Session created
  → User completes payment on Stripe
  → Stripe webhook → POST /api/webhooks/stripe
  → TierService.update_user_tier(user_id, "pro")
  → profiles.user_tier = 'pro'
  → User redirected to /settings?upgrade=success
  → AuthContext.refreshProfile() picks up new tier
```

---

## 7. Protected Page Patterns

**Pages that require auth:**
```tsx
// Read accessToken from context (synchronous, never hangs)
const { user, accessToken } = useAuth()

// For direct API calls in components:
fetch('/api/billing/checkout', {
  headers: { Authorization: `Bearer ${accessToken}` }
})

// For API client calls (token attached automatically via auth-store):
searchApartments(params)  // lib/api.ts reads from auth-store
```

**Pages that work without auth (degraded):**
- `/` (search) — anonymous gets limited results, no AI scoring
- `/compare` — anonymous gets comparison but no AI analysis

---

## 8. Error Handling

| Scenario | Behavior |
|----------|----------|
| `getSession()` hangs on initial load | 5-second timeout in AuthContext, UI proceeds as anonymous |
| Token expired between refreshes | `onAuthStateChange(TOKEN_REFRESHED)` fires with new token automatically |
| Supabase completely unreachable | Timeout fires, user shown as anonymous, API calls go without auth |
| Backend gets expired token | Returns 401, frontend shows "Session expired. Please sign out and sign back in." |
| OAuth callback fails | Console error logged, user redirected to / after 5s safety timeout |

---

## File Reference

| File | Purpose |
|------|---------|
| `frontend/lib/supabase.ts` | Supabase client init (`createBrowserClient`) |
| `frontend/lib/auth-store.ts` | Synchronous token store (module-level variable) |
| `frontend/contexts/AuthContext.tsx` | React auth state, session tracking, profile fetch |
| `frontend/lib/api.ts` | API client, attaches auth headers synchronously |
| `frontend/app/auth/callback/page.tsx` | OAuth code exchange (PKCE) + redirect |
| `frontend/components/AuthButton.tsx` | Sign-in button |
| `frontend/components/UserMenu.tsx` | Authenticated user dropdown |
| `frontend/app/layout.tsx` | Wraps app in `<AuthProvider>` |
| `backend/app/auth.py` | JWT decode + FastAPI dependencies |
| `backend/app/services/tier_service.py` | Tier lookup + rate limiting |
| `backend/app/routers/billing.py` | Stripe checkout, portal, webhooks |
