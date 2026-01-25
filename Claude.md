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
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"city": "San Francisco, CA", "budget": 3500, "bedrooms": 2, "bathrooms": 1, "property_type": "Apartment, Condo", "move_in_date": "2025-12-01"}'
```

## Architecture

HomeScout is a full-stack apartment finder using Claude AI for intelligent matching.

```
SearchForm (React) → API Client → FastAPI Backend
                                    ├─ Filter apartments.json (by city, budget, beds, etc.)
                                    ├─ Claude AI scores filtered results
                                    └─ Return top 10 ranked by match_score
                                           ↓
                               ApartmentCard (with score badge, reasoning, highlights)
```

### Key Flow
1. User submits search criteria via `SearchForm.tsx`
2. `lib/api.ts` sends POST to `/api/search`
3. `apartment_service.py` filters `apartments.json` by basic criteria (city, budget, beds, baths, property type, move-in date)
4. `claude_service.py` calls Claude API with filtered apartments + user preferences
5. Claude returns JSON with `match_score` (0-100), `reasoning`, `highlights` for each apartment
6. Backend merges scores with apartment data, sorts by match_score, returns top 10
7. Frontend displays results in `ApartmentCard` components with image carousels

### Type Synchronization
Frontend TypeScript interfaces (`types/apartment.ts`) must match backend Pydantic models (`models.py`). Changes to data models require updates in both places.

## Key Files

### Frontend
- `app/page.tsx` - Main page with search form + results grid
- `components/SearchForm.tsx` - Form with all inputs, calls API
- `components/ApartmentCard.tsx` - Displays apartment with match score
- `components/ImageCarousel.tsx` - Embla carousel for photos
- `lib/api.ts` - API client (searchApartments, checkHealth)
- `types/apartment.ts` - TypeScript interfaces

### Backend
- `app/main.py` - FastAPI app with endpoints (/, /health, /api/apartments/count, /api/search)
- `app/models.py` - Pydantic models (SearchRequest, Apartment, ApartmentWithScore, SearchResponse)
- `app/services/claude_service.py` - Claude API integration, prompt building, JSON parsing
- `app/services/apartment_service.py` - Filter logic, ranking, merges scores with apartments
- `app/data/apartments.json` - Mock dataset (60 apartments across 4 cities)

## Environment Variables

### Frontend (`.env.local`)
- `NEXT_PUBLIC_API_URL` - Backend URL (default: http://localhost:8000)

### Backend (`.env`)
- `ANTHROPIC_API_KEY` - Claude API key (required)
- `FRONTEND_URL` - Frontend URL for CORS (default: http://localhost:3000)

## Claude AI Integration

The scoring prompts are in `claude_service.py`:
- **System prompt**: Defines Claude as apartment matching expert, scoring criteria (budget fit, location, space, property type, availability, amenities)
- **User prompt**: Contains search criteria + apartment data as JSON

Claude returns JSON array:
```json
[{
  "apartment_id": "apt-001",
  "match_score": 85,
  "reasoning": "Under budget with all requested amenities...",
  "highlights": ["Under budget", "Pet-friendly", "In-unit laundry"]
}]
```

The `_parse_json_response` method handles markdown code blocks in Claude's response.

## Development Notes

- Budget filtering is strict (no flexibility) - `apartment_service.py:69`
- Bedrooms filter is exact match, bathrooms is "at least" - `apartment_service.py:73-77`
- City matching is case-insensitive partial match on address - `apartment_service.py:65`
- Image domains configured in `next.config.ts` (picsum.photos, images.unsplash.com)
- CORS configured in `main.py` for localhost:3000
- Backend uses model `claude-sonnet-4-5-20250929`