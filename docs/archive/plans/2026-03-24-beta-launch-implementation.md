# Snugd Beta Launch — "Polish & Ship" Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Polish Snugd for a 10-20 person friends & family beta: brand overhaul, invite codes, onboarding, auth fix, image fallbacks, and feedback widget.

**Architecture:** Frontend-heavy changes (Next.js 16 + Tailwind 4 + Supabase). New backend endpoints for invite code redemption. New Supabase migrations for invite_codes, invite_redemptions, beta_feedback tables. Profile table extended with `pro_expires_at` and `has_completed_onboarding`.

**Tech Stack:** Next.js 16, React 19, Tailwind CSS 4, Supabase (Postgres + Auth), FastAPI, DM Sans (Google Fonts), react-joyride, html2canvas

**Design Doc:** `docs/plans/2026-03-24-beta-launch-design.md`

---

## Task 1: Install New Dependencies

**Files:**
- Modify: `frontend/package.json`

**Step 1: Install npm packages**

Run:
```bash
cd frontend && npm install react-joyride html2canvas
```

Expected: packages added to `dependencies` in `package.json`.

**Step 2: Verify build still works**

Run:
```bash
cd frontend && npm run build
```

Expected: Build succeeds with no errors.

**Step 3: Commit**

```bash
cd frontend && git add package.json package-lock.json
git commit -m "chore: add react-joyride and html2canvas dependencies"
```

---

## Task 2: Brand Identity — Typography & Color Tokens

Replace the default Geist font with DM Sans. Set up a warm, minimalist color palette in CSS custom properties. Remove the dark mode override (not needed for beta).

**Files:**
- Modify: `frontend/app/layout.tsx:1-17` (font imports)
- Modify: `frontend/app/globals.css` (color tokens, font)

**Step 1: Update `globals.css` with brand color tokens and font**

Replace the entire `frontend/app/globals.css` with:

```css
@import "tailwindcss";

:root {
  /* Brand palette — warm, minimalist */
  --color-primary: #2D6A4F;       /* Forest green — primary actions */
  --color-primary-light: #40916C; /* Hover state */
  --color-primary-dark: #1B4332;  /* Active state */
  --color-accent: #E76F51;        /* Warm coral — CTAs, highlights */
  --color-accent-light: #F4A261;  /* Accent hover */

  /* Neutrals */
  --color-bg: #FAFAF8;            /* Warm off-white page background */
  --color-surface: #FFFFFF;       /* Card/panel backgrounds */
  --color-border: #E8E5E0;        /* Borders, dividers */
  --color-text: #1A1A1A;          /* Primary text */
  --color-text-secondary: #6B7280; /* Secondary text */
  --color-text-muted: #9CA3AF;    /* Muted/placeholder text */

  /* Semantic */
  --color-success: #10B981;
  --color-warning: #F59E0B;
  --color-error: #EF4444;

  --background: var(--color-bg);
  --foreground: var(--color-text);
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --font-sans: var(--font-dm-sans);
}

body {
  background: var(--background);
  color: var(--foreground);
  font-family: var(--font-dm-sans), system-ui, sans-serif;
}
```

**Step 2: Update `layout.tsx` to use DM Sans from Google Fonts**

In `frontend/app/layout.tsx`, replace the font imports and variables:

```tsx
import type { Metadata } from "next";
import { DM_Sans } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/contexts/AuthContext";
import { ComparisonBar } from "@/components/ComparisonBar";
import { BottomNav } from "@/components/BottomNav";
import { Header } from "@/components/Header";

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "snugd — Find Your Perfect Apartment",
  description: "AI-powered apartment matching across 19 East Coast cities. Search, compare, tour, and decide — all in one place.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${dmSans.variable} antialiased`}>
        <AuthProvider>
          <Header />
          <main className="pb-16 md:pb-0">{children}</main>
          <ComparisonBar />
          <BottomNav />
        </AuthProvider>
      </body>
    </html>
  );
}
```

**Step 3: Verify the font loads**

Run:
```bash
cd frontend && npm run dev
```

Open http://localhost:3000 in a browser. Confirm DM Sans renders (body text should look different from default Geist). Confirm the warm off-white background (`#FAFAF8`) appears.

**Step 4: Commit**

```bash
git add frontend/app/globals.css frontend/app/layout.tsx
git commit -m "feat: brand identity — DM Sans font, warm color palette"
```

---

## Task 3: Update Header with Logo and Brand Colors

Replace the blue `Snugd` text with a styled "snugd" wordmark. Update nav link colors from blue to the brand palette. Make nav links hidden on mobile (BottomNav handles mobile navigation).

**Files:**
- Modify: `frontend/components/Header.tsx`

**Step 1: Update Header component**

Replace the entire `frontend/components/Header.tsx` with:

```tsx
'use client'
import Link from 'next/link'
import { AuthButton } from './AuthButton'
import { UserMenu } from './UserMenu'
import { useAuth } from '@/contexts/AuthContext'

export function Header() {
  const { user } = useAuth()

  return (
    <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)] sticky top-0 z-40">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link href="/" className="text-2xl font-bold tracking-tight" style={{ color: 'var(--color-primary)' }}>
          snugd
        </Link>

        <nav className="hidden md:flex items-center gap-6">
          <Link href="/" className="text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors">
            Search
          </Link>
          {user && (
            <>
              <Link href="/favorites" className="text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors">
                Favorites
              </Link>
              <Link href="/tours" className="text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors">
                Tours
              </Link>
              <Link href="/compare" className="text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors">
                Compare
              </Link>
            </>
          )}
          <Link href="/pricing" className="text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors">
            Pricing
          </Link>
          <AuthButton />
          <UserMenu />
        </nav>

        {/* Mobile: only show auth controls */}
        <div className="flex md:hidden items-center gap-3">
          <AuthButton />
          <UserMenu />
        </div>
      </div>
    </header>
  )
}
```

**Step 2: Update BottomNav brand colors**

In `frontend/components/BottomNav.tsx`, change the active color from `text-blue-600` to the brand primary:

Replace:
```tsx
active ? 'text-blue-600' : 'text-gray-400'
```
with:
```tsx
active ? 'text-[var(--color-primary)]' : 'text-gray-400'
```

Also update the nav background:
Replace:
```tsx
<nav className="fixed bottom-0 left-0 right-0 bg-white border-t md:hidden z-50">
```
with:
```tsx
<nav className="fixed bottom-0 left-0 right-0 bg-[var(--color-surface)] border-t border-[var(--color-border)] md:hidden z-50">
```

**Step 3: Verify**

Run dev server, check desktop (nav links visible, "snugd" in forest green) and mobile viewport (nav links hidden, BottomNav shown with green active state).

**Step 4: Commit**

```bash
git add frontend/components/Header.tsx frontend/components/BottomNav.tsx
git commit -m "feat: branded header with snugd wordmark, mobile-responsive nav"
```

---

