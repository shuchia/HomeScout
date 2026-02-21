# User Flows & Monetization Design

**Date:** 2026-02-21
**Status:** Approved
**Approach:** Hybrid — Renter Freemium now, Landlord Lead-Gen later

## Overview

HomeScout currently has Google OAuth and basic user features (favorites, comparison). This design adds the full user lifecycle: onboarding, tier-gated features, Stripe payments, usage tracking, email alerts, and session/security hardening.

**Monetization strategy:** Launch a renter freemium model immediately ($12/mo Pro tier). Use traffic and engagement data to build landlord-side monetization in a future phase.

## Tier Structure

| Feature | Free | Pro ($12/mo) |
|---|---|---|
| Search | 3/day | Unlimited |
| AI Scoring | No | Yes |
| Compare | Side-by-side table only | + Claude analysis |
| Favorites | 5 max | Unlimited |
| Saved Searches | No | Yes |
| Alerts | No | Daily email digest |

---

## 1. User Journey & Account Lifecycle

### States

```
Anonymous → Sign Up (Google OAuth) → Free Tier → [Upgrade] → Pro Tier
                                        |                       |
                                        +-- Profile Settings <--+
                                        +-- Session Management <+
                                        +-- Delete Account <----+
```

### Onboarding

- First-time visitor lands on `/` with hero section explaining HomeScout + "Sign in to search" CTA
- After Google OAuth, redirect to search page with one-time toast: "Welcome! You have 3 free searches per day"
- No onboarding wizard — keep it lightweight

### Login / Logout

- Login: Google OAuth via Supabase (already built)
- Logout: UserMenu → "Sign out" → clears Supabase session + Zustand stores + redirects to `/`

### Session Management

- Supabase handles JWT tokens with auto-refresh (1h expiry)
- If token expired and refresh fails → redirect to login with toast "Session expired, please sign in again"
- No custom session table — Supabase handles this

### Account Settings Page (`/settings`)

- **Profile:** name, email (read-only from Google), avatar
- **Subscription:** current plan, "Manage Billing" button (Stripe Customer Portal)
- **Data:** export my data (favorites + saved searches as JSON), delete account
- **Notifications:** email alert toggle (Phase 2 refinement)

### Account Deletion

- Settings → "Delete Account" → confirmation modal
- Backend: `auth.admin.deleteUser()` + cascade delete profiles, favorites, saved_searches
- Stripe: cancel active subscription
- Analytics events: anonymize (set `user_id = NULL`), don't delete
- Redirect to `/` with toast "Account deleted"

---

## 2. Tier System & Gating UX

### Gate Enforcement

All gates enforced on the backend (source of truth). Frontend mirrors for UX.

| Feature | Gate Location | Free UX |
|---|---|---|
| Search | Backend rate limit + frontend counter | "2 of 3 searches remaining today" below form; at limit: form disables + upgrade CTA |
| AI Scoring | Backend skips scoring + frontend hides scores | Blurred/locked score badge: "Upgrade to see AI match score" |
| Compare | Backend blocks Claude call + frontend lock icon | Lock icon on "Score" button; clicking opens upgrade modal |
| Favorites | Backend rejects save at limit + frontend toast | Toast: "You've reached the free limit. Upgrade for unlimited favorites." |
| Saved Searches | Frontend hides button for free users | Pro badge on "Save this search" button |

### Upgrade Prompts

- Every gate point links to `/pricing` or opens Stripe Checkout directly
- Contextual, inline prompts at the moment the user hits a limit
- No aggressive popups

### Backend: Tier Check

- New `user_tier` field on `profiles` table: `'free' | 'pro'`
- FastAPI dependency injection checks tier before expensive operations
- Daily search counter in Redis: `search_count:{user_id}:{YYYY-MM-DD}` with 48h TTL

---

## 3. Payments & Billing (Stripe)

### Architecture

```
User clicks "Upgrade" → Stripe Checkout (hosted) → Webhook → profile updated
User clicks "Manage Billing" → Stripe Customer Portal (hosted) → Webhook → profile updated
```

Use Stripe's hosted pages exclusively. No custom payment forms. PCI-compliant out of the box.

### Upgrade Flow

1. User hits gate → CTA links to `/pricing` or triggers checkout
2. `/pricing` page: Free vs Pro side-by-side, "Get Pro" button
3. Backend creates Stripe Checkout Session → redirect to Stripe
4. User pays → redirect to `/settings?upgrade=success` → success toast
5. `checkout.session.completed` webhook → set `user_tier = 'pro'`, store `stripe_customer_id`

### Billing Management

- Settings → "Manage Billing" → backend creates Stripe Customer Portal session → redirect
- Portal handles: update card, view invoices, cancel subscription
- No custom billing UI

### Cancellation

