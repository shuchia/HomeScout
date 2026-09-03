# Frontend CLAUDE.md

Claude Code guidance for the Snugd frontend — Next.js 16 (App Router) + React 19 + Tailwind 4, deployed on Vercel.

> Product name is **Snugd**; module/path names still say "HomeScout".

## Quick Commands

```bash
npm install
npm run dev          # → :3000
npm run build
npm run start
npm run lint         # eslint

# Playwright E2E (auto-starts `npm run dev` via webServer)
npm test
npm run test:ui
npm run test:headed
```

## Environment Variables

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...

# Feature flag — baked in at BUILD time, not runtime.
# Changing it requires a rebuild, not just a redeploy.
NEXT_PUBLIC_FLOORPLAN_SEARCH=true    # true on QA, unset by default
```

## Routes (`app/`)

| Route | File | Purpose |
|-------|------|---------|
| `/` | `app/page.tsx` | Search app (the main product) |
| `/landing` | `app/landing/page.tsx` | Marketing landing + consolidated beta invite |
| `/compare` | `app/compare/page.tsx` | Side-by-side comparison |
| `/favorites` | `app/favorites/page.tsx` | Saved apartments |
| `/tours` | `app/tours/page.tsx` | Tour pipeline board |
| `/tours/[id]` | `app/tours/[id]/page.tsx` | Single tour — notes, photos, tags, AI features |
| `/pricing` | `app/pricing/page.tsx` | Tier comparison + Stripe checkout |
| `/settings` | `app/settings/page.tsx` | Account, commute addresses, billing portal |
| `/auth/callback` | `app/auth/callback/page.tsx` | Supabase OAuth callback |

### Host-based rewrite (important)

`next.config.ts` rewrites `/` → `/landing` **only** when the host is `snugd.ai` or `www.snugd.ai`. It uses the object form so the rewrite runs in `beforeFiles` — ahead of filesystem routing, which is required because `app/page.tsx` would otherwise already match `/`. Middleware cannot do this: Vercel applies rewrites before the static HTML cache lookup.

Consequence: **`qa.snugd.ai` and local dev serve the search app at `/`**, production serves the marketing page. When testing the landing page locally, go to `/landing` directly.

## Components (`components/`)

### Search & results
| Component | Purpose |
|-----------|---------|
| `SearchForm.tsx` | Filters + `AVAILABLE_CITIES` dropdown (8 cities). Property type is hardcoded to `Apartment` — the filter was removed since all scraped listings are apartments |
| `ApartmentCard.tsx` | Result card; renders floorplan/N+ badges when the floorplan flag is on |
| `ImageCarousel.tsx` | Embla-based photo carousel |
| `CostBreakdownPanel.tsx` | True-cost breakdown (Pro sees sources) |
| `NearLocationInput.tsx` / `RadiusSlider.tsx` | Proximity search controls |
| `FavoriteButton.tsx` / `CompareButton.tsx` / `ComparisonBar.tsx` | Selection affordances |

### Tours
| Component | Purpose |
|-----------|---------|
| `TourCard.tsx` | Pipeline card |
| `TourScheduler.tsx` | Scheduling UI |
| `TourPrompt.tsx` | Nudge to add a tour |
| `VoiceCapture.tsx` | Records voice notes → async Whisper transcription |
| `StarRating.tsx` / `TagPicker.tsx` | Tour rating and tagging |
| `DayPlanner.tsx` | **Pro** — AI day plan |
| `DecisionBrief.tsx` | **Pro** — AI decision brief |

### Commute
| Component | Purpose |
|-----------|---------|
| `CommuteAddresses.tsx` | Manage saved destinations (`/api/user/locations`) |
| `CommutePanel.tsx` | Per-listing commute times |

### Shell, auth, growth
| Component | Purpose |
|-----------|---------|
| `Header.tsx` / `BottomNav.tsx` | Navigation (bottom nav is the mobile primary) |
| `AuthButton.tsx` / `UserMenu.tsx` | Supabase auth entry points |
| `UpgradePrompt.tsx` | Free → Pro conversion surfaces |
| `InviteCodeBanner.tsx` | Beta invite redemption |
| `FeedbackWidget.tsx` | Beta feedback → `/api/feedback` |
| `OnboardingWalkthrough.tsx` | react-joyride tour |
| `InstallPrompt.tsx` | PWA "Add to Home Screen" prompt |
| `ServiceWorkerRegistration.tsx` | Registers `public/sw.js` |

## State & Data

| File | Role |
|------|------|
| `contexts/AuthContext.tsx` | Supabase session → React context. **5-second safety timeout** so the UI is never stuck loading. Reads `localStorage.__test_auth_user` for E2E (guarded to non-production) |
| `lib/auth-store.ts` | Module-level token store. `AuthContext` writes on every session change; `lib/api.ts` reads it **synchronously** — no `getSession()` in the request path. Also refreshes proactively before expiry |
| `lib/api.ts` | Every backend call (~30 functions: search, scoreBatch, tours, notes, photos, tags, commute, invite, billing) |
| `lib/supabase.ts` | Supabase browser client |
| `lib/geocode.ts` | Address → coordinates for proximity search |
| `lib/useCommuteTimes.ts` | Commute times hook |
| `hooks/useComparison.ts` | Zustand store (persisted) — comparison selection + `SearchContext` |
| `hooks/useFavorites.ts` | Favorites via Supabase + batch apartment hydration. **Owns the free-tier 5-favorite cap** (`atLimit`) — the backend does not enforce it |

**Lazy AI**: `searchApartments()` returns immediately with heuristic scores; `scoreBatch()` is a separate call that fills in Claude scoring for Pro users. Don't block first paint on it.

## Types

`types/apartment.ts` and `types/tour.ts` — **must stay in sync with `backend/app/schemas.py`**. This is a hard project convention; there is no codegen.

Key exports: `Apartment`, `ApartmentWithScore`, `ApartmentUnit`, `MatchedFloorplan`, `CostBreakdown`, `CostSources`, `CommuteTime`, `UserLocation`, `SearchParams`, `SearchResponse`, `SearchContext`, `ComparisonAnalysis`, `Tour`, `TourStage`, `TourNote`, `TourPhoto`, `TourTag`.

## PWA

| File | Purpose |
|------|---------|
| `public/manifest.json` | `Snugd — Find Your Perfect Apartment`, standalone, `start_url: /?source=pwa` |
| `public/sw.js` | Minimal service worker — **deliberately caches nothing** |
| `public/icons/` | 192, 512, maskable-512, apple-touch |

The service worker exists only to satisfy Chrome's installability heuristic (a registered `fetch` handler). Caching is intentionally omitted so beta testers never see a stale deploy. If offline support is wanted later, replace it with a real Workbox setup rather than adding caching here.

## Testing (Playwright)

```bash
npm test                       # headless
npx playwright test e2e/tours.spec.ts
```

- `testDir: ./e2e`, `baseURL: http://localhost:3000`, Desktop Chrome project
- `webServer` auto-runs `npm run dev`
- Auth is mocked by setting `localStorage.__test_auth_user` before navigation — honored by `AuthContext` only when `NODE_ENV !== 'production'`

