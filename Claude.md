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
+-------------------------------------------------------------------------+
|                              Frontend (Next.js)                          |
+-------------------------------------------------------------------------+
|  SearchForm -> API Client -> Results Grid (ApartmentCard)                |
|  AuthContext (Google OAuth + tier) <-> Supabase Auth                     |
|  useFavorites hook <-> Supabase Database (favorites table)               |
|  useComparison (Zustand+persist) -> Compare Page + Claude Analysis       |
|  Tour Pipeline: /tours dashboard + /tours/[id] detail (capture/email)    |
|  Onboarding walkthrough (Joyride) + Invite code redemption               |
|  Auth gates on Search + Compare pages (require sign-in)                  |
|  Tier gating: free (3 searches/day, 5 favorites) vs pro (unlimited)     |
|  True Cost Calculator: Est. True Cost on cards, Pro gets full breakdown  |
|  Landing page (/landing) + Feedback widget + Bottom nav (mobile)         |
|  /pricing, /settings pages for billing + account management              |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                           Backend (FastAPI)                               |
+-------------------------------------------------------------------------+
|  /api/search              -> Filter + Claude AI scoring (pro only)       |
|  /api/search/score-batch  -> Lazy AI scoring for paginated results (pro) |
|  /api/apartments/*        -> CRUD, batch, compare (DB or JSON)           |
|  /api/tours/*             -> Tour pipeline CRUD + AI features            |
|  /api/billing/*           -> Stripe checkout, portal, webhooks           |
|  /api/saved-searches      -> CRUD saved searches (pro only)              |
|  /api/invite/*            -> Invite code redemption + status             |
|  /api/feedback            -> Beta feedback collection                    |
|  /api/waitlist            -> No-auth waitlist signup                     |
|  /api/webhooks/*          -> Stripe + Supabase event handling            |
|  /api/admin/*             -> Data collection + invite code generation    |
|  /metrics                 -> Prometheus metrics endpoint                 |
|  Rate limiting middleware -> Redis-based (120/min auth, 30/min anon)     |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                           Data Sources & Infrastructure                   |
+-------------------------------------------------------------------------+
|  PostgreSQL (scraped data) | apartments.json (fallback/mock)             |
|  MarketConfig (tiered)     | Claude AI (scoring, comparison, touring)    |
|  Apify (apartments.com)   | Redis (Celery + rate limits + metering)     |
|  Stripe (payments)        | Resend (email alerts)                       |
|  AWS S3 (tour photos)     | OpenAI Whisper (voice transcription)        |
|  Prometheus (monitoring)  | Slack (alert notifications)                 |
+-------------------------------------------------------------------------+
```

### Key Flow: Search
1. User signs in via Google OAuth (auth gate on search page)
2. User submits search criteria via `SearchForm.tsx`
3. `lib/api.ts` sends POST to `/api/search` with Supabase JWT
4. Backend verifies JWT via `auth.py`, determines tier via `TierService`
5. **Free tier**: checks daily search limit (3/day via Redis counter), returns filtered results with heuristic scoring (no AI)
6. **Pro tier**: `claude_service.py` calls Claude API, returns scored results with `match_score`, `reasoning`, `highlights`
7. Frontend displays results; free users see "Pro" badge instead of match scores
8. Response includes `tier` and `searches_remaining` for UI state
9. Users can favorite apartments (saved to Supabase) or add to comparison
10. Search context (city, budget, etc.) is saved to Zustand store for the compare page
11. Each apartment includes precomputed `true_cost_monthly` (rent + utilities + fees). Free users see the headline number; Pro users get full `cost_breakdown` with source tracking.

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

### Key Flow: Touring Pipeline
1. User clicks "Start Tour" on an apartment card (TourPrompt component)
2. Tour created via `POST /api/tours` with apartment_id and initial stage "interested"
3. `/tours` dashboard shows all tours grouped by stage (TourCard components)
4. Tour detail page (`/tours/[id]`) allows notes, photos, voice capture, star ratings, tags
5. AI features (Pro): inquiry email generation, day planner, note enhancement, decision brief
6. Voice notes captured via VoiceCapture component, transcribed async by Whisper
7. Photos uploaded to S3 via photo_service, managed per tour
8. Stages: interested -> outreach_sent -> scheduled -> toured -> deciding (linear but skippable)

### Dual Data Mode
The backend supports two data modes, controlled by `USE_DATABASE` env var:
- **JSON Mode** (default): Uses static `app/data/apartments.json`
- **Database Mode**: Uses PostgreSQL with scraped data from Apify

All apartment endpoints (`get`, `batch`, `compare`, `list`) check `is_database_enabled()` and query the appropriate source.

### Type Synchronization
Frontend TypeScript interfaces (`types/apartment.ts`, `types/tour.ts`) must match backend Pydantic models (`schemas.py`). Changes to data models require updates in both places.

## Continuous Scraping Pipeline

The backend uses a market-driven dispatcher pattern for continuous apartment scraping:

### Beat Schedule (5 orchestrator tasks)
| Task | Schedule | Purpose |
|------|----------|---------|
| `dispatch_scrapes` | Every hour at :00 | Check which markets are due, spawn scrape tasks |
| `decay_and_verify` | Every hour at :30 | Update confidence scores, dispatch verification |
| `cleanup_maintenance` | Daily at 3 AM | Deactivate dead listings, reset circuit breakers |
| `send_daily_alerts` | Daily at 1 PM UTC (8 AM ET) | Email Pro users with new listings matching saved searches |
| `check_tour_reminders` | Every 10 minutes | Check and send tour reminder notifications |

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

### Frontend - Core Pages
- `app/page.tsx` - Main page with auth gate, search form + results grid, free search counter
- `app/favorites/page.tsx` - User's saved favorites (requires auth)
- `app/compare/page.tsx` - Enhanced comparison with Claude AI analysis, winner summary, category scores (Score gated to Pro)
- `app/pricing/page.tsx` - Free vs Pro comparison with Stripe checkout button
- `app/settings/page.tsx` - Profile, subscription management, data export, account deletion
- `app/auth/callback/page.tsx` - OAuth callback handler
- `app/landing/page.tsx` - Public landing page (with its own layout)
- `app/tours/page.tsx` - Tour pipeline dashboard, grouped by stage
- `app/tours/[id]/page.tsx` - Tour detail: notes, photos, voice, AI features

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
- `components/CostBreakdownPanel.tsx` - Pro-only detailed cost breakdown with source indicators (scraped vs estimated)
- `components/NearLocationInput.tsx` - Location input for proximity search
- `components/RadiusSlider.tsx` - Radius filter for proximity search (Pro)
- `components/TourCard.tsx` - Tour summary card for dashboard
- `components/TourPrompt.tsx` - Start tour CTA on apartment cards
- `components/TourScheduler.tsx` - Schedule tour dates
- `components/VoiceCapture.tsx` - Voice note recording component
- `components/DecisionBrief.tsx` - AI-generated decision summary (Pro)
- `components/DayPlanner.tsx` - AI tour day planning (Pro)
- `components/StarRating.tsx` - Star rating input for tours
- `components/TagPicker.tsx` - Tag management for tours
- `components/BottomNav.tsx` - Mobile bottom navigation bar
- `components/FeedbackWidget.tsx` - Beta feedback submission widget
- `components/InviteCodeBanner.tsx` - Invite code entry banner
- `components/OnboardingWalkthrough.tsx` - Guided onboarding (Joyride)

### Frontend - State & Hooks
- `contexts/AuthContext.tsx` - Google OAuth via Supabase, tier/isPro/refreshProfile (E2E test bypass in non-production)
- `hooks/useFavorites.ts` - Favorites CRUD with optimistic updates, 5 favorite limit for free tier (`atLimit`)
- `hooks/useComparison.ts` - Zustand store with persist for comparison state + search context
- `lib/supabase.ts` - Supabase client and type definitions (Profile includes user_tier, subscription_status)
- `lib/api.ts` - API client with auth headers (searchApartments, getApartmentsBatch, compareApartments, tours API)
- `lib/auth-store.ts` - Auth state persistence utilities
- `lib/geocode.ts` - Geocoding utilities for proximity search (Nominatim)
- `types/apartment.ts` - TypeScript interfaces (match_score nullable, SearchResponse includes tier/searches_remaining)
- `types/tour.ts` - Tour pipeline TypeScript interfaces

### Backend - API
- `app/main.py` - FastAPI app with tier-gated search endpoint, score-batch endpoint, rate limiting, Prometheus metrics
- `app/auth.py` - Supabase JWT verification (get_current_user, get_optional_user)
- `app/routers/apartments.py` - Apartment detail, batch, list, compare endpoints (compare gated by tier)
- `app/routers/billing.py` - Stripe checkout, portal, and webhook endpoints
- `app/routers/saved_searches.py` - Saved search CRUD (Pro only)
- `app/routers/tours.py` - Full tour pipeline CRUD: tours, notes, photos, tags, AI features (inquiry email, day plan, decision brief, voice notes, note enhancement)
- `app/routers/webhooks.py` - Supabase webhook handlers
- `app/routers/data_collection.py` - Admin endpoints for scraping jobs, markets, sources, metrics
- `app/routers/feedback.py` - Beta feedback submission (auth required)
- `app/routers/invite.py` - Invite code redemption + status, admin code generation
- `app/routers/waitlist.py` - Public waitlist signup, admin listing
- `app/schemas.py` - Pydantic models
- `app/middleware/rate_limit.py` - Redis-based rate limiting (120/min auth, 30/min anon, 20/min expensive)

### Backend - Services
- `app/services/claude_service.py` - Claude AI integration (search scoring, comparison analysis, inquiry emails, day plans, note enhancement, decision briefs)
- `app/services/apartment_service.py` - Filter logic, ranking, Claude semaphore
- `app/services/scoring_service.py` - Heuristic scoring for free tier (non-AI fallback)
- `app/services/tier_service.py` - Tier checking (Supabase profiles), Redis daily search metering, tier updates
- `app/services/analytics_service.py` - Fire-and-forget event logging to Supabase analytics_events table
- `app/services/cost_estimator.py` - True cost estimation from scraped fees + regional averages
- `app/services/distance.py` - Haversine distance calculation for proximity search
- `app/services/scrapers/apify_service.py` - Apify integration for apartments.com scraping
- `app/services/scrapers/base_scraper.py` - Base scraper interface
- `app/services/scrapers/scrapingbee_service.py` - ScrapingBee integration
- `app/services/normalization/normalizer.py` - Data normalization
- `app/services/normalization/address_standardizer.py` - Address standardization
- `app/services/deduplication/deduplicator.py` - Duplicate detection
- `app/services/storage/photo_service.py` - Tour photo management
- `app/services/storage/s3_service.py` - AWS S3 integration for photo storage
- `app/services/transcription/whisper_service.py` - OpenAI Whisper voice transcription
- `app/services/monitoring/alerts.py` - Slack alert notifications
- `app/services/monitoring/metrics.py` - Prometheus metrics collection
- `app/data/apartments.json` - Fallback dataset (12 Bryn Mawr apartments, used in JSON mode)
- `app/data/cost_estimates.json` - Regional utility cost lookup tables by zip prefix + bedroom count

### Backend - Tasks
- `app/celery_app.py` - Celery configuration and beat schedule (5 tasks)
- `app/tasks/dispatcher.py` - Market-driven scrape dispatcher
- `app/tasks/scrape_tasks.py` - Scraping task definitions
- `app/tasks/maintenance_tasks.py` - Listing cleanup, circuit breaker reset
- `app/tasks/alert_tasks.py` - Daily email alerts for Pro users with saved searches (via Resend)
- `app/tasks/true_cost_tasks.py` - Celery task for recomputing true cost estimates
- `app/tasks/tour_reminder_tasks.py` - Tour reminder notifications
- `app/tasks/transcription_tasks.py` - Async voice note transcription

### Backend - Data Layer
- `app/database.py` - Async SQLAlchemy setup
- `app/logging_config.py` - Logging configuration
- `app/models.py` - SQLAlchemy models
- `app/models/apartment.py` - Apartment model
- `app/models/market_config.py` - Market configuration with tier system (hot/standard/cool)
- `app/models/data_source.py` - Data source tracking
- `app/models/scrape_job.py` - Scrape job state tracking

### Database Migrations
- `supabase/migrations/001_initial_schema.sql` - Supabase schema (profiles, favorites, saved_searches, notifications)
- `supabase/migrations/002_add_tier_columns.sql` - Add user_tier, stripe_customer_id, subscription_status to profiles
- `supabase/migrations/003_add_analytics_events.sql` - Analytics events table
- `supabase/migrations/004_update_saved_searches.sql` - Add last_alerted_at, is_active to saved_searches
- `supabase/migrations/005_tour_pipeline.sql` - Tour pipeline tables (tours, notes, photos, tags)
- `supabase/migrations/006_beta_launch.sql` - Beta launch tables (invite codes, feedback)
- `supabase/migrations/007_waitlist.sql` - Waitlist signups table
- `supabase/migrations/008_tour_contact_info.sql` - Tour contact info fields

### Infrastructure
- `infra/main.tf` - Root Terraform configuration (AWS)
- `infra/environments/dev.tfvars`, `qa.tfvars`, `prod.tfvars` - Per-environment variables
- `infra/modules/` - Terraform modules: networking, alb, ecr, ecs, elasticache, rds, monitoring
- `infra/bootstrap/` - Terraform state backend setup
- `.github/workflows/ci.yml` - CI pipeline (lint, test)
- `.github/workflows/deploy-backend.yml` - Backend deployment pipeline
- `scripts/deploy.sh` - Deployment script

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

# Optional - Tour features
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
S3_BUCKET_NAME=homescout-tour-photos
OPENAI_API_KEY=your-openai-key

# CORS
FRONTEND_URL=http://localhost:3000
```

## Supabase Setup

### Database Schema
Run all migrations (001-008) in order in Supabase SQL Editor:

**Tables:**
- `profiles` - User profiles with tier info (user_tier, stripe_customer_id, subscription_status, current_period_end)
- `favorites` - Saved apartments per user
- `saved_searches` - Saved search criteria with alert tracking (last_alerted_at, is_active)
- `notifications` - User notifications
- `analytics_events` - Event logging (search, compare, upgrade events)
- `tours` - Tour pipeline entries (apartment_id, stage, star_rating, contact info)
- `tour_notes` - Text and voice notes per tour
- `tour_photos` - Photo metadata per tour (S3 keys)
- `tour_tags` - User-defined tags per tour
- `invite_codes` - Beta invite codes with usage tracking
- `feedback` - Beta feedback submissions
- `waitlist` - Waitlist signups (email, name, referral_source)

**Row Level Security (RLS):**
- Users can only access their own data
- Policies enforce user isolation
- Service role policies for backend tier updates and alert tracking

### Authentication
1. Enable Google OAuth in Supabase Dashboard -> Authentication -> Providers
2. Add Google Client ID and Secret from Google Cloud Console
3. Set redirect URL: `http://localhost:3000/auth/callback`

## API Endpoints

### Search & Apartments
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/search` | POST | Optional | Search; Pro gets Claude AI scoring, free gets heuristic scoring (3/day limit) |
| `/api/search/score-batch` | POST | Required (Pro) | Lazy AI scoring for paginated results (max 10 apartments) |
| `/api/apartments/{id}` | GET | No | Get single apartment (DB or JSON) |
| `/api/apartments/batch` | POST | No | Get multiple apartments by IDs (DB or JSON) |
| `/api/apartments/compare` | POST | Optional | Compare 2-3 apartments; Pro gets Claude analysis, free gets basic comparison |
| `/api/apartments/count` | GET | No | Total apartment count |
| `/api/apartments/list` | GET | No | List apartments with filters (city, rent, bedrooms) |
| `/api/apartments/stats` | GET | No | Apartment statistics by city |

### Tours (Auth Required)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tours` | POST | Create tour for an apartment |
| `/api/tours` | GET | List user's tours |
| `/api/tours/{id}` | GET | Get tour details |
| `/api/tours/{id}` | PATCH | Update tour (stage, rating, contact info) |
| `/api/tours/{id}` | DELETE | Delete tour |
| `/api/tours/{id}/notes` | POST/GET | Create/list text notes |
| `/api/tours/{id}/notes/voice` | POST | Upload voice note (async transcription) |
| `/api/tours/{id}/notes/{nid}` | DELETE | Delete note |
| `/api/tours/{id}/photos` | POST/GET | Upload/list photos |
| `/api/tours/{id}/photos/{pid}` | PATCH/DELETE | Update caption/delete photo |
| `/api/tours/{id}/tags` | POST | Add tag |
| `/api/tours/{id}/tags/{tid}` | PATCH/DELETE | Update/delete tag |
| `/api/tours/tags/suggestions` | GET | Get tag suggestions |
| `/api/tours/{id}/inquiry-email` | POST | AI-generated inquiry email (Pro) |
| `/api/tours/{id}/enhance-note` | POST | AI note enhancement (Pro) |
| `/api/tours/day-plan` | POST | AI tour day planner (Pro) |
| `/api/tours/decision-brief` | POST | AI decision brief (Pro) |

### Billing & Saved Searches
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/billing/checkout` | POST | Required | Create Stripe Checkout Session for Pro upgrade |
| `/api/billing/portal` | POST | Required | Create Stripe Customer Portal session |
| `/api/saved-searches` | GET | Required | List user's saved searches |
| `/api/saved-searches` | POST | Required (Pro) | Create a saved search |
| `/api/saved-searches/{id}` | DELETE | Required | Delete a saved search |

### Invite & Waitlist
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/invite/redeem` | POST | Required | Redeem invite code (90-day Pro trial) |
| `/api/invite/status` | GET | Required | Check invite status |
| `/api/admin/invite-codes` | POST | Admin key | Generate invite codes |
| `/api/waitlist` | POST | No | Join waitlist |
| `/api/admin/waitlist` | GET | Network-level | List waitlist signups |
| `/api/feedback` | POST | Required | Submit beta feedback |

### Webhooks
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhooks/supabase/check-matches` | POST | Handle Supabase events |
| `/api/webhooks/stripe` | POST | Handle Stripe events (checkout.completed, subscription.updated/deleted, payment_failed) |

### Admin (Data Collection)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/admin/data-collection/jobs` | POST/GET | Trigger/list scrape jobs |
| `/api/admin/data-collection/jobs/{id}` | GET | Job status |
| `/api/admin/data-collection/sources` | GET | List data sources |
| `/api/admin/data-collection/sources/{id}` | PUT | Update data source |
| `/api/admin/data-collection/markets` | GET/POST | List/create markets |
| `/api/admin/data-collection/markets/{id}` | PUT | Update market config |
| `/api/admin/data-collection/markets/{id}/scrape` | POST | Trigger immediate scrape |
| `/api/admin/data-collection/metrics` | GET | Scraping metrics |
| `/api/admin/data-collection/health` | GET | Data collection health check |

### Monitoring
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/metrics` | GET | Prometheus metrics |

## Claude AI Integration

The Claude integration uses two models, both configured in `claude_service.py`:
- **Haiku** (`claude-haiku-4-5-20251001`): Fast, structured output - search scoring, inquiry emails, day plans, note enhancement
- **Sonnet** (`claude-sonnet-4-5-20250929`): Deep reasoning - comparison analysis, decision briefs

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

### Tour AI Features
- **Inquiry email**: Generates professional apartment inquiry email from tour data
- **Day planner**: Plans efficient multi-tour day with travel routing
- **Note enhancement**: Expands brief notes into detailed observations
- **Decision brief**: Comprehensive comparison of toured apartments with recommendation

## Monetization & Tier System

### Tier Model (Renter Freemium)
| Feature | Free | Pro ($12/mo or invite code) |
|---------|------|-------------|
| Search | 3/day, heuristic scoring only | Unlimited + Claude AI match scores |
| Compare | Basic table only | Claude head-to-head analysis |
| Favorites | 5 max | Unlimited |
| Saved Searches | None | Unlimited + daily email alerts |
| True Cost | Headline number only | Full breakdown with sources |
| Tours | Basic CRUD | AI inquiry emails, day planner, decision briefs, note enhancement |
| Rate Limit | 30 req/min | 120 req/min |

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
  - `checkout.session.completed` -> set tier to "pro", store stripe_customer_id
  - `customer.subscription.updated` -> update subscription_status and current_period_end
  - `customer.subscription.deleted` -> revert tier to "free"
  - `invoice.payment_failed` -> set subscription_status to "past_due"

### Invite Code System
- Admin generates codes via `POST /api/admin/invite-codes` (requires X-Admin-Key header)
- Users redeem codes via `POST /api/invite/redeem` -> sets tier to "pro" for 90 days
- Codes have configurable max_uses (1-100), atomic redemption prevents race conditions
- InviteCodeBanner component on frontend for code entry

### Rate Limiting
- Redis-based sliding window counter per minute
- Authenticated: 120 req/min, Anonymous: 30 req/min
- Expensive paths (`/api/search`, `/api/apartments/compare`): 20 req/min
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

### Touring Pipeline
- Tour lifecycle: interested -> outreach_sent -> scheduled -> toured -> deciding
- Stages are linear but skippable
- Notes (text + voice), photos, star ratings, tags per tour
- Pro AI features: inquiry email, day planner, note enhancement, decision brief
- Voice notes transcribed async via OpenAI Whisper + Celery
- Photos stored in S3, managed via photo_service
- Tour reminders checked every 10 minutes via Celery beat

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

### Beta Features
- Landing page at `/landing` with its own layout
- Invite code system (90-day Pro trial via InviteCodeBanner)
- Onboarding walkthrough (Joyride-based OnboardingWalkthrough component)
- Feedback widget for bug reports and suggestions
- Waitlist signup (no auth required)
- Mobile bottom navigation (BottomNav component)

## Development Notes

- Budget filtering is strict (no flexibility) - `apartment_service.py`
- Bedrooms filter is exact match, bathrooms is "at least"
- City matching is case-insensitive partial match on address
- Image domains configured in `next.config.ts` (images.unsplash.com)
- CORS configured in `main.py` for localhost:3000 + FRONTEND_URL
- Search scoring uses `claude-haiku-4-5-20251001` (fast, structured output)
- Comparison analysis and decision briefs use `claude-sonnet-4-5-20250929` (deep reasoning)
- Inquiry emails, day plans, and note enhancement use Haiku
- All calls use prompt caching (`cache_control: ephemeral`) for reduced latency and cost
- Favorites use optimistic updates with rollback on error, 5 limit enforced on frontend for free tier
- Auth has 5-second timeout to prevent infinite loading
- Don't use `--reload` flag with uvicorn (causes venv file watching issues)
- Search endpoint: Pro gets Claude scoring, free/anonymous get heuristic scoring only; response includes `tier` and `searches_remaining`
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
- True cost is precomputed at ingestion time; `_add_cost_breakdown()` in apartments router fills gaps for JSON mode
- Cost estimates use 3-digit zip prefix lookup with default fallback chain
- `cost_breakdown` field is null for free/anonymous users, populated for Pro
- Claude AI prompts include `true_cost_monthly` and `cost_details` for budget-aware scoring
- Large scoring batches (>12 apartments) are split into parallel Claude calls via `asyncio.gather()`
- 15-second timeout on all Claude calls with heuristic fallback for scoring
- Concurrent Claude calls limited to 5 via `_claude_semaphore` in `apartment_service.py`
- Token usage logged after every Claude call (`claude_usage` log prefix) for cost tracking
- Proximity search uses Haversine distance (`distance.py`) and Nominatim geocoding (`lib/geocode.ts`)
- Heuristic scoring (`scoring_service.py`) provides non-AI fallback for free tier searches

## Backend Testing

```bash
cd backend
ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
```

259 tests across 25 test files:
- `test_auth.py` (6) - JWT verification, get_current_user, get_optional_user
- `test_tier_service.py` (5) - Tier checking, Redis metering, fail-open
- `test_billing.py` (13) - Stripe checkout, portal, webhooks, customer lookup
- `test_search_gating.py` (10) - Anonymous/free/pro search behavior, daily limits
- `test_search_endpoint.py` (8) - Search endpoint integration tests
- `test_compare_gating.py` (11) - Anonymous/free/pro compare behavior, Claude gating
- `test_saved_searches.py` (8) - CRUD, auth required, Pro-only creation
- `test_rate_limit.py` (13) - Rate limits, expensive paths, Redis fail-open
- `test_alert_tasks.py` (5) - Daily email alerts, filtering, error handling
- `test_webhooks.py` (2) - Supabase webhook auth
- `test_tours.py` (39) - Full tour pipeline CRUD + AI features
- `test_apartments_router.py` (12) - Apartment list, detail, batch endpoints
- `test_scoring_service.py` (32) - Heuristic scoring logic
- `test_cost_estimator.py` (11) - True cost estimation
- `test_distance.py` (10) - Haversine distance calculations
- `test_proximity_search.py` (5) - Proximity search filtering
- `test_budget_filter.py` (3) - Budget filtering edge cases
- `test_apify_availability.py` (11) - Apify availability parsing
- `test_apify_type_safety.py` (31) - Apify response type safety
- `test_claude_cache.py` (4) - Claude prompt caching
- `test_claude_data.py` (4) - Claude data formatting
- `test_photo_service.py` (6) - Tour photo S3 integration
- `test_whisper_service.py` (4) - Whisper transcription
- `test_transcription_tasks.py` (3) - Async transcription tasks
- `test_tour_reminder_tasks.py` (3) - Tour reminder scheduling

Tests use `TESTING=1` env var (set in conftest.py) to disable rate limiting middleware.

## E2E Testing

```bash
cd frontend
npx playwright test            # Run all tests
npx playwright test --ui       # Run with Playwright UI
npx playwright test --headed   # Run in headed browser mode
```

Test files:
- `e2e/homescout.spec.ts` - Core app flows (search, compare, favorites, pricing)
- `e2e/tours.spec.ts` - Tour pipeline E2E tests

Tests mock auth via `mockAuth()` helper that injects a test user into `localStorage.__test_auth_user` and intercepts Supabase API calls. The `AuthContext` checks for this key in non-production environments before initializing the real Supabase auth flow.