# HomeScout - Technical Specification

## Overview
HomeScout is an apartment finder app that helps young professionals save 20-40 hours on apartment hunting by providing intelligent, ranked recommendations with all key information in one place.

## Requirements

### Functional Requirements
- **Search Input Form**
  - City (text input)
  - Budget (range slider or number input)
  - Bedrooms/Bathrooms (dropdown selectors)
  - Property Type (multi-select: apartment, condo, townhouse, studio)
  - Move-In Date (date picker)
  - Additional Preferences (text area for custom requirements)

- **Results Display**
  - Show top 10 apartment recommendations
  - Each listing displays:
    - Percentage match score (0-100%)
    - Image carousel (3-8 photos per listing)
    - Monthly rent
    - Bedrooms, bathrooms, square footage
    - Address and neighborhood
    - Key amenities (parking, laundry, pet-friendly, etc.)
  - Sort by match percentage (default) or rent

- **Match Scoring**
  - Use Claude Messages API to analyze user preferences against apartment features
  - Generate intelligent match percentage
  - Consider: budget fit, location, amenities, move-in date availability

### Non-Functional Requirements
- Mobile-responsive design
- Fast page loads (<3 seconds)
- Works on modern browsers (Chrome, Firefox, Safari, Edge)
- Accessible (WCAG 2.1 Level AA)

## Tech Stack

### Frontend
- **Framework:** Next.js 14 (App Router)
- **Language:** TypeScript
- **Styling:** Tailwind CSS
- **UI Components:** shadcn/ui (optional) or custom components
- **Image Carousel:** Swiper.js or embla-carousel-react
- **HTTP Client:** fetch API / axios

### Backend
- **Framework:** FastAPI (Python 3.12)
- **AI Integration:** Anthropic Claude Messages API
- **Data Storage:** JSON files (mock data for MVP)
- **CORS:** FastAPI CORS middleware

### Development Tools
- **Package Manager:** npm (frontend), pip (backend)
- **Environment Variables:** .env files
- **Linting:** ESLint (frontend), Ruff (backend)

## Design Guidelines

### Visual Design
- **Color Palette:**
  - Primary: Professional blue (#2563EB)
  - Success/Match: Green (#10B981)
  - Background: Clean white/light gray
  - Text: Dark gray (#1F2937)

- **Typography:**
  - Headings: Bold, clear hierarchy
  - Body: Readable 16px base size
  - Font: System fonts (SF Pro, Segoe UI, Roboto)

### UI Patterns
- **Search Form:** Single page with clear sections
- **Results Grid:** Card-based layout, 2 columns on desktop, 1 on mobile
- **Match Score:** Prominent badge or circular progress indicator
- **Images:** High-quality carousels with navigation dots/arrows
- **Loading States:** Skeleton screens during API calls

### User Experience
- Clear call-to-action buttons
- Inline validation for form inputs
- Error messages that guide users to fix issues
- Smooth transitions and animations
- Quick search results (<2 seconds after submit)

## Phase 1 Milestones

### Milestone 1: Backend Foundation & AI Integration
**Goal:** Build API that returns ranked apartment recommendations

**Tasks:**
- Set up FastAPI project structure
- Create mock apartment dataset (50-100 listings with realistic data)
- Build `/api/search` POST endpoint accepting all search parameters
- Integrate Claude Messages API for match scoring
- Implement ranking algorithm based on Claude's analysis
- Return top 10 apartments with match percentages
- Add CORS configuration for frontend integration

**Deliverables:**
- Working FastAPI server
- Mock data JSON file
- API endpoint returning ranked results
- Basic error handling

**Success Criteria:**
- API returns 10 apartments ranked by match score
- Match scores are contextually relevant to user input
- Response time <2 seconds

### Milestone 2: Frontend Search & Results
**Goal:** Build user interface for search and display results

**Tasks:**
- Initialize Next.js project with TypeScript
- Create search form with all input fields
- Build apartment card component
- Create results page with grid layout
- Connect frontend to backend API
- Add loading states and error handling
- Implement basic responsive design

**Deliverables:**
- Search form page
- Results display page
- API integration layer
- Mobile-responsive layout

**Success Criteria:**
- Users can submit search parameters
- Results display correctly in card format
- Works on mobile and desktop
- Shows loading and error states

### Milestone 3: Image Carousels & Polish
**Goal:** Add image carousels and polish the MVP

**Tasks:**
- Integrate image carousel library
- Add carousel to each apartment card
- Style match percentage badges/indicators
- Refine visual design and spacing
- Add smooth transitions and micro-interactions
- Test cross-browser compatibility
- Write basic README with setup instructions

**Deliverables:**
- Fully functional image carousels
- Polished UI matching design guidelines
- Complete MVP ready for user testing
- Setup documentation

**Success Criteria:**
- Image carousels work smoothly on all devices
- Visual design is clean and professional
- No major bugs or usability issues
- New developers can set up project from README

## Future Enhancements (Post-MVP)
- User accounts and saved searches
- Favorite/bookmark apartments
- Real apartment API integration (Zillow, Apartments.com)
- Neighborhood insights and commute calculator
- Viewing appointment scheduler
- Photo upload for visited apartments
- Notes and comparison tool
