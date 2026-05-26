# MVP User Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add user authentication, favorites, saved searches, notifications, and apartment comparison to HomeScout for Bryn Mawr PA launch.

**Architecture:** Supabase handles auth and user data (favorites, saved searches, notifications) with realtime sync. FastAPI handles apartments, search, and Claude AI scoring. Edge Functions bridge the two systems for notifications.

**Tech Stack:** Supabase (auth, database, edge functions), FastAPI, Next.js, Zustand (comparison state), Resend (email)

**Worktree:** `../HomeScout-mvp-user-features` (branch: `feat/mvp-user-features`)

---

## Phase 1: Supabase Setup

### Task 1.1: Create Supabase Project

**Context:** Set up the Supabase project and configure auth providers.

**Step 1: Create Supabase project**

Go to https://supabase.com/dashboard and create new project:
- Name: `homescout`
- Region: `us-east-1` (closest to PA)
- Generate a strong database password

**Step 2: Enable OAuth providers**

In Supabase Dashboard → Authentication → Providers:

1. Google:
   - Go to https://console.cloud.google.com/apis/credentials
   - Create OAuth 2.0 Client ID (Web application)
   - Authorized redirect URI: `https://<project-ref>.supabase.co/auth/v1/callback`
   - Copy Client ID and Secret to Supabase

2. Apple:
   - Go to https://developer.apple.com/account/resources/identifiers
   - Create Services ID for Sign in with Apple
   - Configure domain and redirect URI
   - Copy credentials to Supabase

**Step 3: Get API keys**

From Supabase Dashboard → Settings → API, copy:
- Project URL
- `anon` public key
- `service_role` secret key

**Step 4: Create environment files**

Create `frontend/.env.local`:
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIs...
```

Add to `backend/.env`:
```bash
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIs...
SUPABASE_WEBHOOK_SECRET=generate-a-random-secret-here
```

**Step 5: Commit environment examples**

```bash
cd ../HomeScout-mvp-user-features
echo "NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key" > frontend/.env.example

git add frontend/.env.example
git commit -m "chore: add frontend env example for Supabase"
```

---

### Task 1.2: Create Supabase Database Tables

**Files:**
- Create: `supabase/migrations/001_initial_schema.sql`

**Step 1: Create migrations directory**

```bash
mkdir -p supabase/migrations
```

**Step 2: Write migration file**

Create `supabase/migrations/001_initial_schema.sql`:

```sql
-- ============================================
-- PROFILES (extends auth.users)
-- ============================================
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

-- ============================================
-- FAVORITES
-- ============================================
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

-- ============================================
-- SAVED SEARCHES
-- ============================================
create table public.saved_searches (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,
  name text not null,

  city text not null,
  budget integer,
  bedrooms integer,
  bathrooms integer,
  property_type text,
  move_in_date date,
  preferences text,

  notify_new_matches boolean default true,
  last_checked_at timestamptz,

  created_at timestamptz default now()
);

create index idx_saved_searches_user on saved_searches(user_id);
create index idx_saved_searches_notify on saved_searches(notify_new_matches)
  where notify_new_matches = true;

