# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

### Frontend (Next.js)
```bash
cd frontend
npm install              # Install dependencies
npm run dev              # Start dev server (port 3000)
npm run build            # Production build
npm run lint             # Run ESLint
```

### Backend (FastAPI)
```bash
cd backend
pip install -r requirements.txt                    # Install dependencies
uvicorn app.main:app --reload --port 8000          # Start dev server
# API docs: http://localhost:8000/docs (Swagger UI)
```

### Testing Endpoints
```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/apartments/count
curl http://localhost:8000/api/apartments/stats
curl "http://localhost:8000/api/apartments/list?city=Pittsburgh&limit=10"
```

## Full Startup Process

### Prerequisites
Ensure these services are running before starting the application:

```bash
# 1. PostgreSQL (required for database mode)
brew services start postgresql@16
# Verify: lsof -i :5432

# 2. Redis (required for Celery task queue)
brew services start redis
# Verify: redis-cli ping  # Should return PONG
```

### Backend Startup (Database Mode)

```bash
cd backend

# 1. Activate virtual environment
source .venv/bin/activate

# 2. Ensure .env has database enabled
# Required vars: USE_DATABASE=true, DATABASE_URL, REDIS_URL, ANTHROPIC_API_KEY

# 3. Start FastAPI server (without --reload to avoid venv file watching issues)
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 4. Verify backend is running
curl http://localhost:8000/health
# Expected: {"status":"healthy","message":"HomeScout API is healthy..."}
```

### Celery Worker Startup (for Data Collection)

```bash
cd backend
source .venv/bin/activate

# Start Celery worker (handles scraping tasks)
celery -A app.celery_app worker --loglevel=info -Q celery,scraping,maintenance

# Optional: Start Celery beat (scheduled tasks)
celery -A app.celery_app beat --loglevel=info
```

### Frontend Startup

```bash
cd frontend

# 1. Install dependencies (if needed)
npm install

# 2. Start development server
npm run dev

# 3. Verify frontend is running
# Open http://localhost:3000 in browser
```

### Quick Start (All Services)

```bash
# Terminal 1: Backend
cd backend && source .venv/bin/activate && .venv/bin/python -m uvicorn app.main:app --port 8000

# Terminal 2: Celery Worker (optional, for scraping)
cd backend && source .venv/bin/activate && celery -A app.celery_app worker --loglevel=info -Q celery,scraping,maintenance

# Terminal 3: Frontend
cd frontend && npm run dev
```

### Verification Checklist

```bash
# Backend health
curl http://localhost:8000/health

# Database stats (shows scraped listings by city)
curl http://localhost:8000/api/apartments/stats

# List apartments
curl "http://localhost:8000/api/apartments/list?limit=5"

# Frontend
open http://localhost:3000
```

### Triggering a Manual Scrape

```bash
# Scrape apartments.com for all MVP cities (Philadelphia, Bryn Mawr, Pittsburgh)
curl -X POST http://localhost:8000/api/admin/data-collection/jobs \
  -H "Content-Type: application/json" \
  -d '{"source": "apartments_com", "max_listings": 50}'
```

### Common Issues

| Issue | Solution |
|-------|----------|
| `Event loop is closed` | Restart Celery worker - httpx client state issue |
| Server hangs at startup | Check PostgreSQL is running: `lsof -i :5432` |
| Celery tasks not running | Check Redis is running: `redis-cli ping` |
| `--reload` causes issues | Don't use `--reload` flag with uvicorn |
| Port 8000 in use | Kill existing: `pkill -f "uvicorn app.main"` |

## Architecture

