# HomeScout MVP User Features Design

**Date:** 2026-02-02
**Status:** Ready for implementation
**Launch Market:** Bryn Mawr, PA (Main Line Philadelphia area)

---

## Overview

This design adds user-facing features to HomeScout for the MVP launch:

- OAuth authentication (Google/Apple)
- Save favorite apartments
- Save searches with new listing alerts
- Compare up to 3 apartments side-by-side
- Notifications when saved listings become unavailable
- Daily data collection from Apartments.com

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js)                              │
│   • Search UI with fixed criteria + text preferences                │
│   • Favorites list, saved searches, comparison view                 │
│   • Notification badge/dropdown                                     │
└───────────────┬─────────────────────────────┬───────────────────────┘
                │                             │
                ▼                             ▼
┌───────────────────────────┐   ┌─────────────────────────────────────┐
│        Supabase           │   │       FastAPI Backend               │
│                           │   │                                     │
│  • Auth (Google/Apple)    │   │  • POST /api/search (Claude AI)     │
│  • profiles table         │   │  • GET /api/apartments/{id}         │
│  • favorites table        │   │  • POST /api/apartments/batch       │
│  • saved_searches table   │   │  • POST /api/apartments/compare     │
│  • notifications table    │   │  • POST /webhooks/supabase/*        │
│  • Edge Functions         │   │                                     │
│  • Realtime subscriptions │   │  • PostgreSQL (apartments)          │
│  • Row Level Security     │   │  • Celery (daily scrape)            │
└───────────────────────────┘   └─────────────────────────────────────┘
                                              │
                                              ▼
                                ┌─────────────────────────────────────┐
                                │  External Services                  │
                                │  • Apify (Apartments.com scraping)  │
                                │  • Resend (email via Supabase)      │
                                └─────────────────────────────────────┘
```

### Data Ownership

| System | Owns |
|--------|------|
| Supabase | Users, favorites, saved searches, notifications |
| FastAPI | Apartments, scrape jobs, data sources |

### Communication Flow

- **Frontend → Supabase:** Direct SDK calls for auth, favorites, notifications
- **Frontend → FastAPI:** REST API for search, apartment details, comparison
- **FastAPI → Supabase:** Webhooks when listings unavailable or new matches found

---

## Supabase Data Models

### profiles (extends auth.users)

```sql
create table public.profiles (
  id uuid references auth.users(id) on delete cascade primary key,
  email text,
  name text,
  avatar_url text,
  email_notifications boolean default true,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Auto-create profile on signup
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, email, name, avatar_url)
  values (
    new.id,
    new.email,
    new.raw_user_meta_data->>'name',
    new.raw_user_meta_data->>'avatar_url'
  );
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();
```

### favorites

```sql
create table public.favorites (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,
  apartment_id text not null,
  notes text,
  is_available boolean default true,
  created_at timestamptz default now(),

  unique(user_id, apartment_id)
);

create index idx_favorites_user on favorites(user_id);
create index idx_favorites_apartment on favorites(apartment_id);
```

### saved_searches

```sql
create table public.saved_searches (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,
  name text not null,

  -- Search criteria
  city text not null,
  budget integer,
  bedrooms integer,
  bathrooms integer,
  property_type text,
  move_in_date date,
  preferences text,

  -- Notification settings
  notify_new_matches boolean default true,
  last_checked_at timestamptz,

  created_at timestamptz default now()
);

create index idx_saved_searches_user on saved_searches(user_id);
create index idx_saved_searches_notify on saved_searches(notify_new_matches)
  where notify_new_matches = true;
```

### notifications

```sql
create table public.notifications (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,

  type text not null,  -- 'listing_unavailable', 'new_match'
  title text not null,
  message text,

  apartment_id text,
  saved_search_id uuid references saved_searches(id) on delete set null,

  read boolean default false,
  emailed boolean default false,

  created_at timestamptz default now()
);

create index idx_notifications_user_unread on notifications(user_id, read)
  where read = false;
```

### Row Level Security

```sql
alter table profiles enable row level security;
alter table favorites enable row level security;
alter table saved_searches enable row level security;
alter table notifications enable row level security;

create policy "Users read own profile" on profiles
  for select using (auth.uid() = id);
create policy "Users update own profile" on profiles
  for update using (auth.uid() = id);

create policy "Users manage own favorites" on favorites
  for all using (auth.uid() = user_id);

create policy "Users manage own searches" on saved_searches
  for all using (auth.uid() = user_id);

create policy "Users read own notifications" on notifications
  for select using (auth.uid() = user_id);
create policy "Users update own notifications" on notifications
  for update using (auth.uid() = user_id);

create policy "Service can insert notifications" on notifications
  for insert with check (true);
```

---

## FastAPI Backend Changes

### New Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/apartments/{id}` | GET | Single apartment details |
| `/api/apartments/batch` | POST | Multiple apartments by ID |
| `/api/apartments/compare` | POST | Compare up to 3 with optional preference scoring |
| `/webhooks/supabase/check-matches` | POST | Check new listings against saved search |

### New Models (models.py)

```python
class CompareRequest(BaseModel):
    apartment_ids: List[str] = Field(..., max_length=3)
    preferences: Optional[str] = None

class CompareResponse(BaseModel):
    apartments: List[ApartmentWithScore]
    comparison_fields: List[str]
```

### Router: apartments.py

```python
@router.get("/{apartment_id}")
async def get_apartment(apartment_id: str, session: AsyncSession = Depends(get_async_session)):
    """Get single apartment details."""
    apt = await session.get(ApartmentModel, apartment_id)
    if not apt:
        raise HTTPException(404, "Apartment not found")
    return apt.to_dict()

@router.post("/batch")
async def get_apartments_batch(
    apartment_ids: List[str] = Body(..., max_length=50),
    session: AsyncSession = Depends(get_async_session)
):
    """Get multiple apartments by ID (for favorites list)."""
    stmt = select(ApartmentModel).where(ApartmentModel.id.in_(apartment_ids))
    result = await session.execute(stmt)
    apartments = {apt.id: apt.to_dict() for apt in result.scalars()}
    return [apartments.get(aid, {"id": aid, "is_available": False}) for aid in apartment_ids]

@router.post("/compare", response_model=CompareResponse)
async def compare_apartments(request: CompareRequest, session: AsyncSession = Depends(get_async_session)):
    """Compare up to 3 apartments with optional preference scoring."""
    # Fetch apartments, optionally score with Claude, return comparison
```

### Router: webhooks.py

```python
@router.post("/supabase/check-matches")
async def check_new_matches(
    saved_search: dict = Body(...),
    request: Request = None,
    session: AsyncSession = Depends(get_async_session)
):
    """Called by Supabase Edge Function to check for new matches."""
    verify_webhook(request)
    # Query apartments matching criteria added since last_checked_at
    # Return matching apartment IDs
```

---

## Supabase Edge Functions

### handle-unavailable

Called by FastAPI when listings become unavailable:

1. Find users who favorited these apartments
2. Mark favorites as `is_available = false`
3. Create notifications
4. Send emails to users with `email_notifications = true`

### check-saved-searches

Triggered daily after scraping:

1. Get all saved searches with `notify_new_matches = true`
2. Call FastAPI webhook to check for new matches
3. Create notifications for matches
4. Send email digests
5. Update `last_checked_at`

### Deployment

```bash
supabase functions deploy handle-unavailable
supabase functions deploy check-saved-searches

supabase secrets set RESEND_API_KEY=re_xxxxx
supabase secrets set FASTAPI_URL=https://api.homescout.app
supabase secrets set FASTAPI_WEBHOOK_SECRET=your-secret
```

---

## Frontend Components

### New Hooks

| Hook | Purpose |
|------|---------|
| `useAuth` | Auth state, signIn/signOut methods |
| `useFavorites` | CRUD favorites, realtime sync |
| `useSavedSearches` | CRUD saved searches |
| `useNotifications` | List, unread count, realtime updates |
| `useComparison` | Zustand store for compare selection |

### New Pages/Components

| Component | Purpose |
|-----------|---------|
| `AuthProvider` | Context for auth state |
| `ComparisonBar` | Sticky footer showing selected apartments |
| `/compare` page | Side-by-side comparison table |
| `/favorites` page | List of saved apartments |
| `/searches` page | List of saved searches |
| Notification dropdown | Bell icon with unread count, notification list |

### Comparison Features

- Compare up to 3 apartments
- Fields: rent, beds, baths, sqft, type, neighborhood, available date, amenities
- Optional: score against user's text preferences using Claude AI
- Highlight: lowest rent, best match score
- Link to original listing on Apartments.com

---

## Data Collection (Bryn Mawr)

### Configuration

- **Source:** Apartments.com via Apify
- **Actor:** `epctex/apartments-scraper-api`
- **Frequency:** Daily at 6 AM EST
- **Markets:** Bryn Mawr, Ardmore, Haverford, Wayne (Main Line area)
- **Stale threshold:** 3 days (listing not seen = marked unavailable)

### Celery Beat Schedule

```python
celery_app.conf.beat_schedule = {
    "scrape-bryn-mawr-daily": {
        "task": "app.tasks.scrape_tasks.scrape_source",
        "schedule": crontab(hour=11, minute=0),  # 6 AM EST
        "args": ("apartments_com",),
        "kwargs": {
            "cities": ["Bryn Mawr"],
            "state": "PA",
            "max_listings_per_city": 200,
        },
    },
    "cleanup-stale-listings": {
        "task": "app.tasks.maintenance_tasks.cleanup_stale_listings",
        "schedule": crontab(hour=12, minute=0),
        "kwargs": {"days_old": 3},
    },
    "trigger-saved-search-check": {
        "task": "app.tasks.notification_tasks.trigger_supabase_search_check",
        "schedule": crontab(hour=12, minute=30),
    },
}
```

### Apify Actor Input

```python
{
    "search": "Bryn Mawr, PA",
    "maxItems": 200,
    "includeInteriorAmenities": True,
    "includeReviews": False,
    "includeVisuals": True,
    "includeWalkScore": False,
}
```

### Expansion (If Inventory Low)

Add nearby Main Line towns:
- Ardmore, PA
- Haverford, PA
- Wayne, PA
- Villanova, PA
- Narberth, PA

---

## Environment Variables

### Backend (.env)

```bash
# Database
USE_DATABASE=true
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/homescout

# Redis
REDIS_URL=redis://localhost:6379/0

# Apify
APIFY_API_TOKEN=apify_api_xxxxx
APIFY_APARTMENTS_ACTOR_ID=epctex/apartments-scraper-api

# Supabase
SUPABASE_URL=https://yourproject.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIs...
SUPABASE_WEBHOOK_SECRET=your-webhook-secret
```

### Frontend (.env.local)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://yourproject.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIs...
```

### Supabase Secrets

```bash
RESEND_API_KEY=re_xxxxx
FASTAPI_URL=https://api.homescout.app
FASTAPI_WEBHOOK_SECRET=your-webhook-secret
```

---

## Cost Estimate (MVP)

| Service | Usage | Monthly Cost |
|---------|-------|--------------|
| Apify (Apartments.com) | ~200 listings/day | ~$10-15 |
| Supabase | Free tier | $0 |
| Resend | Free tier (3K emails) | $0 |
| PostgreSQL (Railway) | Small instance | ~$7 |
| **Total** | | **~$17-22/month** |

---

## Implementation Order

### Phase 1: Backend Infrastructure
1. Set up Supabase project (auth, tables, RLS)
2. Add FastAPI endpoints (`/apartments/{id}`, `/batch`, `/compare`)
3. Add webhook endpoint for Supabase
4. Update Celery schedule for Apartments.com + Bryn Mawr
5. Run initial data scrape

### Phase 2: Frontend Auth & Favorites
1. Add Supabase client and AuthProvider
2. Implement Google/Apple OAuth flow
3. Add favorites functionality (hook, UI, realtime)
4. Create favorites page

### Phase 3: Saved Searches & Notifications
1. Implement saved searches (hook, UI)
2. Create Supabase Edge Functions
3. Add notifications (hook, dropdown, realtime)
4. Set up email templates in Resend

### Phase 4: Comparison
1. Add comparison store (Zustand)
2. Create ComparisonBar component
3. Build comparison page with preference scoring
4. Add "Compare" button to ApartmentCard

### Phase 5: Polish & Launch
1. Test full flow end-to-end
2. Set up production environment
3. Configure daily scrape schedule
4. Launch for Bryn Mawr market

---

## Success Criteria

- [ ] Users can sign in with Google or Apple
- [ ] Users can save/unsave favorite apartments
- [ ] Users can save searches and receive alerts for new matches
- [ ] Users receive notifications (in-app + email) when saved listings become unavailable
- [ ] Users can compare up to 3 apartments side-by-side
- [ ] Comparison shows match score when preferences entered
- [ ] Users can click through to original Apartments.com listing
- [ ] Daily scrape runs automatically for Bryn Mawr area
- [ ] Stale listings (3+ days) are marked unavailable and trigger notifications