-- ============================================
-- NOTIFICATIONS
-- ============================================
create table public.notifications (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,

  type text not null,
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

-- ============================================
-- ROW LEVEL SECURITY
-- ============================================
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

-- ============================================
-- REALTIME
-- ============================================
alter publication supabase_realtime add table favorites;
alter publication supabase_realtime add table notifications;
```

**Step 3: Run migration in Supabase**

Go to Supabase Dashboard → SQL Editor → paste and run the migration.

**Step 4: Verify tables created**

In Supabase Dashboard → Table Editor, confirm all 4 tables exist:
- profiles
- favorites
- saved_searches
- notifications

**Step 5: Commit migration**

```bash
git add supabase/migrations/001_initial_schema.sql
git commit -m "feat: add Supabase schema for user features"
```

---

## Phase 2: Backend API Endpoints

### Task 2.1: Add Apartment Detail Endpoint

**Files:**
- Create: `backend/app/routers/apartments.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_apartments_router.py`

**Step 1: Write failing test**

Create `backend/tests/test_apartments_router.py`:

```python
import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_get_apartment_not_found():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/apartments/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_apartments_batch_empty():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/apartments/batch", json=[])
    assert response.status_code == 200
    assert response.json() == []
```

**Step 2: Run test to verify it fails**

```bash
cd backend
pytest tests/test_apartments_router.py -v
```

Expected: FAIL (404 route not found)

**Step 3: Create apartments router**

Create `backend/app/routers/apartments.py`:

```python
"""
API endpoints for apartment details and batch operations.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session, is_database_enabled
from app.models.apartment import ApartmentModel
from app.services.apartment_service import load_apartments_from_json

router = APIRouter(prefix="/api/apartments", tags=["apartments"])


async def get_apartment_by_id(apartment_id: str, session: AsyncSession = None):
    """Get apartment from database or JSON fallback."""
    if is_database_enabled() and session:
        apt = await session.get(ApartmentModel, apartment_id)
        if apt:
            return apt.to_dict()
        return None
    else:
        # Fallback to JSON
        apartments = load_apartments_from_json()
        for apt in apartments:
            if apt.get("id") == apartment_id:
                return apt
        return None


@router.get("/{apartment_id}")
async def get_apartment(
    apartment_id: str,
    session: AsyncSession = Depends(get_async_session) if is_database_enabled() else None
):
    """Get single apartment details."""
    apt = await get_apartment_by_id(apartment_id, session)
    if not apt:
        raise HTTPException(status_code=404, detail="Apartment not found")
    return apt


@router.post("/batch")
async def get_apartments_batch(
    apartment_ids: List[str] = Body(..., max_length=50),
    session: AsyncSession = Depends(get_async_session) if is_database_enabled() else None
):
    """Get multiple apartments by ID (for favorites list)."""
    if not apartment_ids:
        return []

    results = []
    for aid in apartment_ids:
        apt = await get_apartment_by_id(aid, session)
        if apt:
            results.append(apt)
        else:
            results.append({"id": aid, "is_available": False})

    return results
```

**Step 4: Register router in main.py**

Modify `backend/app/main.py`, add after existing imports:

```python
from app.routers.apartments import router as apartments_router

# Add after other router includes
app.include_router(apartments_router)
```

**Step 5: Run tests**

```bash
pytest tests/test_apartments_router.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add app/routers/apartments.py tests/test_apartments_router.py app/main.py
git commit -m "feat: add apartment detail and batch endpoints"
```

---

### Task 2.2: Add Comparison Endpoint

**Files:**
- Modify: `backend/app/routers/apartments.py`
- Modify: `backend/app/models.py`
- Test: `backend/tests/test_apartments_router.py`

**Step 1: Add comparison models**

Add to `backend/app/models.py`:

```python
class CompareRequest(BaseModel):
    """Request model for apartment comparison."""
    apartment_ids: List[str] = Field(..., max_length=3)
    preferences: Optional[str] = Field(None, description="User preferences for scoring")


class CompareResponse(BaseModel):
    """Response model for apartment comparison."""
    apartments: List[ApartmentWithScore]
    comparison_fields: List[str]
```

**Step 2: Write failing test**

Add to `backend/tests/test_apartments_router.py`:

```python
@pytest.mark.asyncio
async def test_compare_apartments_empty():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/apartments/compare",
            json={"apartment_ids": []}
        )
    assert response.status_code == 200
    assert response.json()["apartments"] == []


@pytest.mark.asyncio
async def test_compare_apartments_max_three():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/apartments/compare",
            json={"apartment_ids": ["1", "2", "3", "4"]}
        )
    assert response.status_code == 422  # Validation error
```

**Step 3: Run tests**

```bash
pytest tests/test_apartments_router.py::test_compare_apartments_empty -v
```

Expected: FAIL (endpoint doesn't exist)

**Step 4: Add compare endpoint**

Add to `backend/app/routers/apartments.py`:

```python
from app.models import CompareRequest, CompareResponse, SearchRequest, ApartmentWithScore
from app.services.claude_service import ClaudeService


@router.post("/compare", response_model=CompareResponse)
async def compare_apartments(
    request: CompareRequest,
    session: AsyncSession = Depends(get_async_session) if is_database_enabled() else None
):
    """Compare up to 3 apartments with optional preference scoring."""
    if len(request.apartment_ids) > 3:
        raise HTTPException(status_code=400, detail="Maximum 3 apartments for comparison")

    if not request.apartment_ids:
        return CompareResponse(apartments=[], comparison_fields=[])

    # Fetch apartments
    apartments = []
    for aid in request.apartment_ids:
        apt = await get_apartment_by_id(aid, session)
        if apt:
            apartments.append(apt)

    # Score against preferences if provided
    if request.preferences and apartments:
        claude = ClaudeService()
        mock_search = SearchRequest(
            city=apartments[0].get("city", "Bryn Mawr, PA"),
            budget=max(a.get("rent", 0) for a in apartments) + 500,
            bedrooms=apartments[0].get("bedrooms", 1),
            bathrooms=apartments[0].get("bathrooms", 1),
            property_type="Any",
            move_in_date="2025-12-01",
            other_preferences=request.preferences,
        )
        scores = await claude.score_apartments(apartments, mock_search)

        # Merge scores into apartments
        score_map = {s["apartment_id"]: s for s in scores}
        for apt in apartments:
            if apt["id"] in score_map:
                apt["match_score"] = score_map[apt["id"]]["match_score"]
                apt["reasoning"] = score_map[apt["id"]]["reasoning"]
                apt["highlights"] = score_map[apt["id"]]["highlights"]

    comparison_fields = [
        "rent", "bedrooms", "bathrooms", "sqft",
        "property_type", "amenities", "available_date", "neighborhood"
    ]

    return CompareResponse(apartments=apartments, comparison_fields=comparison_fields)
```

**Step 5: Run tests**

```bash
pytest tests/test_apartments_router.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add app/routers/apartments.py app/models.py tests/test_apartments_router.py
git commit -m "feat: add apartment comparison endpoint with Claude scoring"
```

---

### Task 2.3: Add Webhook Endpoint for Supabase

**Files:**
- Create: `backend/app/routers/webhooks.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_webhooks.py`

**Step 1: Write failing test**

Create `backend/tests/test_webhooks.py`:

```python
import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_webhook_unauthorized():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/webhooks/supabase/check-matches",
            json={"city": "Bryn Mawr"}
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_authorized():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/webhooks/supabase/check-matches",
            json={"city": "Bryn Mawr", "budget": 3000},
            headers={"x-webhook-secret": "test-secret"}
        )
    # Should work with test secret in test environment
    assert response.status_code in [200, 401]
```

**Step 2: Create webhooks router**

Create `backend/app/routers/webhooks.py`:

```python
"""
Webhook endpoints for Supabase Edge Functions.
"""
import os
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Body, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session, is_database_enabled
from app.models.apartment import ApartmentModel
from app.services.apartment_service import load_apartments_from_json

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

WEBHOOK_SECRET = os.getenv("SUPABASE_WEBHOOK_SECRET", "test-secret")


def verify_webhook(request: Request):
    """Verify webhook came from Supabase."""
    secret = request.headers.get("x-webhook-secret")
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


@router.post("/supabase/check-matches")
async def check_new_matches(
    request: Request,
    saved_search: dict = Body(...),
    session: AsyncSession = Depends(get_async_session) if is_database_enabled() else None
):
    """
    Called by Supabase Edge Function to check for new matches.
    Returns apartments matching the saved search criteria.
    """
    verify_webhook(request)

    city = saved_search.get("city", "")
    budget = saved_search.get("budget")
    bedrooms = saved_search.get("bedrooms")
    bathrooms = saved_search.get("bathrooms")
    last_checked_at = saved_search.get("last_checked_at")

    matches = []

    if is_database_enabled() and session:
        stmt = select(ApartmentModel).where(
            ApartmentModel.is_active == 1,
            ApartmentModel.city.ilike(f"%{city}%"),
        )
        if budget:
            stmt = stmt.where(ApartmentModel.rent <= budget)
        if bedrooms is not None:
            stmt = stmt.where(ApartmentModel.bedrooms == bedrooms)
        if bathrooms is not None:
            stmt = stmt.where(ApartmentModel.bathrooms >= bathrooms)
        if last_checked_at:
            stmt = stmt.where(ApartmentModel.created_at > last_checked_at)

        result = await session.execute(stmt)
        matches = [apt.to_dict() for apt in result.scalars()]
    else:
        # Fallback to JSON
        apartments = load_apartments_from_json()
        for apt in apartments:
            if city.lower() not in apt.get("address", "").lower():
                continue
            if budget and apt.get("rent", 0) > budget:
                continue
            if bedrooms is not None and apt.get("bedrooms") != bedrooms:
                continue
            if bathrooms is not None and apt.get("bathrooms", 0) < bathrooms:
                continue
            matches.append(apt)

    return {"matches": matches, "count": len(matches)}
```

**Step 3: Register router**

Add to `backend/app/main.py`:

```python
from app.routers.webhooks import router as webhooks_router

app.include_router(webhooks_router)
```

**Step 4: Run tests**

```bash
pytest tests/test_webhooks.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add app/routers/webhooks.py tests/test_webhooks.py app/main.py
git commit -m "feat: add webhook endpoint for Supabase saved search matching"
```

---

## Phase 3: Frontend Authentication

### Task 3.1: Install Supabase Client

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/lib/supabase.ts`

**Step 1: Install dependencies**

```bash
cd frontend
npm install @supabase/supabase-js @supabase/ssr zustand
```

**Step 2: Create Supabase client**

Create `frontend/lib/supabase.ts`:

```typescript
import { createBrowserClient } from '@supabase/ssr'

export const supabase = createBrowserClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
)

// Types for Supabase tables
export interface Profile {
  id: string
  email: string
  name: string | null
  avatar_url: string | null
  email_notifications: boolean
}

export interface Favorite {
  id: string
  user_id: string
  apartment_id: string
  notes: string | null
  is_available: boolean
  created_at: string
}

export interface SavedSearch {
  id: string
  user_id: string
  name: string
  city: string
  budget: number | null
  bedrooms: number | null
  bathrooms: number | null
  property_type: string | null
  preferences: string | null
  notify_new_matches: boolean
  created_at: string
}

export interface Notification {
  id: string
  user_id: string
  type: 'listing_unavailable' | 'new_match'
  title: string
  message: string | null
  apartment_id: string | null
  saved_search_id: string | null
  read: boolean
  created_at: string
}
```

**Step 3: Commit**

```bash
git add package.json package-lock.json lib/supabase.ts
git commit -m "feat: add Supabase client and type definitions"
```

---

### Task 3.2: Create Auth Context

**Files:**
- Create: `frontend/contexts/AuthContext.tsx`
- Modify: `frontend/app/layout.tsx`

**Step 1: Create AuthContext**

Create `frontend/contexts/AuthContext.tsx`:

```typescript
'use client'
import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { User } from '@supabase/supabase-js'
import { supabase, Profile } from '@/lib/supabase'

interface AuthContextType {
  user: User | null
  profile: Profile | null
  loading: boolean
  signInWithGoogle: () => Promise<void>
  signInWithApple: () => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null)
      if (session?.user) fetchProfile(session.user.id)
      setLoading(false)
    })

    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        setUser(session?.user ?? null)
        if (session?.user) {
          await fetchProfile(session.user.id)
        } else {
          setProfile(null)
        }
      }
    )

    return () => subscription.unsubscribe()
  }, [])

  async function fetchProfile(userId: string) {
    const { data } = await supabase
      .from('profiles')
      .select('*')
      .eq('id', userId)
      .single()
    setProfile(data)
  }

  async function signInWithGoogle() {
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/auth/callback` }
    })
  }

  async function signInWithApple() {
    await supabase.auth.signInWithOAuth({
      provider: 'apple',
      options: { redirectTo: `${window.location.origin}/auth/callback` }
    })
  }

  async function signOut() {
    await supabase.auth.signOut()
    setProfile(null)
  }

  return (
    <AuthContext.Provider value={{
      user, profile, loading,
      signInWithGoogle, signInWithApple, signOut
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
```

**Step 2: Create auth callback page**

Create `frontend/app/auth/callback/page.tsx`:

```typescript
'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'

export default function AuthCallback() {
  const router = useRouter()

  useEffect(() => {
    supabase.auth.onAuthStateChange((event) => {
      if (event === 'SIGNED_IN') {
        router.push('/')
      }
    })
  }, [router])

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
        <p>Signing you in...</p>
      </div>
    </div>
  )
}
```

**Step 3: Wrap app in AuthProvider**

Modify `frontend/app/layout.tsx`, wrap children:

```typescript
import { AuthProvider } from '@/contexts/AuthContext'

// In the RootLayout component, wrap children:
<body>
  <AuthProvider>
    {children}
  </AuthProvider>
</body>
```

**Step 4: Commit**

```bash
git add contexts/AuthContext.tsx app/auth/callback/page.tsx app/layout.tsx
git commit -m "feat: add auth context with Google/Apple OAuth"
```

---

### Task 3.3: Create Auth UI Components

**Files:**
- Create: `frontend/components/AuthButton.tsx`
- Create: `frontend/components/UserMenu.tsx`

**Step 1: Create AuthButton**

Create `frontend/components/AuthButton.tsx`:

```typescript
'use client'
import { useAuth } from '@/contexts/AuthContext'

export function AuthButton() {
  const { user, loading, signInWithGoogle } = useAuth()

  if (loading) {
    return <div className="w-20 h-9 bg-gray-200 animate-pulse rounded-lg"></div>
  }

  if (user) {
    return null // UserMenu will handle signed-in state
  }

  return (
    <button
      onClick={signInWithGoogle}
      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
    >
      Sign In
    </button>
  )
}
```

**Step 2: Create UserMenu**

Create `frontend/components/UserMenu.tsx`:

```typescript
'use client'
import { useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import Link from 'next/link'

export function UserMenu() {
  const { user, profile, signOut } = useAuth()
  const [isOpen, setIsOpen] = useState(false)

  if (!user) return null

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 p-2 rounded-lg hover:bg-gray-100"
      >
        {profile?.avatar_url ? (
          <img
            src={profile.avatar_url}
            alt={profile.name || 'User'}
            className="w-8 h-8 rounded-full"
          />
        ) : (
          <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white">
            {profile?.name?.[0] || user.email?.[0] || '?'}
          </div>
        )}
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border z-20">
            <div className="p-3 border-b">
              <p className="font-medium truncate">{profile?.name || 'User'}</p>
              <p className="text-sm text-gray-500 truncate">{user.email}</p>
            </div>
            <nav className="p-2">
              <Link
                href="/favorites"
                className="block px-3 py-2 rounded hover:bg-gray-100"
                onClick={() => setIsOpen(false)}
              >
                My Favorites
              </Link>
              <Link
                href="/searches"
                className="block px-3 py-2 rounded hover:bg-gray-100"
                onClick={() => setIsOpen(false)}
              >
                Saved Searches
              </Link>
              <button
                onClick={() => { signOut(); setIsOpen(false) }}
                className="w-full text-left px-3 py-2 rounded hover:bg-gray-100 text-red-600"
              >
                Sign Out
              </button>
            </nav>
          </div>
        </>
      )}
    </div>
  )
}
```

**Step 3: Commit**

```bash
git add components/AuthButton.tsx components/UserMenu.tsx
git commit -m "feat: add auth button and user menu components"
```

---

## Phase 4: Favorites Feature

### Task 4.1: Create Favorites Hook

**Files:**
- Create: `frontend/hooks/useFavorites.ts`
- Modify: `frontend/lib/api.ts`

**Step 1: Add batch endpoint to API client**

Add to `frontend/lib/api.ts`:

```typescript
export async function getApartmentsBatch(ids: string[]): Promise<Apartment[]> {
  if (ids.length === 0) return []

  const response = await fetch(`${API_URL}/api/apartments/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ids),
  })

  if (!response.ok) {
    throw new ApiError('Failed to fetch apartments', response.status)
  }

  return response.json()
}
```

**Step 2: Create useFavorites hook**

Create `frontend/hooks/useFavorites.ts`:

```typescript
'use client'
import { useEffect, useState, useCallback } from 'react'
import { supabase, Favorite } from '@/lib/supabase'
import { useAuth } from '@/contexts/AuthContext'
import { getApartmentsBatch } from '@/lib/api'
import { Apartment } from '@/types/apartment'

interface FavoriteWithApartment extends Favorite {
  apartment: Apartment | null
}

export function useFavorites() {
  const { user } = useAuth()
  const [favorites, setFavorites] = useState<FavoriteWithApartment[]>([])
  const [loading, setLoading] = useState(true)

  const loadFavorites = useCallback(async () => {
    if (!user) {
      setFavorites([])
      setLoading(false)
      return
    }

    setLoading(true)

    // Get favorites from Supabase
    const { data: favs } = await supabase
      .from('favorites')
      .select('*')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false })

    if (!favs?.length) {
      setFavorites([])
      setLoading(false)
      return
    }

    // Fetch apartment details from FastAPI
    const apartmentIds = favs.map(f => f.apartment_id)
    try {
      const apartments = await getApartmentsBatch(apartmentIds)
      const apartmentMap = new Map(apartments.map(a => [a.id, a]))

      const merged = favs.map(fav => ({
        ...fav,
        apartment: apartmentMap.get(fav.apartment_id) || null
      }))

      setFavorites(merged)
    } catch (error) {
      console.error('Failed to fetch apartment details:', error)
      setFavorites(favs.map(fav => ({ ...fav, apartment: null })))
    }

    setLoading(false)
  }, [user])

  useEffect(() => {
    loadFavorites()

    if (!user) return

    // Realtime subscription
    const subscription = supabase
      .channel('favorites-changes')
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'favorites',
          filter: `user_id=eq.${user.id}`
        },
        () => loadFavorites()
      )
      .subscribe()

    return () => {
      subscription.unsubscribe()
    }
  }, [user, loadFavorites])

  async function addFavorite(apartmentId: string): Promise<boolean> {
    if (!user) return false

    const { error } = await supabase.from('favorites').insert({
      user_id: user.id,
      apartment_id: apartmentId,
    })

    return !error
  }

  async function removeFavorite(apartmentId: string): Promise<boolean> {
    if (!user) return false

    const { error } = await supabase
      .from('favorites')
      .delete()
      .eq('user_id', user.id)
      .eq('apartment_id', apartmentId)

    return !error
  }

  function isFavorite(apartmentId: string): boolean {
    return favorites.some(f => f.apartment_id === apartmentId)
  }

  return {
    favorites,
    loading,
    addFavorite,
    removeFavorite,
    isFavorite,
    refresh: loadFavorites
  }
}
```

**Step 3: Commit**

```bash
git add hooks/useFavorites.ts lib/api.ts
git commit -m "feat: add favorites hook with realtime sync"
```

---

### Task 4.2: Create Favorites UI

**Files:**
- Create: `frontend/components/FavoriteButton.tsx`
- Create: `frontend/app/favorites/page.tsx`

**Step 1: Create FavoriteButton**

Create `frontend/components/FavoriteButton.tsx`:

```typescript
'use client'
import { useState } from 'react'
import { useFavorites } from '@/hooks/useFavorites'
import { useAuth } from '@/contexts/AuthContext'

interface FavoriteButtonProps {
  apartmentId: string
  className?: string
}

export function FavoriteButton({ apartmentId, className = '' }: FavoriteButtonProps) {
  const { user, signInWithGoogle } = useAuth()
  const { isFavorite, addFavorite, removeFavorite } = useFavorites()
  const [loading, setLoading] = useState(false)

  const favorited = isFavorite(apartmentId)

  async function handleClick() {
    if (!user) {
      signInWithGoogle()
      return
    }

    setLoading(true)
    if (favorited) {
      await removeFavorite(apartmentId)
    } else {
      await addFavorite(apartmentId)
    }
    setLoading(false)
  }

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      className={`p-2 rounded-full transition-colors ${
        favorited
          ? 'bg-red-100 text-red-600 hover:bg-red-200'
          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
      } disabled:opacity-50 ${className}`}
      title={favorited ? 'Remove from favorites' : 'Add to favorites'}
    >
      <svg
        className="w-5 h-5"
        fill={favorited ? 'currentColor' : 'none'}
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
        />
      </svg>
    </button>
  )
}
```

**Step 2: Create favorites page**

Create `frontend/app/favorites/page.tsx`:

```typescript
'use client'
import { useFavorites } from '@/hooks/useFavorites'
import { useAuth } from '@/contexts/AuthContext'
import { ApartmentCard } from '@/components/ApartmentCard'
import Link from 'next/link'

export default function FavoritesPage() {
  const { user, loading: authLoading, signInWithGoogle } = useAuth()
  const { favorites, loading } = useFavorites()

  if (authLoading) {
    return (
      <div className="max-w-6xl mx-auto p-6">
        <div className="animate-pulse">
          <div className="h-8 w-48 bg-gray-200 rounded mb-6"></div>
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-64 bg-gray-200 rounded-lg"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="max-w-6xl mx-auto p-6 text-center py-20">
        <h1 className="text-2xl font-bold mb-4">My Favorites</h1>
        <p className="text-gray-600 mb-6">Sign in to save your favorite apartments.</p>
        <button
          onClick={signInWithGoogle}
          className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          Sign In with Google
        </button>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">My Favorites</h1>

      {loading ? (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-64 bg-gray-200 rounded-lg animate-pulse"></div>
          ))}
        </div>
      ) : favorites.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-600 mb-4">You haven't saved any favorites yet.</p>
          <Link
            href="/"
            className="text-blue-600 hover:underline"
          >
            Start searching for apartments
          </Link>
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {favorites.map(fav => (
            <div key={fav.id} className="relative">
              {!fav.is_available && (
                <div className="absolute inset-0 bg-white/80 z-10 flex items-center justify-center rounded-lg">
                  <span className="px-3 py-1 bg-red-100 text-red-800 rounded-full text-sm font-medium">
                    No longer available
                  </span>
                </div>
              )}
              {fav.apartment && (
                <ApartmentCard apartment={fav.apartment as any} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

**Step 3: Commit**

```bash
git add components/FavoriteButton.tsx app/favorites/page.tsx
git commit -m "feat: add favorite button and favorites page"
```

---

## Phase 5: Comparison Feature

### Task 5.1: Create Comparison Store

**Files:**
- Create: `frontend/hooks/useComparison.ts`

**Step 1: Create Zustand store**

Create `frontend/hooks/useComparison.ts`:

```typescript
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface ComparisonStore {
  apartmentIds: string[]
  addToCompare: (id: string) => void
  removeFromCompare: (id: string) => void
  clearComparison: () => void
  isInComparison: (id: string) => boolean
}

export const useComparison = create<ComparisonStore>()(
  persist(
    (set, get) => ({
      apartmentIds: [],

      addToCompare: (id) => {
        const current = get().apartmentIds
        if (current.length < 3 && !current.includes(id)) {
          set({ apartmentIds: [...current, id] })
        }
      },

      removeFromCompare: (id) => {
        set({ apartmentIds: get().apartmentIds.filter(i => i !== id) })
      },

      clearComparison: () => set({ apartmentIds: [] }),

      isInComparison: (id) => get().apartmentIds.includes(id),
    }),
    { name: 'homescout-comparison' }
  )
)
```

**Step 2: Commit**

```bash
git add hooks/useComparison.ts
git commit -m "feat: add comparison store with Zustand"
```

---

### Task 5.2: Create Comparison UI

**Files:**
- Create: `frontend/components/ComparisonBar.tsx`
- Create: `frontend/components/CompareButton.tsx`
- Create: `frontend/app/compare/page.tsx`
- Modify: `frontend/lib/api.ts`

**Step 1: Add compare API function**

Add to `frontend/lib/api.ts`:

```typescript
export interface CompareResponse {
  apartments: ApartmentWithScore[]
  comparison_fields: string[]
}

export async function compareApartments(
  apartmentIds: string[],
  preferences?: string
): Promise<CompareResponse> {
  const response = await fetch(`${API_URL}/api/apartments/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      apartment_ids: apartmentIds,
      preferences: preferences || null
    }),
  })

  if (!response.ok) {
    throw new ApiError('Failed to compare apartments', response.status)
  }

  return response.json()
}
```

**Step 2: Create ComparisonBar**

Create `frontend/components/ComparisonBar.tsx`:

```typescript
'use client'
import { useRouter } from 'next/navigation'
import { useComparison } from '@/hooks/useComparison'

export function ComparisonBar() {
  const { apartmentIds, clearComparison } = useComparison()
  const router = useRouter()

  if (apartmentIds.length === 0) return null

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-white border-t shadow-lg p-4 z-50">
      <div className="max-w-6xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-600">
            {apartmentIds.length} of 3 selected
          </span>
          <div className="flex gap-2">
            {[0, 1, 2].map(i => (
              <div
                key={i}
                className={`w-8 h-8 rounded border-2 ${
                  apartmentIds[i]
                    ? 'bg-blue-100 border-blue-500'
                    : 'border-dashed border-gray-300'
                }`}
              />
            ))}
          </div>
        </div>

        <div className="flex gap-3">
          <button
            onClick={clearComparison}
            className="px-4 py-2 text-gray-600 hover:text-gray-800"
          >
            Clear
          </button>
          <button
            onClick={() => router.push('/compare')}
            disabled={apartmentIds.length < 2}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg
                       disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            Compare ({apartmentIds.length})
          </button>
        </div>
      </div>
    </div>
  )
}
```

**Step 3: Create CompareButton**

Create `frontend/components/CompareButton.tsx`:

```typescript
'use client'
import { useComparison } from '@/hooks/useComparison'

interface CompareButtonProps {
  apartmentId: string
  className?: string
}

export function CompareButton({ apartmentId, className = '' }: CompareButtonProps) {
  const { addToCompare, removeFromCompare, isInComparison, apartmentIds } = useComparison()
  const inComparison = isInComparison(apartmentId)
  const canAddMore = apartmentIds.length < 3

  return (
    <button
      onClick={() => inComparison
        ? removeFromCompare(apartmentId)
        : addToCompare(apartmentId)
      }
      disabled={!inComparison && !canAddMore}
      className={`px-3 py-1 rounded text-sm transition-colors ${
        inComparison
          ? 'bg-blue-100 text-blue-700 hover:bg-blue-200'
          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
      } disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
    >
      {inComparison ? '✓ Comparing' : '+ Compare'}
    </button>
  )
}
```

**Step 4: Create compare page**

Create `frontend/app/compare/page.tsx`:

```typescript
'use client'
import { useEffect, useState } from 'react'
import { useComparison } from '@/hooks/useComparison'
import { compareApartments, CompareResponse } from '@/lib/api'
import Link from 'next/link'

export default function ComparePage() {
  const { apartmentIds, removeFromCompare, clearComparison } = useComparison()
  const [data, setData] = useState<CompareResponse | null>(null)
  const [preferences, setPreferences] = useState('')
  const [loading, setLoading] = useState(true)
  const [scoring, setScoring] = useState(false)

  useEffect(() => {
    if (apartmentIds.length >= 2) {
      loadComparison()
    } else {
      setLoading(false)
    }
  }, [apartmentIds])

  async function loadComparison(withPreferences?: string) {
    setLoading(true)
    try {
      const result = await compareApartments(apartmentIds, withPreferences)
      setData(result)
    } catch (error) {
      console.error('Failed to load comparison:', error)
    }
    setLoading(false)
  }

  async function scoreWithPreferences() {
    if (!preferences.trim()) return
    setScoring(true)
    await loadComparison(preferences)
    setScoring(false)
  }

  if (apartmentIds.length < 2) {
    return (
      <div className="max-w-4xl mx-auto p-8 text-center">
        <h1 className="text-2xl font-bold mb-4">Compare Apartments</h1>
        <p className="text-gray-600 mb-6">Select at least 2 apartments to compare.</p>
        <Link href="/" className="text-blue-600 hover:underline">
          Back to search
        </Link>
      </div>
    )
  }

  const apartments = data?.apartments || []

  const comparisonFields = [
    { key: 'rent', label: 'Rent', format: (v: number) => `$${v?.toLocaleString()}/mo` },
    { key: 'bedrooms', label: 'Bedrooms', format: (v: number) => v === 0 ? 'Studio' : `${v} bed` },
    { key: 'bathrooms', label: 'Bathrooms', format: (v: number) => `${v} bath` },
    { key: 'sqft', label: 'Size', format: (v: number) => v ? `${v.toLocaleString()} sqft` : '—' },
    { key: 'property_type', label: 'Type', format: (v: string) => v || '—' },
    { key: 'neighborhood', label: 'Neighborhood', format: (v: string) => v || '—' },
    { key: 'available_date', label: 'Available', format: (v: string) => v || 'Now' },
  ]

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Compare Apartments</h1>
        <button
          onClick={clearComparison}
          className="text-gray-600 hover:text-gray-800"
        >
          Clear All
        </button>
      </div>

      {/* Preferences Input */}
      <div className="mb-6 p-4 bg-gray-50 rounded-lg">
        <label className="block text-sm font-medium mb-2">
          Score against your preferences (optional)
        </label>
        <div className="flex gap-3">
          <input
            type="text"
            value={preferences}
            onChange={(e) => setPreferences(e.target.value)}
            placeholder="e.g., Pet-friendly, parking, near train station..."
            className="flex-1 px-4 py-2 border rounded-lg"
          />
          <button
            onClick={scoreWithPreferences}
            disabled={scoring || !preferences.trim()}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg disabled:bg-gray-300"
          >
            {scoring ? 'Scoring...' : 'Score'}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12">Loading comparison...</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className="w-40"></th>
                {apartments.map(apt => (
                  <th key={apt.id} className="p-4 text-left min-w-64">
                    <div className="relative">
                      <button
                        onClick={() => removeFromCompare(apt.id)}
                        className="absolute -top-2 -right-2 w-6 h-6 bg-red-100
                                   text-red-600 rounded-full text-sm hover:bg-red-200"
                      >
                        ×
                      </button>
                      <img
                        src={apt.images?.[0] || '/placeholder.jpg'}
                        alt={apt.address}
                        className="w-full h-40 object-cover rounded-lg mb-3"
                      />
                      <p className="font-medium text-sm">{apt.address}</p>

                      {apt.match_score !== undefined && (
                        <div className="mt-2 inline-flex items-center px-3 py-1
                                        bg-green-100 text-green-800 rounded-full text-sm">
                          {apt.match_score}% match
                        </div>
                      )}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              {comparisonFields.map(field => (
                <tr key={field.key} className="border-t">
                  <td className="p-4 font-medium text-gray-600">{field.label}</td>
                  {apartments.map(apt => {
                    const value = (apt as any)[field.key]
                    const isLowest = field.key === 'rent' &&
                      apt.rent === Math.min(...apartments.map(a => a.rent))

                    return (
                      <td
                        key={apt.id}
                        className={`p-4 ${isLowest ? 'text-green-600 font-semibold' : ''}`}
                      >
                        {field.format(value)}
                      </td>
                    )
                  })}
                </tr>
              ))}

              {/* Amenities row */}
              <tr className="border-t">
                <td className="p-4 font-medium text-gray-600 align-top">Amenities</td>
                {apartments.map(apt => (
                  <td key={apt.id} className="p-4">
                    <div className="flex flex-wrap gap-1">
                      {apt.amenities?.slice(0, 6).map(amenity => (
                        <span
                          key={amenity}
                          className="px-2 py-1 bg-gray-100 text-xs rounded"
                        >
                          {amenity}
                        </span>
                      ))}
                    </div>
                  </td>
                ))}
              </tr>

              {/* AI Reasoning row */}
              {apartments[0]?.reasoning && (
                <tr className="border-t bg-blue-50">
                  <td className="p-4 font-medium text-gray-600 align-top">AI Analysis</td>
                  {apartments.map(apt => (
                    <td key={apt.id} className="p-4 text-sm">
                      <p className="mb-2">{apt.reasoning}</p>
                      {apt.highlights && (
                        <ul className="list-disc list-inside text-green-700">
                          {apt.highlights.map((h: string) => <li key={h}>{h}</li>)}
                        </ul>
                      )}
                    </td>
                  ))}
                </tr>
              )}

              {/* Action row */}
              <tr className="border-t">
                <td className="p-4"></td>
                {apartments.map(apt => (
                  <td key={apt.id} className="p-4">
                    <a
                      href={(apt as any).source_url || '#'}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-block px-4 py-2 bg-blue-600 text-white
                                 rounded-lg text-sm hover:bg-blue-700"
                    >
                      View Listing →
                    </a>
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
```

**Step 5: Commit**

```bash
git add components/ComparisonBar.tsx components/CompareButton.tsx app/compare/page.tsx lib/api.ts
git commit -m "feat: add apartment comparison UI with preference scoring"
```

---

## Phase 6: Data Collection for Bryn Mawr

### Task 6.1: Update Celery Schedule

**Files:**
- Modify: `backend/app/celery_app.py`

**Step 1: Update beat schedule**

Replace the beat schedule in `backend/app/celery_app.py`:

```python
# Beat schedule for Bryn Mawr MVP
celery_app.conf.beat_schedule = {
    # Daily scrape at 6 AM EST (11 AM UTC)
    "scrape-bryn-mawr-daily": {
        "task": "app.tasks.scrape_tasks.scrape_source",
        "schedule": crontab(hour=11, minute=0),
        "args": ("apartments_com",),
        "kwargs": {
            "cities": ["Bryn Mawr"],
            "state": "PA",
            "max_listings_per_city": 200,
        },
    },

    # Cleanup stale after 3 days
    "cleanup-stale-listings": {
        "task": "app.tasks.maintenance_tasks.cleanup_stale_listings",
        "schedule": crontab(hour=12, minute=0),
        "kwargs": {"days_old": 3},
    },

    # Reset rate limits daily
    "reset-daily-rate-limits": {
        "task": "app.tasks.maintenance_tasks.reset_rate_limits",
        "schedule": crontab(hour=0, minute=0),
        "kwargs": {"period": "day"},
    },
}
```

**Step 2: Update Apify actor ID**

Update in `backend/app/services/scrapers/apify_service.py`:

```python
ACTORS = {
    "apartments_com": os.getenv(
        "APIFY_APARTMENTS_ACTOR_ID",
        "epctex/apartments-scraper-api"
    ),
}
```

**Step 3: Commit**

```bash
git add app/celery_app.py app/services/scrapers/apify_service.py
git commit -m "feat: configure data collection for Bryn Mawr PA"
```

---

### Task 6.2: Create Initial Scrape Script

**Files:**
- Create: `backend/scripts/initial_scrape.py`

**Step 1: Create script**

Create `backend/scripts/__init__.py` (empty file) and `backend/scripts/initial_scrape.py`:

```python
"""
Run once before launch to populate initial apartment data.
Usage: cd backend && python -m scripts.initial_scrape
"""
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tasks.scrape_tasks import scrape_source


def main():
    print("Starting initial Bryn Mawr area scrape...")
    print("This may take a few minutes...\n")

    result = scrape_source.apply(
        args=("apartments_com",),
        kwargs={
            "cities": ["Bryn Mawr"],
            "state": "PA",
            "max_listings_per_city": 300,
        }
    ).get(timeout=600)

    print(f"\nScrape complete!")
    print(f"  Status: {result.get('status')}")
    print(f"  Total found: {result.get('total_found', 0)}")
    print(f"  New listings: {result.get('total_new', 0)}")
    print(f"  Duplicates: {result.get('total_duplicates', 0)}")
    print(f"  Errors: {result.get('total_errors', 0)}")

    if result.get('total_new', 0) < 20:
        print("\n⚠️  Low inventory detected.")
        print("   Consider expanding to nearby areas:")
        print("   - Ardmore, PA")
        print("   - Haverford, PA")
        print("   - Wayne, PA")


if __name__ == "__main__":
    main()
```

**Step 2: Commit**

```bash
git add scripts/__init__.py scripts/initial_scrape.py
git commit -m "feat: add initial scrape script for Bryn Mawr"
```

---

## Phase 7: Integration & Polish

### Task 7.1: Add Components to ApartmentCard

**Files:**
- Modify: `frontend/components/ApartmentCard.tsx`

**Step 1: Add FavoriteButton and CompareButton to ApartmentCard**

In the ApartmentCard component, add the buttons. Find the card header/actions area and add:

```typescript
import { FavoriteButton } from './FavoriteButton'
import { CompareButton } from './CompareButton'

// In the card JSX, add to the top-right corner or actions area:
<div className="absolute top-2 right-2 flex gap-2">
  <FavoriteButton apartmentId={apartment.id} />
</div>

// In the card footer/actions area:
<CompareButton apartmentId={apartment.id} />
```

**Step 2: Commit**

```bash
git add components/ApartmentCard.tsx
git commit -m "feat: add favorite and compare buttons to apartment cards"
```

---

### Task 7.2: Add ComparisonBar to Layout

**Files:**
- Modify: `frontend/app/layout.tsx`

**Step 1: Add ComparisonBar**

Add to `frontend/app/layout.tsx`:

```typescript
import { ComparisonBar } from '@/components/ComparisonBar'

// In the body, after children:
<body>
  <AuthProvider>
    {children}
    <ComparisonBar />
  </AuthProvider>
</body>
```

**Step 2: Commit**

```bash
git add app/layout.tsx
git commit -m "feat: add comparison bar to layout"
```

---

### Task 7.3: Add Header with Auth

**Files:**
- Create: `frontend/components/Header.tsx`
- Modify: `frontend/app/layout.tsx`

**Step 1: Create Header**

Create `frontend/components/Header.tsx`:

```typescript
'use client'
import Link from 'next/link'
import { AuthButton } from './AuthButton'
import { UserMenu } from './UserMenu'
import { useAuth } from '@/contexts/AuthContext'

export function Header() {
  const { user } = useAuth()

  return (
    <header className="border-b bg-white sticky top-0 z-40">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link href="/" className="text-xl font-bold text-blue-600">
          HomeScout
        </Link>

        <nav className="flex items-center gap-6">
          <Link href="/" className="text-gray-600 hover:text-gray-900">
            Search
          </Link>
          {user && (
            <>
              <Link href="/favorites" className="text-gray-600 hover:text-gray-900">
                Favorites
              </Link>
              <Link href="/searches" className="text-gray-600 hover:text-gray-900">
                Saved Searches
              </Link>
            </>
          )}
          <AuthButton />
          <UserMenu />
        </nav>
      </div>
    </header>
  )
}
```

**Step 2: Add to layout**

```typescript
import { Header } from '@/components/Header'

// In layout body:
<body>
  <AuthProvider>
    <Header />
    <main>{children}</main>
    <ComparisonBar />
  </AuthProvider>
</body>
```

**Step 3: Commit**

```bash
git add components/Header.tsx app/layout.tsx
git commit -m "feat: add header with navigation and auth"
```

---

## Verification Checklist

Before marking complete, verify:

- [ ] Supabase project created with OAuth configured
- [ ] All 4 tables created (profiles, favorites, saved_searches, notifications)
- [ ] Backend endpoints work: `/api/apartments/{id}`, `/batch`, `/compare`
- [ ] Webhook endpoint works with secret verification
- [ ] Frontend auth flow works (Google sign-in)
- [ ] Favorites can be added/removed with realtime sync
- [ ] Comparison works with up to 3 apartments
- [ ] Preference scoring works in comparison
- [ ] Data collection configured for Bryn Mawr
- [ ] Initial scrape populates apartments

---

## Post-Implementation

After completing all tasks:

1. Run full E2E test suite
2. Deploy to staging environment
3. Run initial scrape for Bryn Mawr
4. Test with real Apartments.com data
5. Set up Supabase Edge Functions for notifications (Phase 2)
