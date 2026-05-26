# Frontend

> Last verified: 2026-05-04 | Source of truth: this doc + the code it references

Next.js App Router app for Snugd. Mobile-first; renders the same shell on desktop with a sticky bottom nav that hides at `md`.

## Quick Commands

```bash
cd frontend
npm install              # install
npm run dev              # dev server on :3000
npm run build            # production build
npm run lint             # ESLint

# E2E (auto-starts dev server)
npx playwright test
npx playwright test --headed
```

Required env: `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`), `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

## Stack

Next.js 16 (App Router) · React 19 · TypeScript 5 · Tailwind 4 (`@theme inline`) · Zustand 5 · `@supabase/supabase-js` 2.94 · `embla-carousel-react` 8.6 · `react-joyride` 3 (onboarding walkthrough) · Playwright 1.58.

## Architecture

```
frontend/
├── app/                  # Next.js App Router
│   ├── layout.tsx        # Wraps in <AuthProvider>; renders Header + BottomNav
│   ├── page.tsx          # Search + results (the home page)
│   ├── globals.css       # Tailwind v4 @theme tokens (Snugd palette)
│   ├── auth/callback/    # PKCE OAuth code exchange
│   ├── compare/          # Side-by-side comparison (up to 3)
│   ├── favorites/        # Saved apartments
│   ├── tours/            # Tour dashboard
│   │   └── [id]/         # Tour detail (capture/email/schedule tabs)
│   ├── landing/          # Marketing site (passthrough layout)
│   ├── pricing/          # Stripe Checkout entry
│   └── settings/         # Profile, subscription, sign-out
├── components/           # 25 components (table below)
├── hooks/                # useComparison (Zustand), useFavorites (RT subscription)
├── lib/                  # api, auth-store (sync), supabase, geocode
├── contexts/             # AuthContext
├── types/                # apartment.ts, tour.ts (must mirror backend schemas.py)
└── e2e/                  # Playwright specs
```

`app/landing/layout.tsx` is a **passthrough** (`<>{children}</>`) — it does NOT actively hide Header/BottomNav. The marketing chrome is gated by `useAuth()` checks inside Header/ComparisonBar plus the `md:hidden` rule on BottomNav.

## Routes

| Path | Auth | Purpose |
|------|------|---------|
| `/` | optional | Search form + results grid (sticky form on desktop, sessionStorage persists results) |
| `/compare` | optional | Compare up to 3 apartments; Pro gets Claude head-to-head analysis |
| `/favorites` | required | List saved apartments; "Start Touring" button per card |
| `/tours` | required | Tour dashboard with Today/Upcoming/All tabs, Day Planner banner, Decision Brief banner |
| `/tours/[id]` | required | Tour detail with Capture/Email/Schedule tabs; sticky Apply/Pass/Undecided bar |
| `/pricing` | optional | Stripe Checkout CTA, feature table |
| `/settings` | required | Profile, current tier, subscription portal, sign out |
| `/landing` | optional | Public marketing page (separate visual layout) |
| `/auth/callback` | n/a | OAuth PKCE code exchange, redirects to `/` |

## Components

| Component | Purpose |
|-----------|---------|
| `Header` | Top bar with logo, route links, UserMenu/AuthButton |
| `BottomNav` | Mobile-only nav (hidden `md:hidden`) — Home / Tours / Favorites |
| `UserMenu` | Authenticated dropdown: settings, subscription, sign out |
| `AuthButton` | "Sign in with Google" entry point |
| `SearchForm` | City, budget, beds/baths, type, move-in date, free-text preferences |
| `ApartmentCard` | Listing card with image carousel, match badge, cost breakdown link |
| `ImageCarousel` | embla-carousel with arrows, dots, swipe |
| `NearLocationInput` | Geocoded "near a place" search input |
| `RadiusSlider` | Distance slider for proximity search (Pro) |
| `FavoriteButton` | Heart toggle with optimistic update + rollback |
| `CompareButton` | Adds/removes apartment from comparison set |
| `ComparisonBar` | Floating bar showing selected apartments + "Compare" CTA |
| `CostBreakdownPanel` | Modal with utilities/fees/parking/pet sources |
| `TourCard` | Tour summary card on dashboard (stage badge, rating, decision) |
| `TourPrompt` | "Start Touring" button on favorited apartments |
| `TourScheduler` | Date/time picker for `scheduled_at` |
| `VoiceCapture` | Hold-to-record mic; uploads audio for Whisper transcription |
| `StarRating` | 1–5 stars; setting auto-advances Scheduled → Toured |
| `TagPicker` | Pro/con quick tags with "+ Custom" entry |
| `DayPlanner` | AI route optimization for 2+ same-day tours (Pro) |
| `DecisionBrief` | AI synthesis of toured apartments (Pro, requires 2+ toured) |
| `UpgradePrompt` | Tier-gated CTA for free users hitting Pro features |
| `InviteCodeBanner` | Redemption banner; grants 90-day Pro |
| `OnboardingWalkthrough` | react-joyride tour for first-time users |
| `FeedbackWidget` | Beta feedback collector → `/api/feedback` |

## Hooks

| Hook | Purpose |
|------|---------|
| `useComparison` | Zustand store persisted to `localStorage["snugd-comparison"]` (max 3 apartments) |
| `useFavorites` | React state + Supabase realtime subscription with optimistic updates and rollback |

## Lib

| File | Purpose |
|------|---------|
| `lib/api.ts` | API client; reads token synchronously from auth-store, attaches Bearer; custom `ApiError` |
| `lib/auth-store.ts` | Module-level `_accessToken`; `getAccessToken()` is sync — no `await` in hot path |
| `lib/supabase.ts` | `createClient` with localStorage session; auto token refresh |
| `lib/geocode.ts` | Client-side geocoding helper for "near a place" search |

## State Management

- **Auth**: `AuthContext` (React) — `user`, `session`, `accessToken`, `profile`, `tier`, `isPro`, plus 5-second safety timeout that proceeds as anonymous if `getSession()` hangs.
- **Comparison**: Zustand store (`useComparison`) persisted to `localStorage["snugd-comparison"]`.
- **Favorites**: `useFavorites` hook — local React state hydrated from Supabase, optimistic toggles, rollback on error, realtime subscription for cross-device sync.
- **Search results**: persisted in `sessionStorage` so navigating Search → Detail → Compare → back doesn't re-fetch.
- **Token**: mirrored from AuthContext into `lib/auth-store.ts` so `lib/api.ts` can read synchronously.

## Theming

`app/globals.css` defines color tokens via Tailwind v4 `@theme inline`:

- Snugd green `#2D6A4F` (primary)
- Coral `#E76F51` (accent / decision-bar Pass)
- Off-white `#FAFAF8` (background)
- Plus secondary gray scale

