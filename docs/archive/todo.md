# HomeScout Development Roadmap

---

# ✅ Milestone 1: Backend Foundation & AI Integration (COMPLETED)

**Goal:** Build FastAPI backend that returns ranked apartment recommendations using Claude Messages API

**Status:** ✅ COMPLETE - Server running on http://localhost:8000

---

## Setup & Project Structure

- [x] Initialize Python project structure
  - [x] Create `backend/` directory
  - [x] Set up Python virtual environment (`.venv`)
  - [x] Create `requirements.txt` with dependencies
  - [x] Install dependencies and upgrade Anthropic SDK to 0.73.0

- [x] Create project folder structure (app/, services/, data/)
- [x] Create `.env.example` file
- [x] Create `.env` file with API key
- [x] Create `.gitignore` with Python/FastAPI entries

## Mock Data Creation

- [x] Create `backend/app/data/apartments.json` with 60 mock apartments
  - [x] 4 cities: San Francisco, NYC, Austin, Seattle
  - [x] Price ranges ($1,400-$6,000/month)
  - [x] Bedrooms (studio, 1BR, 2BR, 3BR)
  - [x] Bathrooms (1-3)
  - [x] Property types (apartment, condo, townhouse, studio)
  - [x] Amenities (parking, laundry, gym, pool, pet-friendly, etc.)
  - [x] Available dates (November-December 2025)
  - [x] All required fields (id, address, rent, images, etc.)

## Pydantic Models

- [x] Create `backend/app/models.py` with all data models:
  - [x] `SearchRequest` model
  - [x] `Apartment` model
  - [x] `ApartmentScore` model
  - [x] `ApartmentWithScore` model
  - [x] `SearchResponse` model
  - [x] `HealthResponse` model

## Claude API Integration

- [x] Create `backend/app/services/claude_service.py`
  - [x] Import Anthropic SDK
  - [x] Create `ClaudeService` class
  - [x] Implement `score_apartments()` method
  - [x] Format prompt using template from `prompt.md`
  - [x] Call Claude Messages API (claude-sonnet-4-5-20250929)
  - [x] Parse JSON response with markdown handling
  - [x] Add error handling for API errors and invalid JSON
  - [x] Add logging for debugging

## Apartment Matching Service

- [x] Create `backend/app/services/apartment_service.py`
  - [x] Load apartments from JSON file
  - [x] Implement `search_apartments()` function with filters
  - [x] Filter by city, budget (+20% flexibility), beds, baths, type, date
  - [x] Implement `get_top_apartments()` function
  - [x] Call Claude service to score apartments
  - [x] Merge apartment data with scores
  - [x] Sort by match score (highest first)
  - [x] Return top 10 results

## FastAPI Endpoints

- [x] Create `backend/app/main.py`
  - [x] Initialize FastAPI app with metadata
  - [x] Add CORS middleware for localhost:3000
  - [x] Create `GET /` root endpoint
  - [x] Create `GET /health` endpoint
  - [x] Create `GET /api/apartments/count` endpoint
  - [x] Create `POST /api/search` endpoint with full validation
  - [x] Add error handling (400, 500 status codes)

## Testing & Validation

- [x] Manual testing with sample requests:
  - [x] Test San Francisco search (95% & 78% scores)
  - [x] Test Austin search (88% score)
  - [x] Test NYC search (90%, 88%, 85% scores)
  - [x] Verify match scores are reasonable and contextual
  - [x] Verify results are sorted by match score
  - [x] Verify Claude provides intelligent reasoning

- [x] API validation:
  - [x] Test CORS headers are present
  - [x] Test error responses
  - [x] Verify response time <2 seconds

- [x] Claude API validation:
  - [x] Verify API key loads from environment
  - [x] Verify JSON parsing handles markdown
  - [x] Successful API calls logged

## Documentation

- [x] Create `backend/README.md` with:
  - [x] Installation instructions
  - [x] Environment setup (.env configuration)
  - [x] How to run the server
  - [x] API endpoint documentation
  - [x] Example curl requests
  - [x] Troubleshooting guide

- [x] Add code comments and docstrings

## Run & Deploy (Local)

- [x] Test server startup on port 8000
- [x] Verify all endpoints working:
  - [x] `http://localhost:8000/health` ✅
  - [x] `http://localhost:8000/api/apartments/count` ✅
  - [x] `http://localhost:8000/api/search` ✅

## Success Criteria

