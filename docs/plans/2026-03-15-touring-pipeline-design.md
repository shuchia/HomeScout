# Touring Pipeline Design

## Overview

After finding apartments via search/compare, HomeScout's user journey ends at discovery. The entire "action" phase — coordinating tours, capturing impressions, making decisions — is missing. This design adds a mobile-first touring pipeline that tracks apartments from initial interest through final decision, with AI-powered tools at each stage.

**Target user:** Young professionals apartment hunting — weekend warriors cramming tours into Saturday, remote workers scheduling opportunistically, or relocators with 1-2 days to see everything.

**Scope:** User-side organizer with light external touches (generate emails, export calendar events, share plans). No direct landlord/property manager integrations.

## Pipeline Stages

| Stage | Trigger | What Happens |
|-------|---------|-------------|
| **Interested** | User clicks "Start Touring" on a favorited apartment | Entry point. Claude generates inquiry email draft. |
| **Outreach Sent** | User marks outreach as sent | Tracks that user has contacted landlord. Records date. |
| **Scheduled** | User enters tour date/time | Calendar export available. AI groups same-day tours. |
| **Toured** | User marks as toured | Prompted for quick rating (1-5), notes, pros/cons. |
| **Deciding** | Automatic once 2+ apartments are toured | Claude synthesizes all tour impressions + listing data. |

Key decisions:
- Pipeline entries are created **from favorites** — only apartments the user has already saved
- Stages are linear but skippable (e.g., jump to "Scheduled" if landlord contacted first)
- "Deciding" activates automatically once 2+ apartments are toured
- A final `decision` field (applied/passed) archives the entry

## Data Model

### tour_pipeline (Supabase)

```
tour_pipeline
├── id (UUID)
├── user_id (FK -> profiles)
├── apartment_id (text)
├── stage: "interested" | "outreach_sent" | "scheduled" | "toured" | "deciding"
├── inquiry_email_draft (text, AI-generated)
├── outreach_sent_at (timestamp)
├── scheduled_date (date)
├── scheduled_time (time)
├── tour_rating (int, 1-5)
├── toured_at (timestamp)
├── decision (text: "applied" | "passed" | null)
├── decision_reason (text)
├── created_at, updated_at
```

### tour_notes (Supabase)

```
tour_notes
├── id (UUID)
├── tour_pipeline_id (FK)
├── user_id (FK)
├── content (text)
├── source: "voice" | "typed"
├── audio_s3_key (text, nullable — original recording)
├── transcription_status: "pending" | "complete" | "failed"
├── created_at (timestamp)
```

### tour_photos (Supabase)

```
tour_photos
├── id (UUID)
├── tour_pipeline_id (FK)
├── user_id (FK)
├── s3_key (text)
├── thumbnail_url (text)
├── caption (text, optional)
├── created_at (timestamp)
```

### tour_tags (Supabase)

```
tour_tags
├── id (UUID)
├── tour_pipeline_id (FK)
├── tag (text, e.g., "Great light", "Street noise")
├── sentiment: "pro" | "con"
```

## Mobile-First UI/UX

### Core Principle: One-Thumb, Eyes-Free Capture

During a tour the user is walking around, half-listening to the landlord. Capture must work with minimal friction — ideally without looking at the screen.

### /tours — Tour Dashboard (Mobile)