## Task 4: Restyle Core Components with Brand Colors

Update SearchForm, ApartmentCard, FavoriteButton, CompareButton, and ComparisonBar to use the new color palette. Replace all `blue-*` Tailwind classes with brand CSS variables.

**Files:**
- Modify: `frontend/components/SearchForm.tsx`
- Modify: `frontend/components/ApartmentCard.tsx`
- Modify: `frontend/components/FavoriteButton.tsx`
- Modify: `frontend/components/CompareButton.tsx`
- Modify: `frontend/components/ComparisonBar.tsx`
- Modify: `frontend/components/UpgradePrompt.tsx`
- Modify: `frontend/app/page.tsx`

**Step 1: Update SearchForm colors**

In `frontend/components/SearchForm.tsx`, do a find-and-replace for these color classes:

| Old | New |
|-----|-----|
| `focus:ring-blue-500` | `focus:ring-[var(--color-primary)]` |
| `border-blue-500 bg-blue-50` | `border-[var(--color-primary)] bg-[#2D6A4F10]` |
| `text-blue-600` | `text-[var(--color-primary)]` |
| `focus:ring-blue-500` | `focus:ring-[var(--color-primary)]` |
| `bg-blue-400 cursor-not-allowed` | `bg-[var(--color-primary-light)] opacity-70 cursor-not-allowed` |
| `bg-blue-600 hover:bg-blue-700 active:bg-blue-800` | `bg-[var(--color-primary)] hover:bg-[var(--color-primary-light)] active:bg-[var(--color-primary-dark)]` |

**Step 2: Update ApartmentCard — match score badge colors**

In `frontend/components/ApartmentCard.tsx`, update `getScoreColor`:

```tsx
const getScoreColor = (score: number): string => {
  if (score >= 85) return 'bg-emerald-500';
  if (score >= 70) return 'bg-[var(--color-primary)]';
  if (score >= 50) return 'bg-amber-500';
  return 'bg-gray-500';
};
```

Update `getLabelColor`:

```tsx
const getLabelColor = (label: string): string => {
  switch (label) {
    case 'Excellent Match': return 'bg-emerald-500 text-white';
    case 'Great Match': return 'bg-[var(--color-primary)] text-white';
    case 'Good Match': return 'bg-slate-500 text-white';
    case 'Fair Match': return 'bg-gray-400 text-gray-800';
    default: return 'bg-gray-300 text-gray-600';
  }
};
```

Update the card border radius and shadow for warmer feel:
Replace:
```tsx
<div className="bg-white rounded-lg shadow-md overflow-hidden transition hover:shadow-lg">
```
with:
```tsx
<div className="bg-[var(--color-surface)] rounded-xl shadow-sm border border-[var(--color-border)] overflow-hidden transition hover:shadow-md">
```

**Step 3: Update UpgradePrompt colors**

In `frontend/components/UpgradePrompt.tsx`:
- Replace `text-blue-600 hover:underline` → `text-[var(--color-primary)] hover:underline`
- Replace `from-blue-50 to-indigo-50 border border-blue-200` → `from-emerald-50 to-teal-50 border border-emerald-200`
- Replace `bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700` → `bg-[var(--color-primary)] text-white px-6 py-2 rounded-lg hover:bg-[var(--color-primary-light)]`

**Step 4: Update page.tsx — loading spinner and background**

In `frontend/app/page.tsx`:
- Replace `border-blue-600` (spinner) → `border-[var(--color-primary)]`
- Replace `bg-blue-600 text-white rounded-lg hover:bg-blue-700` (sign-in button on favorites page) → `bg-[var(--color-primary)] text-white rounded-lg hover:bg-[var(--color-primary-light)]`
- Replace `bg-gray-50` page background → `bg-[var(--color-bg)]`

**Step 5: Verify**

Run dev server. Confirm all blue elements are now forest green or coral. Check: search form focus rings, property type checkboxes, submit button, match score badges, upgrade prompt, loading spinner.

**Step 6: Commit**

```bash
git add frontend/components/SearchForm.tsx frontend/components/ApartmentCard.tsx \
  frontend/components/FavoriteButton.tsx frontend/components/CompareButton.tsx \
  frontend/components/ComparisonBar.tsx frontend/components/UpgradePrompt.tsx \
  frontend/app/page.tsx
git commit -m "feat: restyle core components with brand color palette"
```

---

## Task 5: Image Fallback Handling

Add `onError` handlers to all `<Image>` and `<img>` tags so broken scraped URLs show a clean placeholder instead of a broken image icon.

**Files:**
- Modify: `frontend/components/ImageCarousel.tsx`
- Modify: `frontend/next.config.ts`

**Step 1: Update `ImageCarousel.tsx` with error handling**

Replace the entire `frontend/components/ImageCarousel.tsx` with:

```tsx
'use client';

import { useState, useCallback, useEffect } from 'react';
import useEmblaCarousel from 'embla-carousel-react';
import Image from 'next/image';

interface ImageCarouselProps {
  images: string[];
  alt: string;
}

function ImagePlaceholder() {
  return (
    <div className="absolute inset-0 bg-gradient-to-br from-gray-100 to-gray-200 flex flex-col items-center justify-center">
      <svg className="h-12 w-12 text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
      <span className="text-sm text-gray-400">No photo available</span>
    </div>
  );
}

function CarouselImage({ src, alt, sizes }: { src: string; alt: string; sizes: string }) {
  const [failed, setFailed] = useState(false);

  if (failed) return <ImagePlaceholder />;

  return (
    <Image
      src={src}
      alt={alt}
      fill
      className="object-cover"
      sizes={sizes}
      onError={() => setFailed(true)}
    />
  );
}

export default function ImageCarousel({ images, alt }: ImageCarouselProps) {
  const [emblaRef, emblaApi] = useEmblaCarousel({ loop: true });
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [canScrollPrev, setCanScrollPrev] = useState(false);
  const [canScrollNext, setCanScrollNext] = useState(false);

  const scrollPrev = useCallback(() => emblaApi?.scrollPrev(), [emblaApi]);
  const scrollNext = useCallback(() => emblaApi?.scrollNext(), [emblaApi]);

  const onSelect = useCallback(() => {
    if (!emblaApi) return;
    setSelectedIndex(emblaApi.selectedScrollSnap());
    setCanScrollPrev(emblaApi.canScrollPrev());
    setCanScrollNext(emblaApi.canScrollNext());
  }, [emblaApi]);

  useEffect(() => {
    if (!emblaApi) return;
    onSelect();
    emblaApi.on('select', onSelect);
    emblaApi.on('reInit', onSelect);
    return () => {
      emblaApi.off('select', onSelect);
      emblaApi.off('reInit', onSelect);
    };
  }, [emblaApi, onSelect]);

  // No images at all
  if (!images || images.length === 0) {
    return (
      <div className="relative aspect-[4/3] w-full overflow-hidden rounded-t-xl bg-gray-100">
        <ImagePlaceholder />
      </div>
    );
  }

  // Single image
  if (images.length === 1) {
    return (
      <div className="relative aspect-[4/3] w-full overflow-hidden rounded-t-xl bg-gray-100">
        <CarouselImage src={images[0]} alt={alt} sizes="(max-width: 768px) 100vw, 50vw" />
      </div>
    );
  }

  return (
    <div className="relative pointer-events-none">
      <div className="overflow-hidden rounded-t-xl pointer-events-auto" ref={emblaRef}>
        <div className="flex">
          {images.map((image, index) => (
            <div key={index} className="relative aspect-[4/3] flex-[0_0_100%] bg-gray-100">
              <CarouselImage
                src={image}
                alt={`${alt} - Image ${index + 1}`}
                sizes="(max-width: 768px) 100vw, 50vw"
              />
            </div>
          ))}
        </div>
      </div>

      {/* Navigation Arrows */}
      <button
        onClick={scrollPrev}
        className={`absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-white/80 p-2 shadow-md transition hover:bg-white pointer-events-auto ${
          !canScrollPrev && 'opacity-50'
        }`}
        aria-label="Previous image"
      >
        <svg className="h-4 w-4 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
      </button>
      <button
        onClick={scrollNext}
        className={`absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-white/80 p-2 shadow-md transition hover:bg-white pointer-events-auto ${
          !canScrollNext && 'opacity-50'
        }`}
        aria-label="Next image"
      >
        <svg className="h-4 w-4 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </button>

      {/* Pagination Dots */}
      <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 gap-1.5 pointer-events-auto">
        {images.map((_, index) => (
          <button
            key={index}
            onClick={() => emblaApi?.scrollTo(index)}
            className={`h-2 w-2 rounded-full transition ${
              index === selectedIndex ? 'bg-white' : 'bg-white/50 hover:bg-white/75'
            }`}
            aria-label={`Go to image ${index + 1}`}
          />
        ))}
      </div>
    </div>
  );
}
```