- User cancels via Stripe Portal
- `customer.subscription.updated` webhook → mark `cancel_at_period_end`
- Access continues until billing period ends
- `customer.subscription.deleted` webhook → set `user_tier = 'free'`
- Favorites beyond 5 preserved but read-only (view/remove, can't add)

### Failed Payments

- Stripe retries automatically (3 attempts over ~2 weeks)
- Stripe sends its own dunning emails (skip custom email for MVP)
- After final failure: `customer.subscription.deleted` → downgrade

### New API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/billing/checkout` | POST | Create Stripe Checkout Session, return URL |
| `/api/billing/portal` | POST | Create Stripe Customer Portal session, return URL |
| `/api/webhooks/stripe` | POST | Handle Stripe events (signature-verified) |

### Database Changes

```sql
ALTER TABLE profiles ADD COLUMN user_tier TEXT NOT NULL DEFAULT 'free';
ALTER TABLE profiles ADD COLUMN stripe_customer_id TEXT;
ALTER TABLE profiles ADD COLUMN subscription_status TEXT;  -- 'active', 'canceled', 'past_due'
ALTER TABLE profiles ADD COLUMN current_period_end TIMESTAMPTZ;
```

### Webhook Events

| Event | Action |
|---|---|
| `checkout.session.completed` | Set tier to 'pro', store stripe_customer_id |
| `customer.subscription.updated` | Update subscription_status, current_period_end |
| `customer.subscription.deleted` | Set tier to 'free' |
| `invoice.payment_failed` | Set subscription_status to 'past_due' |

---

## 4. Usage Tracking & Analytics

### Usage Metering (for tier enforcement)

Redis counters — lightweight, auto-expiring.

```
search_count:{user_id}:{YYYY-MM-DD}  →  integer, TTL 48h
compare_count:{user_id}:{YYYY-MM-DD} →  integer, TTL 48h
```

- Increment on each request, check before executing Claude calls
- If Redis is down, fail open (allow the request)

### Product Analytics

Event logging to a Supabase table. No third-party analytics tool for MVP.

```sql
CREATE TABLE analytics_events (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id),
  event_type TEXT NOT NULL,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_events_type_date ON analytics_events(event_type, created_at);
CREATE INDEX idx_events_user ON analytics_events(user_id);
```

### Events to Track

| Event | Metadata | Purpose |
|---|---|---|
| `search` | city, filters, result_count | Popular markets, search patterns |
| `gate_hit` | gate_type | Which gate drives conversions |
| `upgrade` | source_gate, plan | What triggered the upgrade |
| `downgrade` | reason | Churn analysis |
| `compare` | apartment_count, used_ai | Feature usage |
| `favorite` | apartment_id | Demand signal for landlord phase |

### Claude Cost Tracking

Log token usage from Claude API responses in event metadata: `{input_tokens: 1200, output_tokens: 800}`. Query gives cost per user, cost per search, margin per Pro subscriber.

### No admin dashboard for MVP. Query Supabase directly with SQL.

---

## 5. Notifications & Alerts

### MVP Scope: Daily Email Digest Only

No in-app notifications, no push, no SMS.

### Architecture

```
Celery Beat (daily 8am ET)
  → find Pro users with active saved searches
  → for each: query DB for new listings since last_alerted_at
  → if matches found: send email via Resend
  → update last_alerted_at
```

### Saved Search Changes

```sql
ALTER TABLE saved_searches ADD COLUMN last_alerted_at TIMESTAMPTZ;
ALTER TABLE saved_searches ADD COLUMN is_active BOOLEAN DEFAULT true;
```

### Email Content

- Subject: "3 new apartments in Pittsburgh match your search"
- Body: apartment name, rent, beds/baths, link to HomeScout listing page
- Footer: "Manage alerts" link → `/settings`
- No AI scoring in emails (avoids Claude cost per alert)

### Email Provider: Resend

- Simple API, 3,000 emails/mo free tier
- Single API call per email
- Sufficient for early user base

### Gating

- "Save this search" button only appears for Pro users
- Free users see "Upgrade to Pro to save searches and get daily alerts"
- Backend rejects saved search creation if `user_tier != 'pro'`

### NOT in MVP

- In-app notification center
- Push notifications
- Real-time/instant alerts
- Customizable alert frequency
- AI-scored alerts

---

## 6. Security & Session Hardening

### Session Invalidation

- Supabase JWTs: 1h expiry, auto-refresh via refresh token
- Logout: `supabase.auth.signOut()` invalidates refresh token server-side
- Account deletion: admin API revokes all sessions before deleting
- Downgrade: no session invalidation — next API call reads updated tier

### Stripe Webhook Security

- Verify every webhook with `stripe.webhooks.constructEvent()` + signing secret
- Reject unverified payloads with 400
- Idempotent handling: store processed `event.id` in Redis with 24h TTL

### Rate Limiting

| Scope | Limit |
|---|---|
| Global (all endpoints, per user) | 60 req/min |
| Expensive endpoints (search, compare) | 10 req/min |
| Anonymous (no auth) | 10 req/min |

Implement via Redis + FastAPI middleware.

### API Security

- CORS: add production domain alongside localhost:3000
- Stripe webhook endpoint excluded from CORS
- All billing endpoints require authenticated user (Supabase JWT)

### Data Privacy

- Account deletion cascades: profiles → favorites → saved_searches
- Analytics events anonymized on deletion (set `user_id = NULL`)
- Data export: JSON of favorites + saved searches
- No PII beyond Google OAuth data (name, email, avatar)
- Stripe handles all payment data — no card numbers stored

### New Environment Variables

```bash
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
RESEND_API_KEY=re_...
```

---

## Phase 2: Landlord Monetization (Future)

Deferred until renter freemium validates demand. Potential features:

- Landlord portal: listing management, lead tracking
- Paid listings ($25-50/listing) or subscription ($99/mo)
- Analytics dashboard for landlords (views, favorites, inquiries)
- Renter engagement data as the sales pitch to landlords
