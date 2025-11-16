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

# 🚧 Milestone 2: Frontend Search & Results (IN PROGRESS)

**Goal:** Build Next.js frontend with search form and apartment results display

**Status:** 🔲 Not Started

---

## Setup & Project Structure

- [ ] Initialize Next.js project
  - [ ] Create `frontend/` directory
  - [ ] Run `npx create-next-app@latest` with TypeScript + Tailwind
  - [ ] Configure for App Router (not Pages Router)
  - [ ] Install additional dependencies:
    - [ ] `axios` or `fetch` for API calls
    - [ ] Image carousel library (swiper or embla-carousel-react)
    - [ ] Optional: shadcn/ui components

- [ ] Create project folder structure:
  ```
  frontend/
  ├── app/
  │   ├── page.tsx              # Home/search page
  │   ├── results/
  │   │   └── page.tsx          # Results page
  │   └── layout.tsx
  ├── components/
  │   ├── SearchForm.tsx        # Search input form
  │   ├── ApartmentCard.tsx     # Individual apartment display
  │   ├── ApartmentList.tsx     # Grid of apartments
  │   └── ImageCarousel.tsx     # Image carousel component
  ├── lib/
  │   └── api.ts                # API client functions
  ├── types/
  │   └── apartment.ts          # TypeScript interfaces
  └── public/
  ```

- [ ] Configure environment variables
  - [ ] Create `.env.local` with `NEXT_PUBLIC_API_URL=http://localhost:8000`

---

## TypeScript Types

- [ ] Create `frontend/types/apartment.ts` with interfaces:
  - [ ] `SearchParams` interface (matches backend SearchRequest)
  - [ ] `Apartment` interface (matches backend Apartment model)
  - [ ] `ApartmentWithScore` interface
  - [ ] `SearchResponse` interface

---

## API Client

- [ ] Create `frontend/lib/api.ts`
  - [ ] Create `searchApartments()` function
  - [ ] Handle POST request to `/api/search`
  - [ ] Handle errors and loading states
  - [ ] Type all requests/responses with TypeScript

---

## Search Form Component

- [ ] Create `frontend/components/SearchForm.tsx`
  - [ ] City input (text field)
  - [ ] Budget input (number or range slider)
  - [ ] Bedrooms select (dropdown: 0, 1, 2, 3)
  - [ ] Bathrooms select (dropdown: 1, 2, 3)
  - [ ] Property type multi-select (Apartment, Condo, Townhouse, Studio)
  - [ ] Move-in date picker (calendar input)
  - [ ] Other preferences textarea
  - [ ] Submit button
  - [ ] Form validation
  - [ ] Loading state during search
  - [ ] Error handling

---

## Apartment Card Component

- [ ] Create `frontend/components/ApartmentCard.tsx`
  - [ ] Display apartment image carousel (3-8 images)
  - [ ] Show match percentage badge (prominent display)
  - [ ] Display address and neighborhood
  - [ ] Show rent/month (formatted with $)
  - [ ] Display bedrooms, bathrooms, sqft
  - [ ] Show amenities as tags/badges
  - [ ] Display reasoning text from Claude
  - [ ] Show highlights as bullet points
  - [ ] Responsive design (mobile + desktop)
  - [ ] Hover effects and transitions

---

## Image Carousel Component

- [ ] Create `frontend/components/ImageCarousel.tsx`
  - [ ] Install and configure carousel library
  - [ ] Display images with navigation arrows
  - [ ] Add pagination dots
  - [ ] Touch/swipe support for mobile
  - [ ] Auto-play option (optional)
  - [ ] Smooth transitions

---

## Results Page

- [ ] Create `frontend/app/page.tsx` (home page)
  - [ ] Render SearchForm component
  - [ ] Hero section with app description
  - [ ] Simple, clean design

- [ ] Create results display (same page or separate route)
  - [ ] Show total results count
  - [ ] Display apartments in grid layout (2 cols desktop, 1 col mobile)
  - [ ] Show loading skeleton during API call
  - [ ] Handle empty results (no matches found)
  - [ ] Display error messages if API fails
  - [ ] Add "Search Again" button

---

## Styling & Design

- [ ] Implement design guidelines from spec.md:
  - [ ] Color palette (primary blue, success green, clean white)
  - [ ] Typography (clear hierarchy, 16px base)
  - [ ] System fonts
  - [ ] Match score visualization (badge or circular progress)
  - [ ] Card-based layout with shadows
  - [ ] Smooth animations and transitions

- [ ] Responsive design:
  - [ ] Mobile-first approach
  - [ ] Breakpoints for tablet and desktop
  - [ ] Test on different screen sizes

---

## Integration Testing

- [ ] Connect frontend to backend API:
  - [ ] Test search form submission
  - [ ] Verify API calls work from browser
  - [ ] Check CORS is working
  - [ ] Test with different search parameters

- [ ] Manual testing:
  - [ ] Test search flow end-to-end
  - [ ] Verify match scores display correctly
  - [ ] Test image carousels work smoothly
  - [ ] Check mobile responsiveness
  - [ ] Test error states (no results, API down, etc.)

---

## Documentation

- [ ] Create `frontend/README.md`:
  - [ ] Installation instructions
  - [ ] How to run development server
  - [ ] Environment variable setup
  - [ ] Component documentation

---

## Run & Test

- [ ] Start Next.js development server:
  ```bash
  cd frontend
  npm run dev
  ```

- [ ] Verify pages load:
  - [ ] `http://localhost:3000/` (search form)
  - [ ] Search results display correctly

- [ ] Test with real data from backend:
  - [ ] Make sure backend is running on port 8000
  - [ ] Submit search and verify results render
  - [ ] Check match scores and highlights display

---

## Success Criteria

✅ **Milestone 2 Complete When:**
- Frontend runs on localhost:3000
- Search form accepts all required inputs
- Form submits to backend API successfully
- Results display in card grid layout
- Image carousels work smoothly
- Match scores are prominently displayed
- Reasoning and highlights render correctly
- Mobile-responsive design works well
- No major bugs or usability issues
- Clean, professional UI matching design guidelines

---

## Estimated Time
**Total:** 4-6 hours
- Next.js setup: 30 minutes
- TypeScript types & API client: 30 minutes
- Search form component: 1 hour
- Apartment card component: 1 hour
- Image carousel integration: 1 hour
- Results page layout: 1 hour
- Styling & responsive design: 1-2 hours
- Testing & debugging: 30-60 minutes

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

# 🚀 Future Enhancements (Post-MVP)

- [ ] User authentication and accounts
- [ ] Save favorite apartments
- [ ] Comparison tool (side-by-side)
- [ ] Notes for each apartment
- [ ] Viewing appointment scheduler
- [ ] Photo upload for visited apartments
- [ ] Integrate real apartment APIs (Zillow, Apartments.com)
- [ ] Neighborhood insights (walkability, transit, safety)
- [ ] Commute calculator
- [ ] Email notifications for new matches
- [ ] Deploy to production (Vercel + Railway/Fly.io)