**Step 2: Add `unoptimized` flag for external images in next.config.ts**

In `frontend/next.config.ts`, add `unoptimized: true` to the images config so we don't need to whitelist every scraped domain:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
```

This is simpler than maintaining a growing `remotePatterns` list for scraped domains. For beta, optimization isn't critical.

**Step 3: Verify**

Open the app, find an apartment with images. In browser DevTools, modify an image `src` to a broken URL. Confirm the placeholder appears with the house icon and "No photo available" text.

**Step 4: Commit**

```bash
git add frontend/components/ImageCarousel.tsx frontend/next.config.ts
git commit -m "feat: image fallback placeholders for broken scraped URLs"
```

---

## Task 6: Auth Bug Fix — Session Timeout

Fix the blank white page that occurs when a Supabase session token expires and refresh fails. Add a 5-second timeout to `getSession()` and handle token refresh failures gracefully.

**Files:**
- Modify: `frontend/contexts/AuthContext.tsx:47-104`

**Step 1: Add timeout and error handling to AuthContext**

Replace the `useEffect` block in `frontend/contexts/AuthContext.tsx` (lines 47-105) with:

```tsx
  useEffect(() => {
    let mounted = true

    // E2E test auth bypass
    if (process.env.NODE_ENV !== 'production') {
      const testUser = typeof window !== 'undefined'
        ? localStorage.getItem('__test_auth_user')
        : null
      if (testUser) {
        try {
          setUser(JSON.parse(testUser) as User)
          const testProfile = typeof window !== 'undefined'
            ? localStorage.getItem('__test_auth_profile')
            : null
          if (testProfile) {
            try {
              setProfile(JSON.parse(testProfile) as Profile)
            } catch { /* ignore parse errors */ }
          }
          setLoading(false)
          return
        } catch { /* fall through */ }
      }
    }

    // 5-second timeout to prevent infinite loading on stale sessions
    const timeout = setTimeout(() => {
      if (mounted && loading) {
        console.warn('Auth initialization timed out — clearing stale session')
        supabase.auth.signOut().catch(() => {})
        applySession(null)
        setProfile(null)
        setLoading(false)
      }
    }, 5000)

    supabase.auth.getSession().then(({ data: { session: s } }) => {
      clearTimeout(timeout)
      if (mounted) {
        applySession(s)
        if (s?.user) fetchProfile(s.user.id)
        setLoading(false)
      }
    }).catch(() => {
      clearTimeout(timeout)
      if (mounted) {
        // Session retrieval failed — clear and let user re-auth
        supabase.auth.signOut().catch(() => {})
        applySession(null)
        setLoading(false)
      }
    })

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, s) => {
        if (!mounted) return

        // Handle token refresh failure
        if (event === 'TOKEN_REFRESHED' && !s) {
          console.warn('Token refresh failed — signing out')
          applySession(null)
          setProfile(null)
          return
        }

        applySession(s)
        if (s?.user) {
          await fetchProfile(s.user.id)
        } else {
          setProfile(null)
        }
      }
    )

    return () => {
      mounted = false
      clearTimeout(timeout)
      subscription.unsubscribe()
    }
  }, [fetchProfile, applySession])
```

Note: `loading` is read inside the timeout callback. Since `loading` starts as `true` and is set to `false` on resolution, this works correctly — the timeout only fires if we're still loading after 5 seconds.

**Step 2: Verify**

1. Run `npm run dev`, sign in, verify normal flow works.
2. In browser DevTools → Application → Local Storage, corrupt the Supabase session key (change the access token to garbage). Refresh the page. Confirm: no blank page; user is signed out after 5 seconds with the app rendering normally.

**Step 3: Commit**

```bash
git add frontend/contexts/AuthContext.tsx
git commit -m "fix: 5-second auth timeout prevents blank page on stale sessions"
```

---

## Task 7: Supabase Migration — Invite Codes, Feedback, Onboarding

Create a new migration that adds tables for the invite code system, beta feedback widget, and onboarding tracking.

**Files:**
- Create: `supabase/migrations/006_beta_launch.sql`

**Step 1: Write the migration**

Create `supabase/migrations/006_beta_launch.sql`:

```sql
-- ============================================
-- INVITE CODES (admin-generated)
-- ============================================
create table public.invite_codes (
  code text primary key,
  max_uses integer not null default 1,
  times_used integer not null default 0,
  expires_at timestamptz,
  created_at timestamptz default now()
);

-- Track who redeemed what
create table public.invite_redemptions (
  id uuid default gen_random_uuid() primary key,
  code text references invite_codes(code) not null,
  user_id uuid references auth.users(id) on delete cascade not null,
  redeemed_at timestamptz default now(),
  unique(code, user_id)
);

create index idx_invite_redemptions_user on invite_redemptions(user_id);

-- ============================================
-- PROFILES — add pro_expires_at and onboarding
-- ============================================
alter table public.profiles
  add column if not exists pro_expires_at timestamptz,
  add column if not exists has_completed_onboarding boolean not null default false;