✅ **Milestone 1 COMPLETE:**
- ✅ FastAPI server runs without errors
- ✅ `/api/search` endpoint returns ranked apartments
- ✅ Match scores are contextually relevant (78-95% range)
- ✅ Response time is under 2 seconds
- ✅ CORS is configured for frontend integration
- ✅ Code is documented and clean
- ✅ README has clear setup instructions
- ✅ Interactive API docs at http://localhost:8000/docs

**Actual Time:** ~2 hours (including debugging SDK version issue)

---

# ✅ Milestone 2: Frontend Search & Results (COMPLETED)

**Goal:** Build Next.js frontend with search form and apartment results display

**Status:** ✅ COMPLETE - Frontend running on http://localhost:3000

---

## Setup & Project Structure

- [x] Initialize Next.js project
  - [x] Create `frontend/` directory
  - [x] Run `npx create-next-app@latest` with TypeScript + Tailwind
  - [x] Configure for App Router (not Pages Router)
  - [x] Install additional dependencies:
    - [x] Using native `fetch` for API calls
    - [x] Image carousel library (embla-carousel-react)

- [x] Create project folder structure:
  ```
  frontend/
  ├── app/
  │   ├── page.tsx              # Home/search page with results
  │   └── layout.tsx
  ├── components/
  │   ├── SearchForm.tsx        # Search input form
  │   ├── ApartmentCard.tsx     # Individual apartment display
  │   └── ImageCarousel.tsx     # Image carousel component
  ├── lib/
  │   └── api.ts                # API client functions
  ├── types/
  │   └── apartment.ts          # TypeScript interfaces
  └── public/
  ```

- [x] Configure environment variables
  - [x] Create `.env.local` with `NEXT_PUBLIC_API_URL=http://localhost:8000`

---

## TypeScript Types

- [x] Create `frontend/types/apartment.ts` with interfaces:
  - [x] `SearchParams` interface (matches backend SearchRequest)
  - [x] `Apartment` interface (matches backend Apartment model)
  - [x] `ApartmentWithScore` interface
  - [x] `SearchResponse` interface

---

## API Client

- [x] Create `frontend/lib/api.ts`
  - [x] Create `searchApartments()` function
  - [x] Handle POST request to `/api/search`
  - [x] Handle errors and loading states
  - [x] Type all requests/responses with TypeScript
  - [x] Custom `ApiError` class for error handling

---

## Search Form Component

- [x] Create `frontend/components/SearchForm.tsx`
  - [x] City input (text field)
  - [x] Budget input (number input)
  - [x] Bedrooms select (dropdown: Studio, 1, 2, 3)
  - [x] Bathrooms select (dropdown: 1, 2, 3)
  - [x] Property type multi-select (Apartment, Condo, Townhouse, Studio)
  - [x] Move-in date picker (date input)
  - [x] Other preferences textarea
  - [x] Submit button
  - [x] Form validation
  - [x] Loading state during search
  - [x] Error handling

---

## Apartment Card Component

- [x] Create `frontend/components/ApartmentCard.tsx`
  - [x] Display apartment image carousel (3-8 images)
  - [x] Show match percentage badge (color-coded: green/blue/yellow)
  - [x] Display address and neighborhood
  - [x] Show rent/month (formatted with $)
  - [x] Display bedrooms, bathrooms, sqft
  - [x] Show amenities as tags/badges (max 5 + "more")
  - [x] Display reasoning text from Claude (italic)
  - [x] Show highlights as bullet points with checkmarks
  - [x] Responsive design (mobile + desktop)
  - [x] Hover effects and transitions

---

## Image Carousel Component

- [x] Create `frontend/components/ImageCarousel.tsx`
  - [x] Install and configure embla-carousel-react
  - [x] Display images with navigation arrows
  - [x] Add pagination dots
  - [x] Touch/swipe support for mobile (loop enabled)
  - [x] Smooth transitions
  - [x] Single image optimization (no controls)

---

## Results Page

- [x] Create `frontend/app/page.tsx` (home page)
  - [x] Render SearchForm component
  - [x] Hero section with app description
  - [x] Simple, clean design

- [x] Create results display (same page, responsive layout)
  - [x] Show total results count
  - [x] Display apartments in grid layout (2 cols desktop, 1 col mobile)
  - [x] Show loading spinner during API call
  - [x] Handle empty results (no matches found)
  - [x] Display error messages if API fails
  - [x] Sticky search form on desktop

---

## Styling & Design

- [x] Implement design guidelines:
  - [x] Color palette (primary blue, success green, clean white/gray)
  - [x] Typography (clear hierarchy)
  - [x] System fonts
  - [x] Match score visualization (color-coded badge)
  - [x] Card-based layout with shadows
  - [x] Smooth animations and transitions