| Spec | Covers |
|------|--------|
| `e2e/homescout.spec.ts` | Search flow, default city (New York, NY) |
| `e2e/tours.spec.ts` | Tour pipeline, notes, photos |
| `e2e/commute.spec.ts` | Saved locations + commute times |

## Stack Notes

- **Next.js 16** App Router, React 19, TypeScript 5
- **Tailwind 4** via `@tailwindcss/postcss`
- `images.unoptimized: true` — listing images come from external CDNs and S3; Vercel image optimization is off
- `zustand` v5 for comparison state, `embla-carousel-react` for carousels, `react-joyride` for onboarding, `html2canvas` for shareable captures

## Deployment

Two Vercel projects — `snugd` (production, `snugd.ai`) and `snugd-dev` — **both deploy from `main`**. `qa.snugd.ai` is an alias, not a separate project. See [../infra/CLAUDE.md](../infra/CLAUDE.md).

## Gotchas

| Issue | Cause |
|-------|-------|
| Landing page shows on `/` locally | It shouldn't — the rewrite is host-gated to `snugd.ai`. Use `/landing` |
| Floorplan badges missing | `NEXT_PUBLIC_FLOORPLAN_SEARCH` is build-time; rebuild, don't just redeploy |
| Auth spinner forever | Should be impossible — `AuthContext` has a 5 s timeout; if it happens, check that timeout wasn't removed |
| E2E auth mock ignored | Only honored when `NODE_ENV !== 'production'` |
| Types drift from API | `types/*.ts` are hand-maintained against `backend/app/schemas.py` |