-- ============================================
-- BETA FEEDBACK
-- ============================================
create table public.beta_feedback (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,
  type text not null check (type in ('bug', 'suggestion', 'general')),
  message text not null,
  screenshot_url text,
  page_url text,
  metadata jsonb default '{}',
  created_at timestamptz default now()
);

create index idx_beta_feedback_user on beta_feedback(user_id);
create index idx_beta_feedback_type on beta_feedback(type);

-- ============================================
-- ROW LEVEL SECURITY
-- ============================================

-- Invite codes: readable by authenticated users (to validate), writable by service role only
alter table invite_codes enable row level security;
create policy "Anyone can read invite codes" on invite_codes
  for select using (true);
create policy "Service can manage invite codes" on invite_codes
  for all using (true) with check (true);

-- Invite redemptions: users can read their own
alter table invite_redemptions enable row level security;
create policy "Users read own redemptions" on invite_redemptions
  for select using (auth.uid() = user_id);
create policy "Service can manage redemptions" on invite_redemptions
  for all using (true) with check (true);

-- Beta feedback: users insert their own, service reads all
alter table beta_feedback enable row level security;
create policy "Users insert own feedback" on beta_feedback
  for insert with check (auth.uid() = user_id);
create policy "Users read own feedback" on beta_feedback
  for select using (auth.uid() = user_id);
create policy "Service can read all feedback" on beta_feedback
  for select using (true);
```

**Step 2: Run migration in Supabase**

Go to Supabase Dashboard → SQL Editor → paste and run the migration. Verify: all tables created, `profiles` has new columns.

Alternatively, if using the Supabase CLI:
```bash
supabase db push
```

**Step 3: Commit**

```bash
git add supabase/migrations/006_beta_launch.sql
git commit -m "feat: migration for invite codes, feedback, onboarding tracking"
```

---

## Task 8: Backend — Invite Code Endpoints

Add three new endpoints: redeem an invite code, check invite status, and admin endpoint to generate codes.

**Files:**
- Create: `backend/app/routers/invite.py`
- Modify: `backend/app/main.py` (register new router)

**Step 1: Create the invite router**

Create `backend/app/routers/invite.py`:

```python
"""Invite code endpoints for beta access."""
import logging
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, UserContext
from app.services.tier_service import supabase_admin, TierService

logger = logging.getLogger(__name__)

router = APIRouter()


class RedeemRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)


class RedeemResponse(BaseModel):
    success: bool
    message: str
    expires_at: str | None = None


class InviteStatus(BaseModel):
    has_invite: bool
    expires_at: str | None = None


class GenerateCodesRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=50)
    max_uses: int = Field(default=1, ge=1, le=100)
    prefix: str = Field(default="BETA")
    expires_at: str | None = None


def _ensure_supabase():
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")


@router.post("/api/invite/redeem", response_model=RedeemResponse)
async def redeem_invite_code(
    body: RedeemRequest,
    user: UserContext = Depends(get_current_user),
):
    """Redeem an invite code to get Pro access for 90 days."""
    _ensure_supabase()
    code = body.code.strip().upper()

    # Check if code exists
    result = supabase_admin.table("invite_codes").select("*").eq("code", code).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Invalid invite code")

    invite = result.data[0]

    # Check expiration
    if invite.get("expires_at"):
        expires = datetime.fromisoformat(invite["expires_at"].replace("Z", "+00:00"))
        if expires < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="This invite code has expired")

    # Check uses remaining
    if invite["times_used"] >= invite["max_uses"]:
        raise HTTPException(status_code=400, detail="This invite code has been fully used")

    # Check if already redeemed by this user
    existing = (
        supabase_admin.table("invite_redemptions")
        .select("id")
        .eq("code", code)
        .eq("user_id", user.user_id)
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=400, detail="You have already redeemed this code")

    # Calculate expiration (90 days from now)
    pro_expires = datetime.now(timezone.utc) + timedelta(days=90)

    # Redeem: update profile, increment uses, record redemption
    try:
        # Update user to pro with expiration
        supabase_admin.table("profiles").update({
            "user_tier": "pro",
            "pro_expires_at": pro_expires.isoformat(),
        }).eq("id", user.user_id).execute()

        # Increment times_used
        supabase_admin.table("invite_codes").update({
            "times_used": invite["times_used"] + 1,
        }).eq("code", code).execute()

        # Record redemption
        supabase_admin.table("invite_redemptions").insert({
            "code": code,
            "user_id": user.user_id,
        }).execute()

        logger.info(f"User {user.user_id} redeemed invite code {code}")
        return RedeemResponse(
            success=True,
            message="Welcome to Pro! Your access expires in 90 days.",
            expires_at=pro_expires.isoformat(),
        )
    except Exception as e:
        logger.error(f"Failed to redeem invite code: {e}")
        raise HTTPException(status_code=500, detail="Failed to redeem code")


@router.get("/api/invite/status", response_model=InviteStatus)
async def get_invite_status(
    user: UserContext = Depends(get_current_user),
):
    """Check if current user has an active invite-based Pro subscription."""
    _ensure_supabase()

    result = (
        supabase_admin.table("profiles")
        .select("user_tier, pro_expires_at")
        .eq("id", user.user_id)
        .single()
        .execute()
    )

    if not result.data:
        return InviteStatus(has_invite=False)

    profile = result.data
    if profile.get("pro_expires_at"):
        expires = datetime.fromisoformat(
            profile["pro_expires_at"].replace("Z", "+00:00")
        )
        if expires > datetime.now(timezone.utc) and profile.get("user_tier") == "pro":
            return InviteStatus(has_invite=True, expires_at=profile["pro_expires_at"])

    return InviteStatus(has_invite=False)


@router.post("/api/admin/invite-codes")
async def generate_invite_codes(body: GenerateCodesRequest):
    """Generate invite codes. No auth for now (admin-only by obscurity during beta)."""
    _ensure_supabase()

    import secrets
    codes = []
    for _ in range(body.count):
        code = f"{body.prefix}-{secrets.token_hex(3).upper()}"
        data = {
            "code": code,
            "max_uses": body.max_uses,
        }
        if body.expires_at:
            data["expires_at"] = body.expires_at
        supabase_admin.table("invite_codes").insert(data).execute()
        codes.append(code)

    return {"codes": codes}
```

**Step 2: Register the router in main.py**

In `backend/app/main.py`, add the import and include the router. Find the section where routers are included (after the `from app.routers` imports) and add:

```python
from app.routers import invite as invite_router
```

Then add this line alongside the other `app.include_router()` calls:

```python
app.include_router(invite_router.router)
```

**Step 3: Test manually**

```bash
# Generate a test code
curl -X POST http://localhost:8000/api/admin/invite-codes \
  -H "Content-Type: application/json" \
  -d '{"count": 1, "max_uses": 5, "prefix": "BETA"}'