HomeScout is a full-stack apartment finder using Claude AI for intelligent matching, with Supabase for authentication and user data.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Frontend (Next.js)                          │
├─────────────────────────────────────────────────────────────────────────┤
│  SearchForm → API Client → Results Grid (ApartmentCard)                 │
│  AuthContext (Google OAuth + tier) ←→ Supabase Auth                     │
│  useFavorites hook ←→ Supabase Database (favorites table)               │
│  useComparison (Zustand+persist) → Compare Page + Claude Analysis       │
│  Auth gates on Search + Compare pages (require sign-in)                 │
│  Tier gating: free (3 searches/day, 5 favorites) vs pro (unlimited)    │
│  /pricing, /settings pages for billing + account management             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Backend (FastAPI)                              │
├─────────────────────────────────────────────────────────────────────────┤
│  /api/search              → Filter + Claude AI scoring (pro only)       │
│  /api/apartments/{id}     → Get single apartment (DB or JSON)           │
│  /api/apartments/batch    → Get multiple apartments by ID (DB or JSON)  │
│  /api/apartments/compare  → Claude analysis (pro) or basic (free)       │
│  /api/billing/*           → Stripe checkout, portal, webhooks           │
│  /api/saved-searches      → CRUD saved searches (pro only)              │
│  /api/webhooks/stripe     → Stripe event handling                       │
│  /api/webhooks/supabase   → Handle Supabase events                      │
│  Rate limiting middleware → Redis-based (60/min auth, 10/min anon)      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Data Sources                                   │
├─────────────────────────────────────────────────────────────────────────┤
│  PostgreSQL (scraped data) │ apartments.json (fallback/mock)            │
│  MarketConfig (19 markets) │ Claude AI (scoring + comparison analysis)  │
│  Apify (apartments.com)   │ Redis (Celery + rate limits + metering)    │
│  Stripe (payments)        │ Resend (email alerts)                      │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Flow: Search
1. User signs in via Google OAuth (auth gate on search page)
2. User submits search criteria via `SearchForm.tsx`
3. `lib/api.ts` sends POST to `/api/search` with Supabase JWT
4. Backend verifies JWT via `auth.py`, determines tier via `TierService`
5. **Free tier**: checks daily search limit (3/day via Redis counter), returns filtered results without AI scoring
6. **Pro tier**: `claude_service.py` calls Claude API, returns scored results with `match_score`, `reasoning`, `highlights`
7. Frontend displays results; free users see "Pro" badge instead of match scores
8. Response includes `tier` and `searches_remaining` for UI state
9. Users can favorite apartments (saved to Supabase) or add to comparison
10. Search context (city, budget, etc.) is saved to Zustand store for the compare page

### Key Flow: Comparison
1. User selects 2-3 apartments via CompareButton on apartment cards
2. ComparisonBar shows selected apartments, user clicks "Compare"
3. Compare page loads apartments from `/api/apartments/compare`
4. **Free tier**: sees comparison table but "Score" button shows UpgradePrompt
5. **Pro tier**: clicks "Score" for Claude AI head-to-head analysis
6. Backend calls `claude_service.compare_apartments_with_analysis()`
7. Claude returns winner, category scores (Value, Space, Amenities, etc.), reasoning
8. Frontend displays winner summary card, category breakdown grid, and comparison table

### Key Flow: Upgrade to Pro
1. User clicks upgrade CTA (UpgradePrompt, pricing page, or settings page)
2. Frontend calls `POST /api/billing/checkout` with Supabase JWT
3. Backend creates Stripe Checkout Session with `client_reference_id = user_id`
4. User completes payment on Stripe hosted page
5. Stripe sends `checkout.session.completed` webhook to `/api/webhooks/stripe`
6. Backend updates `profiles.user_tier = 'pro'` via `TierService.update_user_tier()`
7. Frontend calls `refreshProfile()` to pick up new tier

### Dual Data Mode
The backend supports two data modes, controlled by `USE_DATABASE` env var:
- **JSON Mode** (default): Uses static `app/data/apartments.json`
- **Database Mode**: Uses PostgreSQL with scraped data from Apify

All apartment endpoints (`get`, `batch`, `compare`, `list`) check `is_database_enabled()` and query the appropriate source.

### Type Synchronization
Frontend TypeScript interfaces (`types/apartment.ts`) must match backend Pydantic models (`schemas.py`). Changes to data models require updates in both places.

## Continuous Scraping Pipeline

The backend uses a market-driven dispatcher pattern for continuous apartment scraping:

### Beat Schedule (4 orchestrator tasks)
| Task | Schedule | Purpose |
|------|----------|---------|
| `dispatch_scrapes` | Every hour at :00 | Check which markets are due, spawn scrape tasks |
| `decay_and_verify` | Every hour at :30 | Update confidence scores, dispatch verification |
| `cleanup_maintenance` | Daily at 3 AM | Deactivate dead listings, reset circuit breakers |
| `send_daily_alerts` | Daily at 1 PM UTC (8 AM ET) | Email Pro users with new listings matching saved searches |

### Market Tiers
| Tier | Frequency | Decay Rate | Cities |
|------|-----------|------------|--------|
| Hot | Every 6h | -3/hour | NYC, Boston, DC, Philadelphia |
| Standard | Every 12h | -2/hour | Pittsburgh, Baltimore, Newark, Jersey City, Cambridge, Arlington |
| Cool | Every 24h | -1/hour | Bryn Mawr, Hoboken, Stamford, New Haven, Providence, Richmond, Charlotte, Raleigh, Hartford |

### Freshness Confidence
- New listings start at confidence=100
- Confidence decays based on market tier when not re-seen
- At <40: verification triggered (HTTP check on source URL)
- At 0: listing deactivated (unless verified)
- Re-seen in scrape: confidence resets to 100

### Admin Endpoints
```bash
# List all markets
curl http://localhost:8000/api/admin/data-collection/markets

# Trigger immediate scrape
curl -X POST http://localhost:8000/api/admin/data-collection/markets/bryn-mawr/scrape

# Update market config
curl -X PUT http://localhost:8000/api/admin/data-collection/markets/bryn-mawr \
  -H "Content-Type: application/json" \
  -d '{"tier": "standard", "scrape_frequency_hours": 12}'
```

## Key Files

### Frontend - Core
- `app/page.tsx` - Main page with auth gate, search form + results grid, free search counter
- `app/favorites/page.tsx` - User's saved favorites (requires auth)
- `app/compare/page.tsx` - Enhanced comparison with Claude AI analysis, winner summary, category scores (Score gated to Pro)
- `app/pricing/page.tsx` - Free vs Pro comparison with Stripe checkout button
- `app/settings/page.tsx` - Profile, subscription management, data export, account deletion
- `app/auth/callback/page.tsx` - OAuth callback handler

### Frontend - Components
- `components/SearchForm.tsx` - Search form with all inputs, `onSearchMeta` callback for tier info
- `components/ApartmentCard.tsx` - Apartment display with match score (or "Pro" badge for free), favorite button, compare button
- `components/ImageCarousel.tsx` - Embla carousel for photos
- `components/Header.tsx` - Navigation with auth state + Pricing link
- `components/AuthButton.tsx` - Sign in button
- `components/UserMenu.tsx` - User dropdown menu with Settings link
- `components/FavoriteButton.tsx` - Heart button to save favorites (5 limit alert for free)
- `components/CompareButton.tsx` - Add to comparison button
- `components/ComparisonBar.tsx` - Floating bar showing comparison selection
- `components/UpgradePrompt.tsx` - Reusable upgrade CTA (inline or block mode), links to /pricing

### Frontend - State & Hooks
- `contexts/AuthContext.tsx` - Google OAuth via Supabase, tier/isPro/refreshProfile (E2E test bypass in non-production)
- `hooks/useFavorites.ts` - Favorites CRUD with optimistic updates, 5 favorite limit for free tier (`atLimit`)
- `hooks/useComparison.ts` - Zustand store with persist for comparison state + search context
- `lib/supabase.ts` - Supabase client and type definitions (Profile includes user_tier, subscription_status)
- `lib/api.ts` - API client with auth headers (searchApartments, getApartmentsBatch, compareApartments)
- `types/apartment.ts` - TypeScript interfaces (match_score nullable, SearchResponse includes tier/searches_remaining)

### Backend - API
- `app/main.py` - FastAPI app with tier-gated search endpoint, rate limiting middleware
- `app/auth.py` - Supabase JWT verification (get_current_user, get_optional_user)
- `app/routers/apartments.py` - Apartment detail, batch, compare endpoints (compare gated by tier)
- `app/routers/billing.py` - Stripe checkout, portal, and webhook endpoints
- `app/routers/saved_searches.py` - Saved search CRUD (Pro only)
- `app/routers/webhooks.py` - Supabase webhook handlers
- `app/routers/data_collection.py` - Admin endpoints for scraping jobs
- `app/schemas.py` - Pydantic models
- `app/middleware/rate_limit.py` - Redis-based rate limiting (60/min auth, 10/min anon, 10/min expensive)

### Backend - Services
- `app/services/claude_service.py` - Claude AI integration (search scoring + comparison analysis)
- `app/services/apartment_service.py` - Filter logic, ranking
- `app/services/tier_service.py` - Tier checking (Supabase profiles), Redis daily search metering, tier updates
- `app/services/analytics_service.py` - Fire-and-forget event logging to Supabase analytics_events table
- `app/data/apartments.json` - Fallback dataset (12 Bryn Mawr apartments, used in JSON mode)

### Backend - Data Collection (Infrastructure)
- `app/celery_app.py` - Celery configuration and beat schedule (4 tasks including daily alerts)
- `app/database.py` - Async SQLAlchemy setup
- `app/tasks/scrape_tasks.py` - Scraping task definitions
- `app/tasks/alert_tasks.py` - Daily email alerts for Pro users with saved searches (via Resend)
- `app/services/scrapers/apify_service.py` - Apify integration
- `app/services/normalization/normalizer.py` - Data normalization
- `app/services/deduplication/deduplicator.py` - Duplicate detection

### Database
- `supabase/migrations/001_initial_schema.sql` - Supabase schema (profiles, favorites, saved_searches, notifications)
- `supabase/migrations/002_add_tier_columns.sql` - Add user_tier, stripe_customer_id, subscription_status to profiles
- `supabase/migrations/003_add_analytics_events.sql` - Analytics events table
- `supabase/migrations/004_update_saved_searches.sql` - Add last_alerted_at, is_active to saved_searches

## Environment Variables

### Frontend (`.env.local`)
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

### Backend (`.env`)
```bash
# Required
ANTHROPIC_API_KEY=your-claude-api-key

# Required - Supabase (for auth + tier management)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret

# Required - Stripe (for payments)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...

# Optional - Email alerts
RESEND_API_KEY=re_...
ALERT_FROM_EMAIL=alerts@homescout.app

# Optional - Supabase webhook verification
SUPABASE_WEBHOOK_SECRET=your-webhook-secret

# Optional - Data collection
APIFY_API_TOKEN=your-apify-token
SCRAPINGBEE_API_KEY=your-scrapingbee-key
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/homescout
REDIS_URL=redis://localhost:6379/0

# CORS
FRONTEND_URL=http://localhost:3000
```

## Supabase Setup

### Database Schema
Run all migrations in order in Supabase SQL Editor:

**Tables:**
- `profiles` - User profiles with tier info (user_tier, stripe_customer_id, subscription_status, current_period_end)
- `favorites` - Saved apartments per user
- `saved_searches` - Saved search criteria with alert tracking (last_alerted_at, is_active)
- `notifications` - User notifications
- `analytics_events` - Event logging (search, compare, upgrade events)

**Row Level Security (RLS):**
- Users can only access their own data
- Policies enforce user isolation
- Service role policies for backend tier updates and alert tracking

### Authentication
1. Enable Google OAuth in Supabase Dashboard → Authentication → Providers
2. Add Google Client ID and Secret from Google Cloud Console
3. Set redirect URL: `http://localhost:3000/auth/callback`

## API Endpoints

### Search & Apartments
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/search` | POST | Optional | Search; Pro gets Claude AI scoring, free gets filtered results (3/day limit) |
| `/api/apartments/{id}` | GET | No | Get single apartment (DB or JSON) |
| `/api/apartments/batch` | POST | No | Get multiple apartments by IDs (DB or JSON) |
| `/api/apartments/compare` | POST | Optional | Compare 2-3 apartments; Pro gets Claude analysis, free gets basic comparison |
| `/api/apartments/count` | GET | No | Total apartment count |
| `/api/apartments/list` | GET | No | List apartments with filters (city, rent, bedrooms) |
| `/api/apartments/stats` | GET | No | Apartment statistics by city |

### Billing & Saved Searches
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/billing/checkout` | POST | Required | Create Stripe Checkout Session for Pro upgrade |
| `/api/billing/portal` | POST | Required | Create Stripe Customer Portal session |
| `/api/saved-searches` | GET | Required | List user's saved searches |
| `/api/saved-searches` | POST | Required (Pro) | Create a saved search |
| `/api/saved-searches/{id}` | DELETE | Required | Delete a saved search |

### Webhooks
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/webhooks/supabase` | POST | Handle Supabase events |
| `/api/webhooks/stripe` | POST | Handle Stripe events (checkout.completed, subscription.updated/deleted, payment_failed) |

### Admin (Data Collection)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/admin/data-collection/jobs` | POST | Trigger manual scrape |
| `/api/admin/data-collection/jobs` | GET | List scrape jobs |
| `/api/admin/data-collection/health` | GET | Data collection health check |

## Claude AI Integration

The Claude integration has two modes, both in `claude_service.py`:

### Search Scoring (`score_apartments()`)
- **System prompt**: Defines Claude as apartment matching expert
- **User prompt**: Contains search criteria + apartment data as JSON
- Returns JSON array:
```json
[{
  "apartment_id": "bryn-001",
  "match_score": 85,
  "reasoning": "Under budget with all requested amenities...",
  "highlights": ["Under budget", "Pet-friendly", "Near train"]
}]
```

### Comparison Analysis (`compare_apartments_with_analysis()`)
- Deep head-to-head analysis of 2-3 apartments
- Scores across categories: Value, Space & Layout, Amenities, + 1-3 custom
- Picks a winner with reasoning
- Uses `asyncio.to_thread()` to avoid blocking the async event loop
- Returns structured JSON:
```json
{
  "winner": {"apartment_id": "uuid", "reason": "Best overall value..."},
  "categories": ["Value", "Space & Layout", "Amenities", "Location"],
  "apartment_scores": [{
    "apartment_id": "uuid",
    "overall_score": 82,
    "reasoning": "Strong choice for budget-conscious renters...",
    "highlights": ["Lowest rent", "Good amenities"],
    "category_scores": {
      "Value": {"score": 90, "note": "Best price per sqft"},
      "Amenities": {"score": 75, "note": "Standard amenities"}
    }
  }]
}
```

## Monetization & Tier System

### Tier Model (Renter Freemium)
| Feature | Free | Pro ($12/mo) |
|---------|------|-------------|
| Search | 3/day, no AI scoring | Unlimited + Claude AI match scores |
| Compare | Basic table only | Claude head-to-head analysis |
| Favorites | 5 max | Unlimited |
| Saved Searches | None | Unlimited + daily email alerts |
| Rate Limit | 10 req/min | 60 req/min |

### Backend Auth & Tier Flow
- `app/auth.py` decodes Supabase JWTs (HS256, audience "authenticated")
- `get_current_user` (mandatory) and `get_optional_user` (returns None) FastAPI dependencies
- `TierService.get_user_tier()` queries `profiles.user_tier` from Supabase
- `TierService.check_search_limit()` uses Redis daily counter (`search_count:{user_id}:{date}`, 48h TTL)
- Fail-open: if Redis or Supabase is down, defaults to allowing requests

### Stripe Integration
- Checkout: `POST /api/billing/checkout` creates Stripe Checkout Session
- Portal: `POST /api/billing/portal` creates Stripe Customer Portal (manage subscription)
- Webhooks handle 4 events:
  - `checkout.session.completed` → set tier to "pro", store stripe_customer_id
  - `customer.subscription.updated` → update subscription_status and current_period_end
  - `customer.subscription.deleted` → revert tier to "free"
  - `invoice.payment_failed` → set subscription_status to "past_due"

### Rate Limiting
- Redis-based sliding window counter per minute
- Authenticated: 60 req/min, Anonymous: 10 req/min
- Expensive paths (`/api/search`, `/api/apartments/compare`): 10 req/min
- Returns HTTP 429 with `{"detail": "Rate limit exceeded. Please slow down."}`
- Fail-open: if Redis unavailable, requests pass through
- Disabled during tests via `TESTING` env var

### Analytics
- `AnalyticsService.log_event()` - fire-and-forget to `analytics_events` table
- Events logged: search (with city, tier, result count), compare (with tier, apartment count)
- Never raises exceptions (catches and logs errors)

### Email Alerts (Resend)
- Celery beat task `send_daily_alerts` runs daily at 1 PM UTC (8 AM ET)
- Finds Pro users with active saved searches (`is_active=True`, `notify_new_matches=True`)
- Filters to apartments added since `last_alerted_at`
- Sends plain text email via Resend with up to 10 listings
- Updates `last_alerted_at` after sending

## User Features

### Favorites
- Click heart icon on any apartment card
- Requires sign-in (prompts Google OAuth if not signed in)
- Optimistic UI updates (instant feedback)
- Free tier: limited to 5 favorites (shows alert when at limit)
- Pro tier: unlimited favorites
- Synced to Supabase with realtime subscriptions
- View all favorites at `/favorites`

### Comparison (Enhanced)
- Click "Compare" button on apartment cards (up to 3)
- Floating ComparisonBar shows selected apartments
- Side-by-side view at `/compare` with auth gate
- Search context (city, budget, preferences) auto-passed from search page
- Free tier: sees comparison table but Score button shows UpgradePrompt
- Pro tier: click "Score" for Claude AI head-to-head analysis (preferences optional)
- Winner summary card with green border and star icon
- Category breakdown grid (Value, Space, Amenities, etc.)
- Comparison table with Overall Score row, rent/beds/baths/amenities
- Zustand store with `persist` middleware keeps state across page navigation

### Saved Searches (Pro only)
- Create saved search criteria via `/api/saved-searches`
- Daily email alerts for new matching apartments (via Resend)
- Manage alerts in `/settings` page

### Authentication
- Google OAuth via Supabase
- Session persisted in cookies
- AuthContext provides user state, tier, isPro, refreshProfile to all components
- Auth gates on search page (`/`) and compare page (`/compare`)
- E2E test bypass via `localStorage.__test_auth_user` (non-production only)

### Billing & Account Management
- `/pricing` page: Free vs Pro side-by-side with Stripe checkout
- `/settings` page: profile info, subscription management (via Stripe Portal), data export, account deletion
- Settings page handles `?upgrade=success` query param with success banner and profile refresh

## Development Notes

- Budget filtering is strict (no flexibility) - `apartment_service.py`
- Bedrooms filter is exact match, bathrooms is "at least"
- City matching is case-insensitive partial match on address
- Image domains configured in `next.config.ts` (images.unsplash.com)
- CORS configured in `main.py` for localhost:3000
- Backend uses model `claude-sonnet-4-5-20250929`
- Favorites use optimistic updates with rollback on error, 5 limit enforced on frontend for free tier
- Auth has 5-second timeout to prevent infinite loading
- Don't use `--reload` flag with uvicorn (causes venv file watching issues)
- Search endpoint: Pro gets Claude scoring, free/anonymous get filtered results only; response includes `tier` and `searches_remaining`
- Compare endpoint: Pro gets Claude analysis, free/anonymous get basic comparison table; Claude called only for Pro with 2+ apartments
- All apartment endpoints (get, batch, compare) support both DB and JSON modes via `is_database_enabled()`
- E2E tests mock auth via `localStorage.__test_auth_user` + Supabase API route interception
- Zustand comparison store uses `persist` middleware with `createJSONStorage(() => localStorage)`
- Backend comparison uses `asyncio.to_thread()` for synchronous Claude API calls
- Rate limiting middleware checks `TESTING` env var to skip during tests; conftest.py sets `TESTING=1`
- Stripe webhooks verify signature via `stripe.Webhook.construct_event()`; use `STRIPE_WEBHOOK_SECRET`
- TierService uses Redis for daily search counters (fail-open) and Supabase service role for profile queries
- AnalyticsService is fire-and-forget; never blocks or raises on failure
- Frontend `AuthContext` exposes `tier`, `isPro`, `refreshProfile()` for tier-aware rendering
- `UpgradePrompt` component has `inline` (horizontal bar) and block (centered card) display modes

## Backend Testing

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
```

77 tests across 9 test files:
- `test_auth.py` (6) - JWT verification, get_current_user, get_optional_user
- `test_tier_service.py` (5) - Tier checking, Redis metering, fail-open
- `test_billing.py` (13) - Stripe checkout, portal, webhooks, customer lookup
- `test_search_gating.py` (9) - Anonymous/free/pro search behavior, daily limits
- `test_compare_gating.py` (9) - Anonymous/free/pro compare behavior, Claude gating
- `test_saved_searches.py` (8) - CRUD, auth required, Pro-only creation
- `test_rate_limit.py` (13) - Rate limits, expensive paths, Redis fail-open
- `test_alert_tasks.py` (5) - Daily email alerts, filtering, error handling
- `test_webhooks.py` (2) - Supabase webhook auth

Tests use `TESTING=1` env var (set in conftest.py) to disable rate limiting middleware.

## E2E Testing

```bash
cd frontend
npx playwright test            # Run all 25 tests
npx playwright test --ui       # Run with Playwright UI
npx playwright test --headed   # Run in headed browser mode
```

Tests mock auth via `mockAuth()` helper that injects a test user into `localStorage.__test_auth_user` and intercepts Supabase API calls. The `AuthContext` checks for this key in non-production environments before initializing the real Supabase auth flow.