Use Tailwind utility classes (`bg-primary`, `text-accent`, etc.). System fonts (SF Pro / Segoe UI / Roboto stack).

## Testing (Playwright)

- Specs: `e2e/homescout.spec.ts`, `e2e/tours.spec.ts`.
- Config: `playwright.config.ts` — Chromium, **single worker** (avoids Claude rate limits), **60s timeout**, **auto-starts dev server**.
- **Auth bypass**: set `localStorage.__test_auth_user` (and optionally `__test_auth_profile`) before page load. `AuthContext` honors these only when `NODE_ENV !== 'production'`.
- `SKIP_BACKEND_TESTS=true npm test` runs the subset that doesn't hit the API.

## Key Conventions

- **Type sync**: `types/apartment.ts` and `types/tour.ts` MUST mirror `backend/app/schemas.py`. Drift causes silent runtime bugs.
- **Search persistence**: results live in `sessionStorage`, not state — they survive Compare ↔ Detail navigation.
- **Optimistic favorites**: heart toggles immediately, rolls back on API failure. `useFavorites` filters out stub apartments deleted from DB (recent fix `75de3ad`).
- **Token reads are synchronous**: never `await getSession()` in API code paths — that previously hung; use the auth-store mirror.
- **Bottom nav** is mobile-only; desktop layouts use Header navigation.
- **Comparison cap = 3** — enforced by `useComparison`.

## Common Issues

| Issue | Fix |
|-------|-----|
| Auth spinner stuck on load | Supabase `getSession()` hung — 5-second timeout will proceed as anonymous. Check Supabase status / clear localStorage. |
| `localStorage` access during SSR | Guard reads with `typeof window !== 'undefined'` |
| Type drift after backend change | Re-pull `schemas.py` field names; run `npx tsc --noEmit` |
| Playwright auth not applied | Bypass only works when `NODE_ENV !== 'production'`; ensure dev or test build |
| Search results lost on hard refresh | `sessionStorage` is per-tab — expected on full reload |