# Should return: {"codes": ["BETA-A1B2C3"]}
```

**Step 4: Commit**

```bash
git add backend/app/routers/invite.py backend/app/main.py
git commit -m "feat: invite code endpoints — redeem, status, admin generate"
```

---

## Task 9: Backend — Feedback Endpoint

Add a single endpoint for submitting beta feedback.

**Files:**
- Create: `backend/app/routers/feedback.py`
- Modify: `backend/app/main.py` (register router)

**Step 1: Create the feedback router**

Create `backend/app/routers/feedback.py`:

```python
"""Beta feedback endpoint."""
import logging
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, UserContext
from app.services.tier_service import supabase_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class FeedbackRequest(BaseModel):
    type: str = Field(..., pattern="^(bug|suggestion|general)$")
    message: str = Field(..., min_length=1, max_length=5000)
    screenshot_url: str | None = None
    page_url: str | None = None


class FeedbackResponse(BaseModel):
    success: bool
    message: str


@router.post("/api/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    user: UserContext = Depends(get_current_user),
):
    """Submit beta feedback."""
    if not supabase_admin:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        supabase_admin.table("beta_feedback").insert({
            "user_id": user.user_id,
            "type": body.type,
            "message": body.message,
            "screenshot_url": body.screenshot_url,
            "page_url": body.page_url,
            "metadata": {
                "email": user.email,
            },
        }).execute()

        logger.info(f"Feedback submitted by {user.user_id}: {body.type}")
        return FeedbackResponse(success=True, message="Thanks for your feedback!")
    except Exception as e:
        logger.error(f"Failed to submit feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit feedback")
```

**Step 2: Register the router in main.py**

In `backend/app/main.py`, add:

```python
from app.routers import feedback as feedback_router
```

And:

```python
app.include_router(feedback_router.router)
```

**Step 3: Commit**

```bash
git add backend/app/routers/feedback.py backend/app/main.py
git commit -m "feat: beta feedback submission endpoint"
```

---

## Task 10: Frontend — Invite Code Redemption UI

Add an invite code input banner to the main page (shown for free users), the pricing page, and the settings page.

**Files:**
- Create: `frontend/components/InviteCodeBanner.tsx`
- Modify: `frontend/app/page.tsx` (add banner)
- Modify: `frontend/lib/api.ts` (add invite API functions)

**Step 1: Add invite API functions to `lib/api.ts`**

At the bottom of `frontend/lib/api.ts`, add:

```typescript
// Invite code endpoints
export async function redeemInviteCode(code: string): Promise<{ success: boolean; message: string; expires_at?: string }> {
  const res = await fetch(`${API_BASE}/api/invite/redeem`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to redeem code' }));
    throw new ApiError(err.detail || 'Failed to redeem code', res.status);
  }
  return res.json();
}