Tab-based list view instead of Kanban (columns don't work on narrow screens):

```
┌──────────────────────────┐
│  My Tours            [+] │
├──────────────────────────┤
│ [Today] [Upcoming] [All] │
├──────────────────────────┤
│ ┌──────────────────────┐ │
│ │ TODAY · Sat Mar 15   │ │
│ │                      │ │
│ │  2:00 PM             │ │
│ │  123 Oak St · $1,800 │ │
│ │  ★★★★☆  3 notes      │ │
│ │  Toured              │ │
│ │                      │ │
│ │  4:00 PM             │ │
│ │  456 Elm St · $2,100 │ │
│ │  Up next             │ │
│ │                      │ │
│ │  6:00 PM             │ │
│ │  789 Pine · $1,950   │ │
│ │  Scheduled           │ │
│ └──────────────────────┘ │
│                          │
│ ┌──────────────────────┐ │
│ │ NEEDS ACTION         │ │
│ │  200 2nd Ave · $1,700│ │
│ │  Draft ready         │ │
│ │  [Copy & Send]       │ │
│ └──────────────────────┘ │
│                          │
│ ┌──────────────────────┐ │
│ │ READY TO DECIDE (3)  │ │
│ │ [See AI Summary]     │ │
│ └──────────────────────┘ │
├──────────────────────────┤
│  Home   Tours   Favorites│
└──────────────────────────┘
```

- **Time-based grouping** instead of stage columns — "Today", "Upcoming", "Needs Action"
- Smart ordering: today's tours chronological, then actionable items
- Bottom tab navigation (Home / Tours / Favorites)
- Stage shown as status badge on each card

### /tours/[id] — Tour Detail (Mobile)

Swipeable tab sections instead of two-column layout:

```
┌──────────────────────────┐
│ <- 123 Oak St     $1,800 │
│   2bd/1ba · Scheduled    │
├──────────────────────────┤
│ [Info] [Capture] [Email] │
├──────────────────────────┤
│                          │
│  How was it?             │
│  ☆ ☆ ☆ ☆ ☆              │
│  (tap to rate)           │
│                          │
│  Quick tags:             │
│  [Great light] [Quiet]   │
│  [Spacious] [Modern]     │
│  [Small kitchen] [Noisy] │
│  [+ Custom]              │
│                          │
│ ┌────────────────────┐   │
│ │  Hold to talk      │   │
│ └────────────────────┘   │
│                          │
│ [Photo]        [Note]    │
│                          │
│  --- Your Notes ---      │
│  (voice) 2:35 PM         │
│  "Kitchen is smaller     │
│   than expected but      │
│   the living room is     │
│   really nice"           │
│                          │
│  (typed) 8:00 PM         │
│  "Checked commute,       │
│   25 min by subway"      │
│                          │
│  [Apply] [Pass] [Undecided│
└──────────────────────────┘
```

- Left column (Info tab): listing data from apartment DB
- Center column (Capture tab): all user-generated tour content
- Right column (Email tab): AI inquiry email with copy/share
- Voice capture button is the centerpiece — big, hold-to-talk

### Voice Capture Flow

```
User holds button
  -> Recording indicator (pulsing red dot, duration timer)
User releases
  -> Audio uploaded to S3
  -> Whisper API transcribes (async via Celery)
  -> Note appears with voice icon + timestamp
  -> "Transcribing..." placeholder, then text swaps in
  -> User can edit transcription
  -> Original audio kept in S3 for playback
```

### Quick Capture Sheet (Post-Tour Notification)

30 minutes after scheduled tour time, push a notification: "Just toured 123 Oak St? [Quick Rate]". Tapping opens a minimal bottom sheet:

```
┌──────────────────────────┐
│  123 Oak St · Just toured│
├──────────────────────────┤
│  ★ ★ ★ ★ ☆  (4/5)      │
│                          │
│  [Great light] [Spacious]│
│  [Small kitchen]         │
│                          │
│ ┌────────────────────┐   │
│ │  Hold to talk      │   │
│ └────────────────────┘   │
│                          │
│  [Done]      [Add More]  │
└──────────────────────────┘
```

Rate, tag, voice note — three actions, under 15 seconds.

### Photo Capture

- Direct camera access on mobile (no file picker detour)
- Optional caption per photo
- Thumbnails shown inline with notes in chronological order
- 10 MB max per photo, 20 photos per tour entry

### New Components

| Component | Purpose |
|-----------|---------|
| `TourList.tsx` | Time-grouped list view (mobile-first) |
| `TourCard.tsx` | Compact card with stage badge |
| `TourDetail.tsx` | Tabbed detail view (Info / Capture / Email) |
| `VoiceCapture.tsx` | Hold-to-talk button + Whisper transcription |
| `QuickCapture.tsx` | Post-tour bottom sheet (rate, tag, voice) |
| `PhotoCapture.tsx` | Camera/gallery with captions |
| `TagPicker.tsx` | Pro/con tag chips with suggestions |
| `StarRating.tsx` | Tappable star rating |
| `InquiryEmail.tsx` | AI email draft with copy/share |
| `DayPlanner.tsx` | Chronological day view with route |
| `TourPrompt.tsx` | CTA on favorites page |
| `BottomNav.tsx` | Mobile tab bar (Home / Tours / Favorites) |

## AI-Powered Features (Pro Tier Only)

### Stage: Interested — AI Inquiry Email

Claude generates personalized inquiry email using listing data + user context.

**Input:** Apartment details, user's search context (move-in date, budget, preferences), user's name.

**Output:** Subject line + email body. Claude tailors questions based on what's missing from the listing (no sqft -> asks about size, no pet policy -> asks about pets if user mentioned pets). User can edit before copying. Mobile share sheet: copy, email app, or text message.

### Stage: Scheduled — Smart Day Grouping

When 2+ tours are scheduled, Claude analyzes logistics.

**Input:** All scheduled tours with dates/times/addresses, user's home address (optional).

**Output — Tour Day Brief:**
- Groups by neighborhood proximity
- Suggests optimal visiting order
- Estimates travel times between stops
- Tips ("789 Pine and 123 Oak are 3 blocks apart — book back-to-back")
- Calendar export (.ics) and share plan buttons

### Stage: Toured — AI Note Enhancement

After voice note transcription, Claude does a light cleanup pass (optional, user can toggle off).

- Removes filler words, structures the note
- Shows both raw and enhanced versions
- Auto-suggests pro/con tags from note content

### Stage: Deciding — AI Decision Brief

Highest-value AI feature. Synthesizes everything when 2+ apartments are toured.

**Input:** All toured apartments' listing data, user ratings/tags/notes/photos, original search preferences.

**Output — Decision Brief:**
- Ranked list of toured apartments
- Each entry shows: user's rating, what they loved, what they flagged, Claude's analysis
- Translates budget differences into real annual costs
- Respects user's own ratings — contextualizes rather than overrides
- Final recommendation with reasoning
- Actionable CTA: "Apply to [apartment]" or "I need to think more"

### AI Feature Summary

| Stage | AI Feature | Claude Calls | Tier |
|-------|-----------|-------------|------|
| Interested | Inquiry email generation | 1 per apartment | Pro |
| Scheduled | Day grouping + route suggestions | 1 per tour day | Pro |
| Toured | Note enhancement + auto-tagging | 1 per voice note | Pro |
| Deciding | Decision brief with recommendation | 1 per refresh | Pro |

Free users get the full pipeline, manual notes, photos, ratings, and tags. AI features are the Pro upgrade motivator.

## Backend API Design

New router: `routers/tours.py`. All endpoints require authentication.

### Pipeline CRUD

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /api/tours` | Create | Move a favorite into the pipeline |
| `GET /api/tours` | List | All user's pipeline entries, grouped by stage |
| `GET /api/tours/{id}` | Detail | Single entry with notes, photos, tags |
| `PATCH /api/tours/{id}` | Update | Advance stage, update rating, set schedule, record decision |
| `DELETE /api/tours/{id}` | Remove | Remove from pipeline |

### Notes & Capture

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /api/tours/{id}/notes` | Create | Add typed note |
| `POST /api/tours/{id}/notes/voice` | Create | Upload audio -> S3, trigger transcription |
| `GET /api/tours/{id}/notes` | List | All notes chronological |
| `DELETE /api/tours/{id}/notes/{note_id}` | Delete | Remove a note |

### Photos

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /api/tours/{id}/photos` | Upload | Upload photo -> S3, generate thumbnail |
| `GET /api/tours/{id}/photos` | List | All photos with thumbnails and captions |
| `PATCH /api/tours/{id}/photos/{photo_id}` | Update | Edit caption |
| `DELETE /api/tours/{id}/photos/{photo_id}` | Delete | Remove photo |

### Tags

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /api/tours/{id}/tags` | Create | Add pro/con tag |
| `DELETE /api/tours/{id}/tags/{tag_id}` | Delete | Remove tag |
| `GET /api/tours/tags/suggestions` | List | Common tags + user's past tags |

### AI Features (Pro only)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /api/tours/{id}/inquiry-email` | Generate | Claude drafts inquiry email |
| `POST /api/tours/day-plan` | Generate | Optimized tour order for a date |
| `POST /api/tours/{id}/enhance-note` | Generate | Claude cleans up transcribed note, suggests tags |
| `POST /api/tours/decision-brief` | Generate | Claude synthesizes all toured apartments |

### Voice Transcription Flow

```
POST /api/tours/{id}/notes/voice (multipart: audio file)
  -> Upload audio to S3
  -> Create tour_note (source="voice", transcription_status="pending")
  -> Dispatch Celery task: transcribe_voice_note
  -> Return note ID (202 Accepted)

Celery worker (async):
  -> Download from S3
  -> Call OpenAI Whisper API
  -> Save transcription to tour_note.content
  -> Set transcription_status="complete"
  -> If Pro: chain enhance_note task

Frontend polls GET /api/tours/{id}/notes every 2 seconds
```

### New Celery Tasks

| Task | Queue | Description |
|------|-------|-------------|
| `transcribe_voice_note` | `default` | Whisper API transcription + save |
| `enhance_note` | `default` | Claude note cleanup + auto-tag suggestions (Pro, chained after transcription) |
| `generate_tour_reminder` | `default` | Push notification 30 min after scheduled tour time |

### Pydantic Schemas

```python
# Request models
class CreateTourRequest:
    apartment_id: str

class UpdateTourRequest:
    stage: Optional[str]
    scheduled_date: Optional[date]
    scheduled_time: Optional[time]
    tour_rating: Optional[int]       # 1-5
    decision: Optional[str]          # "applied" | "passed"
    decision_reason: Optional[str]

class CreateNoteRequest:
    content: str

class CreateTagRequest:
    tag: str
    sentiment: str                   # "pro" | "con"

class DayPlanRequest:
    date: date
    tour_ids: list[str]

# Response models
class TourResponse:
    id: str
    apartment: Apartment
    stage: str
    inquiry_email_draft: Optional[str]
    scheduled_date: Optional[date]
    scheduled_time: Optional[time]
    tour_rating: Optional[int]
    notes: list[NoteResponse]
    photos: list[PhotoResponse]
    tags: list[TagResponse]
    decision: Optional[str]
    created_at: datetime

class NoteResponse:
    id: str
    content: Optional[str]
    source: str                      # "voice" | "typed"
    transcription_status: Optional[str]
    audio_url: Optional[str]         # S3 presigned URL
    created_at: datetime

class PhotoResponse:
    id: str
    thumbnail_url: str
    full_url: str                    # S3 presigned URL
    caption: Optional[str]
    created_at: datetime

class DayPlanResponse:
    date: date
    tours_ordered: list[TourResponse]
    travel_notes: list[str]
    tips: list[str]
    calendar_ics: str

class DecisionBriefResponse:
    apartments: list[DecisionApartment]
    recommendation: Recommendation

class DecisionApartment:
    tour: TourResponse
    ai_take: str
    strengths: list[str]
    concerns: list[str]

class Recommendation:
    apartment_id: str
    reasoning: str
```

### Rate Limiting

| Action | Limit | Reason |
|--------|-------|--------|
| AI endpoints | 10/min (existing expensive path limit) | Claude API cost |
| Voice upload | 5 MB max file size | S3 storage cost |
| Photo upload | 10 MB max, 20 photos per tour entry | S3 storage cost |

### External Dependencies (New)

| Service | Purpose | Cost Model |
|---------|---------|------------|
| OpenAI Whisper API | Voice transcription | ~$0.006/min of audio |
| S3 | Audio + photo storage | ~$0.023/GB/month |
| CloudFront | Photo thumbnail serving | Already configured |

## Testing Strategy

### Backend Tests (~34 new tests)

| Test Group | Count | Coverage |
|-----------|-------|---------|
| Pipeline CRUD | 8 | Create from favorite, list by stage, advance stage, delete, duplicate prevention |
| Notes | 5 | Create typed, list chronological, delete, voice creates pending record |
| Photos | 4 | Upload to S3, thumbnail generation, caption update, delete |
| Tags | 4 | Add pro/con, delete, suggestions include user's past tags |
| AI endpoints | 6 | Inquiry email, day plan, note enhancement, decision brief, Pro-only gating (403 for free) |
| Voice transcription | 4 | Celery task dispatched, Whisper called, transcription saved, failure handling |
| Auth | 3 | All endpoints require auth, users only see own tours |

### Frontend E2E Tests (~10 new tests)

| Test | Coverage |
|------|---------|
| Tour dashboard loads | List view with stage badges |
| Move favorite to pipeline | "Start Touring" click, appears in tours |
| Advance through stages | Scheduled -> Toured with rating |
| Add typed note | Note appears with timestamp |
| Add/remove tags | Pro/con tags on tour detail |
| AI email generation | Mock Claude, verify draft appears |
| Quick capture sheet | Rate + tag in bottom sheet |
| Day plan | Select tours, get optimized order |

## Implementation Priority

Three phases, each independently shippable:

### Phase 1: Pipeline + Manual Capture (core value)

Tracking pipeline with typed notes, photos, ratings, and tags. No AI, no voice.

| Task | What |
|------|------|
| 1 | Supabase migrations (4 tables) |
| 2 | Backend pipeline CRUD endpoints + tests |
| 3 | Backend notes/photos/tags endpoints + tests |
| 4 | S3 photo upload with thumbnails |
| 5 | Frontend tour list page (mobile-first) |
| 6 | Frontend tour detail page with capture tab |
| 7 | Frontend tag picker + star rating components |
| 8 | "Start Touring" integration on favorites page |
| 9 | E2E tests |

### Phase 2: AI Features (Pro differentiator)

Claude-powered tools at each stage. Strongest Pro upgrade motivator.

| Task | What |
|------|------|
| 10 | AI inquiry email endpoint + Claude prompt |
| 11 | AI day plan endpoint + Claude prompt |
| 12 | AI note enhancement endpoint + Claude prompt |
| 13 | AI decision brief endpoint + Claude prompt |
| 14 | Pro tier gating on all AI endpoints |
| 15 | Frontend AI email component with copy/share |
| 16 | Frontend day planner view |
| 17 | Frontend decision brief view |
| 18 | Backend + E2E tests for AI features |

### Phase 3: Voice Capture (mobile polish)

Voice notes with Whisper transcription. Depends on Phase 1 notes infrastructure.

| Task | What |
|------|------|
| 19 | Whisper API integration service |
| 20 | Voice upload endpoint + Celery transcription task |
| 21 | AI auto-enhancement chained after transcription (Pro) |
| 22 | Frontend hold-to-talk component |
| 23 | Frontend transcription polling + status display |
| 24 | Post-tour push notification (Celery scheduled task) |
| 25 | Backend + E2E tests for voice |

**Phase order rationale:**
- Phase 1 ships a useful product without new external API dependencies
- Phase 2 adds the wow factor and drives Pro conversions (uses Claude, already integrated)
- Phase 3 adds the only new external dependency (Whisper) and most complex mobile UX
