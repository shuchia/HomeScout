-- ============================================
-- Saved listings — the user's own copy of a listing
-- Run this in Supabase SQL Editor
-- ============================================
--
-- ADDITIVE AND SAFE TO RUN AT ANY TIME. Creates `saved_listings` and nothing
-- else; no existing table is altered or dropped, and no deployed code reads
-- this table yet.
--
-- The destructive half — repointing tour_notes/tour_photos/tour_tags and
-- dropping `favorites` and `tour_pipeline` — is migration 012, which must run
-- only AFTER the backend and frontend have moved onto saved_listings. Running
-- it early takes down every tour endpoint, the reminder task, voice-note
-- transcription, the beta report and the favorites page, since all of them
-- still address the old tables.
--
-- WHY THIS EXISTS
--
-- favorites, tour_pipeline and notifications all stored `apartment_id` — a
-- pointer into the scraped corpus — and re-joined it live on every read. Three
-- consequences:
--
--   1. The corpus could silently rewrite a user's history. A tour displayed
--      whatever the listing said *now*, not what the user saw when they
--      decided to go. Since the re-seen scrape path never writes `rent`, that
--      could be a price that was never real.
--   2. A listing outside the corpus could not be saved at all. The bulk scrape
--      only ever returns the head ~100 results per market, so most of the
--      internet's listings can never appear there — including every listing a
--      user might paste from Zillow, Craigslist or a management company site.
--   3. Deleting corpus rows gutted user history with no warning.
--
-- The inversion: the user's saved copy IS the record. `listing` is
-- authoritative for display. The corpus becomes a *refresh source* — useful
-- when present, never required.
--
-- Favorites and tours were also two tables describing one thing: a listing
-- someone is considering. They are now stages of one record.

-- ============================================
-- SAVED LISTINGS
-- ============================================
create table public.saved_listings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,

  -- Provenance. All three are nullable-ish because a listing can arrive from
  -- a pasted URL with no corpus row behind it. apartment_id is a soft link
  -- used to refresh the snapshot when we happen to hold that listing — it is
  -- deliberately NOT a foreign key, so pruning the corpus can never cascade
  -- into user data.
  apartment_id text,
  source text not null default 'corpus',
  source_url text,

  -- The user's own copy of the listing (ApartmentModel.to_dict() shape).
  -- Authoritative for every display path. Never null: a saved listing without
  -- listing data is not a saved listing.
  listing jsonb not null,
  listing_captured_at timestamptz not null default now(),
  listing_refreshed_at timestamptz,

  -- Position in the touring pipeline. 'saved' means "not in the pipeline yet".
  stage text not null default 'saved'
    check (stage in ('saved', 'interested', 'outreach_sent', 'scheduled', 'toured', 'deciding')),

  -- The star, tracked separately from `stage` on purpose.
  --
  -- Un-starring a listing you have already toured must leave it in the
  -- pipeline. If the star were just stage='saved', unfavouriting a toured
  -- listing would have to either move it backwards (losing the tour) or refuse
  -- (surprising). They are two independent facts about the same listing:
  -- "I marked this" and "I am this far along with it".
  --
  -- Consequence for the application: unfavouriting sets this false and leaves
  -- stage alone. A row with is_favorite = false AND stage = 'saved' has nothing
  -- left to record and should be deleted rather than kept as an orphan.
  is_favorite boolean not null default false,

  -- Outreach / touring state (was tour_pipeline)
  inquiry_email_draft text,
  outreach_sent_at timestamptz,
  scheduled_date date,
  scheduled_time time,
  contact_phone text,
  contact_email text,
  tour_rating integer check (tour_rating >= 1 and tour_rating <= 5),
  toured_at timestamptz,
  decision text check (decision in ('applied', 'passed')),
  decision_reason text,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- A saved listing must be identifiable even with no corpus row. Generated
  -- rather than trigger-maintained so it cannot drift from its inputs.
  --
  -- Known gap: the same listing saved twice by different routes — once from a
  -- search result (apartment_id set) and once from a pasted URL (source_url
  -- only) — produces two different keys and therefore two rows. The fix
  -- belongs in the add-by-URL path, which should resolve the URL against
  -- apartments.source_url first and set apartment_id when it matches. Noted
  -- here because the schema alone cannot prevent it.
  dedupe_key text generated always as (
    coalesce(apartment_id, lower(source_url))
  ) stored,

  -- Either we know which corpus row this is, or we know where it came from.
  constraint saved_listings_identifiable
    check (apartment_id is not null or source_url is not null)
);

create unique index idx_saved_listings_user_dedupe
  on public.saved_listings (user_id, dedupe_key);

create index idx_saved_listings_user on public.saved_listings (user_id);
create index idx_saved_listings_user_stage on public.saved_listings (user_id, stage);
-- The favourites list is its own view of this table.
create index idx_saved_listings_user_favorite on public.saved_listings (user_id)
  where is_favorite;
-- Refresh sweeps look up saved listings by the corpus row they came from.
create index idx_saved_listings_apartment on public.saved_listings (apartment_id)
  where apartment_id is not null;

comment on column public.saved_listings.listing is
  'The user''s copy of the listing, authoritative for display. The scraped corpus is only a refresh source.';
comment on column public.saved_listings.apartment_id is
  'Soft link to the scraped corpus. Intentionally not a FK — pruning the corpus must never touch user data.';

-- ============================================
-- ROW LEVEL SECURITY
-- ============================================
alter table public.saved_listings enable row level security;

create policy "Users manage own saved listings" on public.saved_listings
  for all using (auth.uid() = user_id);

-- ============================================
-- UPDATED_AT TRIGGER
-- ============================================
create or replace function public.handle_saved_listings_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_saved_listings_updated on public.saved_listings;
create trigger on_saved_listings_updated
  before update on public.saved_listings
  for each row execute procedure public.handle_saved_listings_updated_at();

-- Favorites was in the realtime publication; saved_listings replaces it.
-- Guarded because `alter publication ... add table` errors if it's already
-- there, which would abort a re-run partway through.
do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'saved_listings'
  ) then
    alter publication supabase_realtime add table public.saved_listings;
  end if;
end $$;
