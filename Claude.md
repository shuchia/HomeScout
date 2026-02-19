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
│  AuthContext (Google OAuth) ←→ Supabase Auth                            │
│  useFavorites hook ←→ Supabase Database (favorites table)               │
│  useComparisonStore (Zustand) → Compare Page                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Backend (FastAPI)                              │
├─────────────────────────────────────────────────────────────────────────┤
│  /api/search          → Filter + Claude AI scoring                      │
│  /api/apartments/batch → Get multiple apartments by ID                  │
│  /api/apartments/compare → Side-by-side comparison                      │
│  /api/webhooks/supabase → Handle Supabase events                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Data Sources                                   │
├─────────────────────────────────────────────────────────────────────────┤
│  apartments.json (mock data) │ Supabase (users, favorites, searches)    │
│  Claude AI (scoring)         │ Apify/ScrapingBee (future scraping)      │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Flow
1. User submits search criteria via `SearchForm.tsx`
2. `lib/api.ts` sends POST to `/api/search`
3. `apartment_service.py` filters `apartments.json` by basic criteria
4. `claude_service.py` calls Claude API with filtered apartments + user preferences
5. Claude returns JSON with `match_score` (0-100), `reasoning`, `highlights`
6. Backend merges scores with apartment data, sorts by match_score, returns top 10
7. Frontend displays results in `ApartmentCard` components with image carousels
8. Users can favorite apartments (saved to Supabase) or add to comparison

### Type Synchronization
Frontend TypeScript interfaces (`types/apartment.ts`) must match backend Pydantic models (`schemas.py`). Changes to data models require updates in both places.

## Key Files

### Frontend - Core
- `app/page.tsx` - Main page with search form + results grid
- `app/favorites/page.tsx` - User's saved favorites
- `app/compare/page.tsx` - Side-by-side apartment comparison
- `app/auth/callback/route.ts` - OAuth callback handler

### Frontend - Components
- `components/SearchForm.tsx` - Search form with all inputs
- `components/ApartmentCard.tsx` - Apartment display with match score, favorite button, compare button
- `components/ImageCarousel.tsx` - Embla carousel for photos
- `components/Header.tsx` - Navigation with auth state
- `components/AuthButton.tsx` - Sign in button
- `components/UserMenu.tsx` - User dropdown menu
- `components/FavoriteButton.tsx` - Heart button to save favorites
- `components/CompareButton.tsx` - Add to comparison button
- `components/ComparisonBar.tsx` - Floating bar showing comparison selection

### Frontend - State & Hooks
- `contexts/AuthContext.tsx` - Google OAuth via Supabase
- `hooks/useFavorites.ts` - Favorites CRUD with optimistic updates
- `stores/comparisonStore.ts` - Zustand store for comparison state
- `lib/supabase.ts` - Supabase client and type definitions
- `lib/api.ts` - API client (searchApartments, getApartmentsBatch, compareApartments)
- `types/apartment.ts` - TypeScript interfaces

### Backend - API
- `app/main.py` - FastAPI app with main endpoints
- `app/routers/apartments.py` - Apartment detail, batch, compare endpoints
- `app/routers/webhooks.py` - Supabase webhook handlers
- `app/routers/data_collection.py` - Admin endpoints for scraping jobs
- `app/schemas.py` - Pydantic models

### Backend - Services
- `app/services/claude_service.py` - Claude AI integration
- `app/services/apartment_service.py` - Filter logic, ranking
- `app/data/apartments.json` - Mock dataset (12 Bryn Mawr apartments)

### Backend - Data Collection (Infrastructure)
- `app/celery_app.py` - Celery configuration and beat schedule
- `app/database.py` - Async SQLAlchemy setup
- `app/tasks/scrape_tasks.py` - Scraping task definitions
- `app/services/scrapers/apify_service.py` - Apify integration
- `app/services/normalization/normalizer.py` - Data normalization
- `app/services/deduplication/deduplicator.py` - Duplicate detection

### Database
- `supabase/migrations/001_initial_schema.sql` - Supabase schema (profiles, favorites, saved_searches, notifications)

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
Run `supabase/migrations/001_initial_schema.sql` in Supabase SQL Editor:

**Tables:**
- `profiles` - User profiles (auto-created on signup)
- `favorites` - Saved apartments per user
- `saved_searches` - Saved search criteria with notifications
- `notifications` - User notifications

**Row Level Security (RLS):**
- Users can only access their own data
- Policies enforce user isolation

### Authentication
1. Enable Google OAuth in Supabase Dashboard → Authentication → Providers
2. Add Google Client ID and Secret from Google Cloud Console
3. Set redirect URL: `http://localhost:3000/auth/callback`

## API Endpoints

### Search & Apartments
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/search` | POST | Search with Claude AI scoring |
| `/api/apartments/{id}` | GET | Get single apartment |
| `/api/apartments/batch` | POST | Get multiple apartments by IDs |
| `/api/apartments/compare` | POST | Compare 2-3 apartments |
| `/api/apartments/count` | GET | Total apartment count |

### Webhooks
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/webhooks/supabase` | POST | Handle Supabase events |

## Claude AI Integration

The scoring prompts are in `claude_service.py`:
- **System prompt**: Defines Claude as apartment matching expert
- **User prompt**: Contains search criteria + apartment data as JSON

Claude returns JSON array:
```json
[{
  "apartment_id": "bryn-001",
  "match_score": 85,
  "reasoning": "Under budget with all requested amenities...",
  "highlights": ["Under budget", "Pet-friendly", "Near train"]
}]
```

## User Features

### Favorites
- Click heart icon on any apartment card
- Requires sign-in (prompts Google OAuth if not signed in)
- Optimistic UI updates (instant feedback)
- Synced to Supabase with realtime subscriptions
- View all favorites at `/favorites`

### Comparison
- Click "Compare" button on apartment cards (up to 3)
- Floating ComparisonBar shows selected apartments
- Side-by-side view at `/compare`
- Zustand store persists selection during session

### Authentication
- Google OAuth via Supabase
- Session persisted in cookies
- AuthContext provides user state to all components
- Protected routes redirect to sign-in

## Development Notes

- Budget filtering is strict (no flexibility) - `apartment_service.py`
- Bedrooms filter is exact match, bathrooms is "at least"
- City matching is case-insensitive partial match on address
- Image domains configured in `next.config.ts` (images.unsplash.com)
- CORS configured in `main.py` for localhost:3000
- Backend uses model `claude-sonnet-4-5-20250929`
- Favorites use optimistic updates with rollback on error
- Auth has 5-second timeout to prevent infinite loading