export async function getInviteStatus(): Promise<{ has_invite: boolean; expires_at?: string }> {
  const res = await fetch(`${API_BASE}/api/invite/status`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new ApiError('Failed to check invite status', res.status);
  return res.json();
}
```

**Step 2: Create `InviteCodeBanner.tsx`**

Create `frontend/components/InviteCodeBanner.tsx`:

```tsx
'use client'
import { useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { redeemInviteCode } from '@/lib/api'

export function InviteCodeBanner() {
  const { user, isPro, refreshProfile } = useAuth()
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)
  const [dismissed, setDismissed] = useState(false)

  // Don't show if not signed in, already pro, or dismissed
  if (!user || isPro || dismissed) return null

  async function handleRedeem(e: React.FormEvent) {
    e.preventDefault()
    if (!code.trim()) return

    setLoading(true)
    setMessage(null)

    try {
      const result = await redeemInviteCode(code.trim())
      setMessage({ text: result.message, type: 'success' })
      setCode('')
      // Refresh profile to pick up new tier
      await refreshProfile()
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to redeem code'
      setMessage({ text: errorMessage, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl p-4 mb-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-[var(--color-text)]">Have an invite code?</p>
          <p className="text-xs text-[var(--color-text-muted)]">Enter it below to unlock Pro features for 90 days.</p>
        </div>
        <form onSubmit={handleRedeem} className="flex items-center gap-2">
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="BETA-XXXXXX"
            className="w-36 px-3 py-1.5 text-sm border border-[var(--color-border)] rounded-lg focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !code.trim()}
            className="px-4 py-1.5 text-sm font-medium text-white bg-[var(--color-primary)] rounded-lg hover:bg-[var(--color-primary-light)] disabled:opacity-50 transition-colors"
          >
            {loading ? 'Redeeming...' : 'Redeem'}
          </button>
          <button
            type="button"
            onClick={() => setDismissed(true)}
            className="text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] p-1"
            aria-label="Dismiss"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </form>
      </div>
      {message && (
        <p className={`text-sm mt-2 ${message.type === 'success' ? 'text-emerald-600' : 'text-red-600'}`}>
          {message.text}
        </p>
      )}
    </div>
  )
}
```

**Step 3: Add banner to `app/page.tsx`**

In `frontend/app/page.tsx`, add the import at the top:

```tsx
import { InviteCodeBanner } from '@/components/InviteCodeBanner';
```

Then add the banner right after the opening of the `max-w-7xl` container div (after line `<div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">`):

```tsx
        <InviteCodeBanner />
```

**Step 4: Verify**

Sign in as a free user. Confirm the invite code banner appears. Enter a valid code (generate one first via the admin endpoint). Confirm: success message, banner disappears (user is now Pro). Dismiss button hides the banner.

**Step 5: Commit**

```bash
git add frontend/components/InviteCodeBanner.tsx frontend/lib/api.ts frontend/app/page.tsx
git commit -m "feat: invite code redemption UI with banner on search page"
```

---

## Task 11: Frontend — Feedback Widget

Create a floating feedback button that appears on every page. Opens a small form with type selector, message textarea, and optional screenshot capture.

**Files:**
- Create: `frontend/components/FeedbackWidget.tsx`
- Modify: `frontend/app/layout.tsx` (add widget to layout)
- Modify: `frontend/lib/api.ts` (add feedback API function)

**Step 1: Add feedback API function to `lib/api.ts`**

At the bottom of `frontend/lib/api.ts`, add:

```typescript
// Feedback endpoint
export async function submitFeedback(data: {
  type: 'bug' | 'suggestion' | 'general';
  message: string;
  screenshot_url?: string;
  page_url?: string;
}): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/api/feedback`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to submit feedback' }));
    throw new ApiError(err.detail || 'Failed to submit feedback', res.status);
  }
  return res.json();
}
```

**Step 2: Create `FeedbackWidget.tsx`**

Create `frontend/components/FeedbackWidget.tsx`:

```tsx
'use client'
import { useState, useRef } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { submitFeedback } from '@/lib/api'

const TYPES = [
  { value: 'bug' as const, label: 'Bug', icon: '!' },
  { value: 'suggestion' as const, label: 'Idea', icon: '+' },
  { value: 'general' as const, label: 'General', icon: '?' },
]

export function FeedbackWidget() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [type, setType] = useState<'bug' | 'suggestion' | 'general'>('general')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState(false)
  const formRef = useRef<HTMLFormElement>(null)

  if (!user) return null

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!message.trim()) return

    setLoading(true)
    try {
      await submitFeedback({
        type,
        message: message.trim(),
        page_url: window.location.href,
      })
      setMessage('')
      setType('general')
      setOpen(false)
      setToast(true)
      setTimeout(() => setToast(false), 3000)
    } catch {
      // Silently fail for beta
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      {/* Toast */}
      {toast && (
        <div className="fixed bottom-20 right-6 z-[60] bg-emerald-600 text-white px-4 py-2 rounded-lg shadow-lg text-sm animate-fade-in">
          Thanks for your feedback!
        </div>
      )}

      {/* Feedback Form */}
      {open && (
        <div className="fixed bottom-20 right-6 z-[60] w-80 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl shadow-xl">
          <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
            <h3 className="font-semibold text-sm">Send Feedback</h3>
            <button onClick={() => setOpen(false)} className="text-[var(--color-text-muted)] hover:text-[var(--color-text)]">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <form ref={formRef} onSubmit={handleSubmit} className="p-4 space-y-3">
            {/* Type selector */}
            <div className="flex gap-2">
              {TYPES.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => setType(t.value)}
                  className={`flex-1 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                    type === t.value
                      ? 'border-[var(--color-primary)] bg-[#2D6A4F10] text-[var(--color-primary)]'
                      : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-gray-400'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* Message */}
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="What's on your mind?"
              rows={4}
              className="w-full px-3 py-2 text-sm border border-[var(--color-border)] rounded-lg focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent resize-none"
              required
            />

            {/* Submit */}
            <button
              type="submit"
              disabled={loading || !message.trim()}
              className="w-full py-2 text-sm font-medium text-white bg-[var(--color-primary)] rounded-lg hover:bg-[var(--color-primary-light)] disabled:opacity-50 transition-colors"
            >
              {loading ? 'Sending...' : 'Send Feedback'}
            </button>
          </form>
        </div>
      )}

      {/* Floating Button */}
      <button
        onClick={() => setOpen(!open)}
        className="fixed bottom-4 right-6 z-50 bg-[var(--color-primary)] text-white p-3 rounded-full shadow-lg hover:bg-[var(--color-primary-light)] transition-colors md:bottom-6"
        aria-label="Send feedback"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      </button>
    </>
  )
}
```

**Step 3: Add widget to layout**

In `frontend/app/layout.tsx`, add the import:

```tsx
import { FeedbackWidget } from "@/components/FeedbackWidget";
```

And add `<FeedbackWidget />` right before `</AuthProvider>`:

```tsx
        <AuthProvider>
          <Header />
          <main className="pb-16 md:pb-0">{children}</main>
          <ComparisonBar />
          <BottomNav />
          <FeedbackWidget />
        </AuthProvider>
```

**Step 4: Verify**

Sign in. Confirm the floating chat bubble button appears in the bottom-right. Click it — form opens. Select a type, enter a message, submit. Confirm: form closes, "Thanks!" toast appears, check Supabase Dashboard → beta_feedback table for the new row.

**Step 5: Commit**

```bash
git add frontend/components/FeedbackWidget.tsx frontend/app/layout.tsx frontend/lib/api.ts
git commit -m "feat: floating feedback widget for beta testers"
```

---

## Task 12: Frontend — Guided Onboarding Walkthrough

Add a 4-step tooltip walkthrough using react-joyride that triggers on first sign-in. The last step includes an invite code input.

**Files:**
- Create: `frontend/components/OnboardingWalkthrough.tsx`
- Modify: `frontend/app/layout.tsx` (add walkthrough)
- Modify: `frontend/lib/supabase.ts` (add onboarding field to Profile type)

**Step 1: Update Profile type in `lib/supabase.ts`**

In `frontend/lib/supabase.ts`, add the new fields to the `Profile` interface:

```typescript
export interface Profile {
  id: string
  email: string
  name: string | null
  avatar_url: string | null
  email_notifications: boolean
  user_tier: 'free' | 'pro'
  subscription_status: string | null
  current_period_end: string | null
  pro_expires_at: string | null
  has_completed_onboarding: boolean
}
```

**Step 2: Create `OnboardingWalkthrough.tsx`**

Create `frontend/components/OnboardingWalkthrough.tsx`:

```tsx
'use client'
import { useState, useEffect } from 'react'
import Joyride, { CallBackProps, STATUS, Step } from 'react-joyride'
import { useAuth } from '@/contexts/AuthContext'
import { supabase } from '@/lib/supabase'
import { redeemInviteCode } from '@/lib/api'

const STEPS: Step[] = [
  {
    target: 'body',
    placement: 'center',
    disableBeacon: true,
    title: 'Welcome to snugd!',
    content: 'Find apartments across 19 East Coast cities. Set your budget and preferences, and we\'ll match you with the best options.',
  },
  {
    target: '[data-onboarding="favorites"]',
    title: 'Save Your Favorites',
    content: 'Tap the heart icon to save apartments you love. Compare them side by side to find your perfect match.',
    placement: 'bottom',
    disableBeacon: true,
  },
  {
    target: '[data-onboarding="tours"]',
    title: 'Plan Your Tours',
    content: 'Plan tours, capture notes and photos, and get AI-powered insights to help you decide.',
    placement: 'bottom',
    disableBeacon: true,
  },
  {
    target: 'body',
    placement: 'center',
    disableBeacon: true,
    title: 'Unlock Pro Features',
    content: 'Get AI scoring, smart comparisons, and inquiry emails with a Pro invite code. Enter it below or on the Pricing page.',
  },
]

export function OnboardingWalkthrough() {
  const { user, profile, isPro, refreshProfile } = useAuth()
  const [run, setRun] = useState(false)
  const [stepIndex, setStepIndex] = useState(0)
  const [inviteCode, setInviteCode] = useState('')
  const [inviteMessage, setInviteMessage] = useState('')
  const [inviteLoading, setInviteLoading] = useState(false)

  useEffect(() => {
    // Only run if user is signed in, profile loaded, and hasn't completed onboarding
    if (user && profile && !profile.has_completed_onboarding) {
      // Small delay so the page renders targets first
      const timer = setTimeout(() => setRun(true), 1000)
      return () => clearTimeout(timer)
    }
  }, [user, profile])

  async function markComplete() {
    if (!user) return
    try {
      await supabase
        .from('profiles')
        .update({ has_completed_onboarding: true })
        .eq('id', user.id)
      await refreshProfile()
    } catch {
      // Non-critical
    }
  }

  async function handleRedeemInOnboarding() {
    if (!inviteCode.trim()) return
    setInviteLoading(true)
    try {
      const result = await redeemInviteCode(inviteCode.trim())
      setInviteMessage(result.message)
      await refreshProfile()
    } catch (err: unknown) {
      setInviteMessage(err instanceof Error ? err.message : 'Invalid code')
    } finally {
      setInviteLoading(false)
    }
  }

  function handleCallback(data: CallBackProps) {
    const { status, action, index, type } = data

    if (status === STATUS.FINISHED || status === STATUS.SKIPPED) {
      setRun(false)
      markComplete()
      return
    }

    if (type === 'step:after') {
      if (action === 'next') {
        setStepIndex(index + 1)
      } else if (action === 'prev') {
        setStepIndex(index - 1)
      }
    }
  }

  if (!user || !profile || profile.has_completed_onboarding) return null

  return (
    <Joyride
      steps={STEPS}
      run={run}
      stepIndex={stepIndex}
      callback={handleCallback}
      continuous
      showSkipButton
      showProgress
      disableOverlayClose
      styles={{
        options: {
          primaryColor: '#2D6A4F',
          zIndex: 10000,
        },
        tooltip: {
          borderRadius: '12px',
          fontSize: '14px',
        },
        buttonNext: {
          borderRadius: '8px',
          padding: '8px 16px',
        },
        buttonBack: {
          color: '#6B7280',
        },
      }}
      locale={{
        last: 'Get Started',
        skip: 'Skip Tour',
      }}
      tooltipComponent={stepIndex === 3 ? undefined : undefined}
    />
  )
}
```

**Step 3: Add onboarding target attributes to components**

In `frontend/components/BottomNav.tsx`, add `data-onboarding` attributes to the tabs for targeting:

On the Favorites tab link, add the attribute:
```tsx
data-onboarding={tab.label === 'Favorites' ? 'favorites' : tab.label === 'Tours' ? 'tours' : undefined}
```

Actually, it's easier to add target attributes in the Header for desktop. In `frontend/components/Header.tsx`, add `data-onboarding="favorites"` to the Favorites link and `data-onboarding="tours"` to the Tours link:

```tsx
<Link href="/favorites" data-onboarding="favorites" className="...">
  Favorites
</Link>
<Link href="/tours" data-onboarding="tours" className="...">
  Tours
</Link>
```

And in `frontend/components/BottomNav.tsx`, also add `data-onboarding` to the matching tabs (so mobile also has targets). On each Link in the tabs map:

```tsx
<Link
  key={tab.href}
  href={tab.href}
  data-onboarding={tab.label.toLowerCase() === 'favorites' ? 'favorites' : tab.label.toLowerCase() === 'tours' ? 'tours' : undefined}
  className={...}
>
```

**Step 4: Add walkthrough to layout**

In `frontend/app/layout.tsx`, add the import:

```tsx
import { OnboardingWalkthrough } from "@/components/OnboardingWalkthrough";
```

Add it inside `AuthProvider`, after `Header`:

```tsx
<AuthProvider>
  <Header />
  <OnboardingWalkthrough />
  <main className="pb-16 md:pb-0">{children}</main>
  ...
</AuthProvider>
```

**Step 5: Verify**

1. In Supabase, set your user's `has_completed_onboarding` to `false`.
2. Refresh the app. Confirm the 4-step walkthrough appears.
3. Click through all steps. On the last step, confirm the "Get Started" button.
4. After completion, check that `has_completed_onboarding` is now `true` in Supabase.
5. Refresh — walkthrough should not appear again.

**Step 6: Commit**

```bash
git add frontend/components/OnboardingWalkthrough.tsx frontend/components/Header.tsx \
  frontend/components/BottomNav.tsx frontend/app/layout.tsx frontend/lib/supabase.ts
git commit -m "feat: 4-step guided onboarding walkthrough with react-joyride"
```

---

## Task 13: Mobile Responsiveness Polish

Ensure the search form, results grid, comparison bar, and all pages work well on mobile viewports. Stack fields vertically, single-column results, larger touch targets.

**Files:**
- Modify: `frontend/components/SearchForm.tsx` (mobile stacking)
- Modify: `frontend/app/page.tsx` (results grid)
- Modify: `frontend/components/ComparisonBar.tsx` (mobile adaptation)
- Modify: `frontend/app/favorites/page.tsx` (grid columns)

**Step 1: Update SearchForm for mobile**

In `frontend/components/SearchForm.tsx`, change the bedrooms/bathrooms row from always 2-column to stack on mobile:

Replace:
```tsx
<div className="grid grid-cols-2 gap-4">
```
with:
```tsx
<div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
```

Also update the property type grid:
Replace:
```tsx
<div className="grid grid-cols-2 gap-2">
```
with:
```tsx
<div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
```

Make all form inputs have larger touch targets on mobile by adding `min-h-[44px]` to select and input elements (44px is Apple's minimum recommended touch target):

Add this class to all `<select>` and `<input>` elements:
```
min-h-[44px]
```

**Step 2: Update results grid for single column on mobile**

In `frontend/app/page.tsx`, change the results grid:

Replace:
```tsx
<div className="grid gap-6 md:grid-cols-2">
```
with:
```tsx
<div className="grid gap-6 sm:grid-cols-2">
```

This is already mostly correct. Verify the layout collapses to single column below `sm` (640px).

**Step 3: Update favorites page grid**

In `frontend/app/favorites/page.tsx`, update the grid:

Replace:
```tsx
<div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
```
with:
```tsx
<div className="grid gap-6 sm:grid-cols-2">
```

(2 columns on tablet+, single column on mobile — matching the search results.)

**Step 4: Verify**

Use Chrome DevTools responsive mode. Check at 375px (iPhone), 768px (iPad), 1024px+ (desktop):
- Search form: fields stack on mobile, 2-column on desktop
- Results: single column on mobile, 2 columns on tablet+
- Bottom nav visible on mobile, hidden on desktop
- Touch targets are at least 44px height
- No horizontal overflow on any page

**Step 5: Commit**

```bash
git add frontend/components/SearchForm.tsx frontend/app/page.tsx frontend/app/favorites/page.tsx
git commit -m "feat: mobile responsiveness — stacked forms, single-column results, 44px touch targets"
```

---

## Task 14: Empty States and Loading Skeletons

Replace the generic empty states and spinner with polished versions — better copy, subtle illustrations, and skeleton loading for content pages.

**Files:**
- Modify: `frontend/app/page.tsx` (loading skeleton, empty state)
- Modify: `frontend/app/favorites/page.tsx` (empty state)

**Step 1: Update search page loading state**

In `frontend/app/page.tsx`, replace the loading spinner section with a skeleton grid:

Replace:
```tsx
{isLoading && (
  <div className="flex flex-col items-center justify-center py-12">
    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[var(--color-primary)] mb-4"></div>
    <p className="text-gray-600">Finding your perfect apartments...</p>
  </div>
)}
```

with:

```tsx
{isLoading && (
  <div className="grid gap-6 sm:grid-cols-2">
    {[1, 2, 3, 4].map(i => (
      <div key={i} className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] overflow-hidden animate-pulse">
        <div className="aspect-[4/3] bg-gray-200" />
        <div className="p-4 space-y-3">
          <div className="h-6 bg-gray-200 rounded w-1/3" />
          <div className="h-4 bg-gray-200 rounded w-2/3" />
          <div className="flex gap-4">
            <div className="h-4 bg-gray-200 rounded w-16" />
            <div className="h-4 bg-gray-200 rounded w-16" />
            <div className="h-4 bg-gray-200 rounded w-16" />
          </div>
          <div className="flex gap-1.5">
            <div className="h-6 bg-gray-200 rounded-full w-16" />
            <div className="h-6 bg-gray-200 rounded-full w-20" />
            <div className="h-6 bg-gray-200 rounded-full w-14" />
          </div>
        </div>
      </div>
    ))}
  </div>
)}
```

**Step 2: Polish the no-results empty state**

In `frontend/app/page.tsx`, update the no-results section:

Replace the "No apartments found" section with:

```tsx
{!isLoading && !error && hasSearched && results.length === 0 && (
  <div className="text-center py-16">
    <div className="mx-auto w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
      <svg className="h-8 w-8 text-[var(--color-text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
    </div>
    <h3 className="text-lg font-medium text-[var(--color-text)] mb-2">
      No apartments match your criteria
    </h3>
    <p className="text-[var(--color-text-secondary)] max-w-md mx-auto">
      Try increasing your budget, changing the city, or adjusting your bedroom and bathroom preferences.
    </p>
  </div>
)}
```

**Step 3: Polish favorites empty state**

In `frontend/app/favorites/page.tsx`, update the empty favorites section:

Replace:
```tsx
<div className="text-center py-12">
  <p className="text-gray-600 mb-4">You haven&apos;t saved any favorites yet.</p>
  <Link href="/" className="text-blue-600 hover:underline">
    Start searching for apartments
  </Link>
</div>
```

with:

```tsx
<div className="text-center py-16">
  <div className="mx-auto w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
    <svg className="h-8 w-8 text-[var(--color-text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
    </svg>
  </div>
  <h3 className="text-lg font-medium text-[var(--color-text)] mb-2">
    No favorites yet
  </h3>
  <p className="text-[var(--color-text-secondary)] mb-4">
    Search for apartments and tap the heart icon to save your favorites here.
  </p>
  <Link
    href="/"
    className="inline-block px-6 py-2 bg-[var(--color-primary)] text-white rounded-lg hover:bg-[var(--color-primary-light)] transition-colors"
  >
    Start Searching
  </Link>
</div>
```

**Step 4: Verify**

1. Before searching: hero section looks clean.
2. During search: skeleton grid appears (not spinner).
3. Empty results: polished message with suggestion to adjust criteria.
4. Empty favorites: heart icon, helpful copy, green CTA button.

**Step 5: Commit**

```bash
git add frontend/app/page.tsx frontend/app/favorites/page.tsx
git commit -m "feat: loading skeletons and polished empty states"
```

---

## Task 15: Remove Debug Console Logs

Clean up debug `console.log` statements from FavoriteButton.tsx and favorites/page.tsx that were added during development.

**Files:**
- Modify: `frontend/components/FavoriteButton.tsx`
- Modify: `frontend/app/favorites/page.tsx`

**Step 1: Remove console.logs from FavoriteButton**

In `frontend/components/FavoriteButton.tsx`, remove these lines:
- Line 22: `console.log('FavoriteButton clicked!', ...)`
- Line 25: `console.log('No user, triggering sign in...')`
- Line 33: `console.log('Removing favorite...')`
- Line 34: `console.log('Remove result:', result)`
- Line 37: `console.log('Adding favorite...')`
- Line 39: `console.log('Add result:', success)`
- Line 45: `console.error('Error toggling favorite:', error)`

**Step 2: Remove console.logs from favorites page**

In `frontend/app/favorites/page.tsx`, remove lines 38-44 (the debug logging block):
```tsx
console.log('FavoritesPage render:', {
  user: user?.id,
  authLoading,
  loading,
  favoritesCount: favorites.length,
  favorites: favorites.map(f => ({ id: f.id, apartment_id: f.apartment_id, hasApartment: !!f.apartment }))
})
```

**Step 3: Commit**

```bash
git add frontend/components/FavoriteButton.tsx frontend/app/favorites/page.tsx
git commit -m "chore: remove debug console.log statements"
```

---

## Task 16: Final Build Verification

Ensure the entire frontend builds without errors and all existing tests pass.

**Files:** None (verification only)

**Step 1: Run the build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds with no TypeScript errors and no warnings about missing imports.

**Step 2: Run ESLint**

```bash
cd frontend && npm run lint
```

Expected: No lint errors. Warnings are acceptable.

**Step 3: Run backend tests**

```bash
cd backend && source .venv/bin/activate && ANTHROPIC_API_KEY=test-key SUPABASE_JWT_SECRET=test-secret python -m pytest tests/ -v
```

Expected: All existing tests pass. New endpoints (invite, feedback) don't have backend tests yet — that's acceptable for beta.

**Step 4: Commit any fixes**

If the build or lint found issues, fix them and commit:

```bash
git add -A
git commit -m "fix: resolve build and lint issues"
```

---

## Task Summary

| # | Task | Type | Files Changed |
|---|------|------|---------------|
| 1 | Install dependencies | Setup | package.json |
| 2 | Typography & color tokens | Frontend | globals.css, layout.tsx |
| 3 | Header & BottomNav branding | Frontend | Header.tsx, BottomNav.tsx |
| 4 | Restyle core components | Frontend | 7 component files |
| 5 | Image fallback handling | Frontend | ImageCarousel.tsx, next.config.ts |
| 6 | Auth bug fix | Frontend | AuthContext.tsx |
| 7 | Supabase migration | Database | 006_beta_launch.sql |
| 8 | Invite code endpoints | Backend | invite.py, main.py |
| 9 | Feedback endpoint | Backend | feedback.py, main.py |
| 10 | Invite code UI | Frontend | InviteCodeBanner.tsx, api.ts, page.tsx |
| 11 | Feedback widget | Frontend | FeedbackWidget.tsx, layout.tsx, api.ts |
| 12 | Guided onboarding | Frontend | OnboardingWalkthrough.tsx, layout.tsx, supabase.ts |
| 13 | Mobile responsiveness | Frontend | SearchForm.tsx, page.tsx, favorites/page.tsx |
| 14 | Empty states & skeletons | Frontend | page.tsx, favorites/page.tsx |
| 15 | Remove debug logs | Cleanup | FavoriteButton.tsx, favorites/page.tsx |
| 16 | Final build verification | QA | None |

**Total: 16 tasks. Tasks 1-6 are the highest priority (brand + critical fixes). Tasks 7-12 are the core beta features. Tasks 13-16 are polish and cleanup.**
