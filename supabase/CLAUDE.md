# Supabase CLAUDE.md

Claude Code guidance for the Snugd Supabase project — auth, user data, tours, and beta tracking.

## Division of Responsibility

| Lives in Supabase | Lives in Postgres (RDS) |
|-------------------|-------------------------|
| Auth (`auth.users`), profiles, tiers | Apartment listings (`apartments`) |
| Favorites, saved searches, notifications | Floorplan buckets (`apartment_floorplans`) |
| Tour pipeline (tours, notes, photos, tags) | Scrape jobs, data sources, market configs |
| Invite codes, redemptions, beta feedback, waitlist | |
| Analytics events, user locations | |

They are **separate databases**. Apartment rows are referenced from Supabase by `apartment_id text` with no FK — the backend hydrates them from RDS via `/api/apartments/batch`.

## Migrations

Applied in order from `migrations/`. There is no migration runner in the repo — these are applied through the Supabase SQL editor / CLI.

| Migration | Adds |
|-----------|------|
| `001_initial_schema.sql` | `profiles`, `favorites`, `saved_searches`, `notifications`, RLS, `handle_new_user` trigger |
| `002_add_tier_columns.sql` | `user_tier`, `stripe_customer_id`, `subscription_status`, `current_period_end` on `profiles` |
| `003_add_analytics_events.sql` | `analytics_events` |
| `004_update_saved_searches.sql` | `last_alerted_at`, `is_active` + service update policy |
| `005_tour_pipeline.sql` | `tour_pipeline`, `tour_notes`, `tour_photos`, `tour_tags` + updated-at trigger |
| `006_beta_launch.sql` | `invite_codes`, `invite_redemptions`, `beta_feedback` |
| `007_waitlist.sql` | `waitlist` |
| `008_tour_contact_info.sql` | `contact_phone`, `contact_email` on `tour_pipeline` |
| `009_add_user_locations.sql` | `user_locations` (commute destinations) |

## Key Tables

### `profiles`
Created automatically for every new auth user by the `on_auth_user_created` trigger → `handle_new_user()`.

```sql
id uuid primary key references auth.users(id) on delete cascade
email text, name text, avatar_url text
email_notifications boolean default true
user_tier text not null default 'free'      -- 'free' | 'pro'
stripe_customer_id text
subscription_status text                     -- active | past_due | ...
current_period_end timestamptz
created_at, updated_at timestamptz
```

`user_tier` is the single source of truth for gating. It is written by the Stripe webhook handler **and** by invite redemption — both via the service-role client in `backend/app/services/tier_service.py`.

### `tour_pipeline`
The core touring feature. One row per (user, apartment) — enforced by `unique(user_id, apartment_id)`.

```sql
stage text not null default 'interested'
  check (stage in ('interested','outreach_sent','scheduled','toured','deciding'))
inquiry_email_draft text
outreach_sent_at timestamptz
scheduled_date date, scheduled_time time
tour_rating integer check (1..5)
toured_at timestamptz
decision text check (decision in ('applied','passed'))
decision_reason text
contact_phone text, contact_email text       -- added in 008
```

Children: `tour_notes`, `tour_photos`, `tour_tags`, each FK'd to `tour_pipeline` and indexed on it.

### `invite_codes` / `invite_redemptions`

```sql
invite_codes(code text pk, max_uses int default 1, times_used int default 0,
             expires_at timestamptz, created_at timestamptz)

invite_redemptions(id uuid pk, code text references invite_codes(code),
                   user_id uuid references auth.users(id),
                   redeemed_at timestamptz, unique(code, user_id))
```

`times_used` is an atomic counter on `invite_codes`; `invite_redemptions` is the row-level record. **They should always agree** — `/api/admin/beta-report` cross-checks `times_used` against the actual redemption count and surfaces any divergence, which would indicate a counter bug.

Redeeming a code sets `profiles.user_tier = 'pro'`.

### `user_locations`

```sql
location_type text check (location_type in ('work','school'))
label text not null, address text not null
latitude, longitude double precision
is_primary boolean default false
unique(user_id, label)
```

### `beta_feedback`, `waitlist`, `analytics_events`
Feedback and waitlist accept public/anon inserts (`"Anyone can insert"` policies); reads are service-role only. `analytics_events` is written fire-and-forget by the backend and is service-role on both sides.

## RLS Model

Two policy shapes throughout:

1. **`"Users can ..."`** — `auth.uid() = user_id`. Everything user-owned (profiles, favorites, saved_searches, notifications, tour_*, user_locations, own feedback).
2. **`"Service can ..."`** — service-role only. Used for anything the backend writes on the user's behalf: tier updates, analytics, alert bookkeeping (`last_alerted_at`), invite code administration, waitlist reads.

The backend holds a module-level service-role client (`supabase_admin` in `tier_service.py`) that **bypasses RLS**. It is reused by `beta_admin.py` for reporting. Never expose service-role behavior through an unauthenticated route — every admin surface is gated by `X-Admin-Key`.

## Working With It

```bash
# The backend reaches Supabase with these
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...   # bypasses RLS — backend only
SUPABASE_JWT_SECRET=...         # HS256, audience "authenticated"

# The frontend uses the anon key (RLS enforced)
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
```

## Gotchas

| Issue | Cause |
|-------|-------|
| New user has no profile row | The `on_auth_user_created` trigger didn't fire — check it exists in `001` |
| Tier change didn't take effect | `user_tier` is read per-request via `TierService.get_user_tier()`, but that call fails open to `"free"` if Supabase is unreachable |
| Frontend can't read a row it just wrote | RLS — the anon key only sees `auth.uid() = user_id` rows |
| `times_used` ≠ redemption count | Atomicity bug in code redemption; the beta report flags it |
| Duplicate tour on the same apartment | Blocked by `unique(user_id, apartment_id)` — surfaces as a constraint error |