- [x] Responsive design:
  - [x] Mobile-first approach with Tailwind
  - [x] Breakpoints for tablet and desktop (lg:grid-cols-3)
  - [x] Tested on different screen sizes

---

## Documentation

- [x] Create `frontend/README.md`:
  - [x] Installation instructions
  - [x] How to run development server
  - [x] Environment variable setup
  - [x] Component documentation

---

## Run & Test

- [x] Start Next.js development server:
  ```bash
  cd frontend
  npm run dev
  ```

- [x] Verify pages load:
  - [x] `http://localhost:3000/` (search form)
  - [x] Search results display correctly

---

## E2E Testing (Playwright)

- [x] Set up Playwright testing framework
  - [x] Install `@playwright/test` dependency
  - [x] Create `playwright.config.ts` with Chromium browser
  - [x] Configure single worker to avoid Claude API rate limits
  - [x] Set 60-second timeout for API-dependent tests

- [x] Create `frontend/e2e/homescout.spec.ts` with 20 test cases:
  - [x] **Homepage tests** (2): Header, hero section, search form display
  - [x] **Search Form tests** (5): Default values, form inputs, property type toggles, validation
  - [x] **Search Results tests** (5): Loading state, results display, apartment cards, match scores, no results
  - [x] **Image Carousel tests** (3): Image display, navigation arrows, carousel interaction
  - [x] **Responsive Layout tests** (2): Desktop grid, mobile stack
  - [x] **Error Handling tests** (1): API failure recovery
  - [x] **AI Features tests** (2): Reasoning display, highlight checkmarks

- [x] Add npm scripts for testing:
  - [x] `npm test` - Run all tests
  - [x] `npm run test:ui` - Run with Playwright UI
  - [x] `npm run test:headed` - Run in headed browser mode

- [x] Test execution:
  - [x] Tests without backend: `SKIP_BACKEND_TESTS=true npm test` (9 pass, 11 skip)
  - [x] Tests with backend: Start backend first, then `npm test` (all 20 pass when API available)

---

## Success Criteria

✅ **Milestone 2 COMPLETE:**
- ✅ Frontend runs on localhost:3000
- ✅ Search form accepts all required inputs
- ✅ Form submits to backend API successfully
- ✅ Results display in card grid layout
- ✅ Image carousels work smoothly
- ✅ Match scores are prominently displayed
- ✅ Reasoning and highlights render correctly
- ✅ Mobile-responsive design works well
- ✅ Clean, professional UI matching design guidelines
- ✅ E2E test suite with 20 Playwright tests

---

# 🔮 Milestone 3: Image Carousels & Polish (PLANNED)

**Goal:** Add final touches and polish the MVP

- [ ] Refine image carousel implementation
- [ ] Polish visual design and spacing
- [ ] Add smooth transitions and micro-interactions
- [ ] Cross-browser testing
- [ ] Performance optimization
- [ ] Final bug fixes
- [ ] Update README with complete setup instructions

**Estimated Time:** 2-3 hours

---

# ✅ Milestone 3: User Features & Enhanced Comparison (COMPLETED)

**Goal:** Add authentication, favorites, and AI-powered comparison tool

**Status:** ✅ COMPLETE

---

## Authentication
- [x] Google OAuth via Supabase
- [x] Auth gates on search page and compare page
- [x] AuthContext with session persistence and 5-second timeout
- [x] E2E test auth bypass (non-production only)

## Favorites
- [x] Heart icon on apartment cards
- [x] Optimistic UI updates with rollback
- [x] Supabase realtime subscriptions
- [x] Dedicated favorites page (`/favorites`)

## Enhanced Comparison Tool
- [x] Compare up to 3 apartments side-by-side
- [x] Claude AI head-to-head analysis (preferences optional)
- [x] Winner summary card with reasoning
- [x] Category-by-category scoring (Value, Space, Amenities, etc.)
- [x] Search context auto-passed from search page via Zustand store
- [x] Comparison table with Overall Score, rent, beds, baths, amenities

## Data Collection Pipeline
- [x] PostgreSQL database mode with async SQLAlchemy
- [x] Apify integration for apartments.com scraping
- [x] Data normalization and deduplication
- [x] Celery task queue with Redis
- [x] All apartment endpoints support both DB and JSON modes

---

# 🚀 Future Enhancements (Post-MVP)

- [ ] Notes for each apartment
- [ ] Viewing appointment scheduler
- [ ] Photo upload for visited apartments
- [ ] Neighborhood insights (walkability, transit, safety)
- [ ] Commute calculator
- [ ] Email notifications for new matches
- [ ] Deploy to production (Vercel + Railway/Fly.io)
