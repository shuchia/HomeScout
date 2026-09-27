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

-- WHAT THIS TABLE DELIBERATELY DOES NOT STORE, AND HOW TO GET IT BACK
--
-- An earlier draft carried six listing-related fields. Three were cut. None of
-- the cuts is a one-way door, but they are not equally reversible, so:
--
--   listing_captured_at  — cut as genuinely redundant. Row creation *is* the
--     capture, so it duplicated created_at exactly. Nothing can ever need it.
--
--   listing_refreshed_at — not cut, renamed to listing_checked_at. Same field.
--
--   availability_checked_at — merged into listing_checked_at. One check answers
--     "is it still there" and "has it changed" at the same instant, so the two
--     timestamps would always hold the same value. Re-add it only if checks
--     ever stop being a single operation.
--
--   listing_as_saved (a frozen copy of the listing as first seen) — cut, and
--     this is the one with a cost. The column itself is trivially re-addable,
--     but the data is not recoverable retroactively: once `listing` has been
--     overwritten by a check, the original is gone. Today that costs nothing
--     because this table has no rows. The cost accrues gradually as people
--     start saving listings, so the door closes slowly rather than slamming.
--
--     Two things would want it: "the rent dropped $200 since you saved this",
--     and lease-vs-listing reconciliation ("the listing said water was
--     included"), which is the sharpest feature on the roadmap. Neither exists.
--
--     Insurance, so that waiting is not expensive: the check already computes a
--     diff in order to tell the user what changed. Log that diff to
--     analytics_events (event_type 'listing-changed', metadata carrying the
--     before/after). That table already exists, takes arbitrary JSON, and is
--     fire-and-forget, so it costs no schema commitment — and it preserves the
--     record of every observed change, which is what both of those features
--     actually need. Adding listing_as_saved later then loses only the original
--     first-seen state, not the change history.

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
  --
  -- Replaced wholesale whenever the listing is checked against its source,
  -- which happens when the user favourites it, adds it to a comparison, or adds
  -- it to the tour pipeline. Between those moments it can be up to one scrape
  -- interval stale, which is fine — nothing is promised to the user off the
  -- back of a search result. Checking stops once `decision` is set, so a
  -- decided listing naturally freezes at the state it was decided on.
  listing jsonb not null,

  -- When `listing` was last checked against the source. NULL means never
  -- checked, i.e. it is still the copy taken from the scraped corpus.
  --
  -- Replaces the listing_captured_at / listing_refreshed_at pair from the
  -- first draft. captured_at duplicated created_at exactly, and one timestamp
  -- covers both questions because a single check answers "is it still there"
  -- and "has it changed" at the same instant.
  listing_checked_at timestamptz,

  -- Result of that check. 'unknown' until one has run, or when a check could
  -- not reach the source — a failed check must never be recorded as 'live'.
  availability_status text not null default 'unknown'
    check (availability_status in ('live', 'gone', 'unknown')),

  -- Position in the touring pipeline. NULL means not in the pipeline.
  --
  -- The first draft used stage='saved' for that, which invented a "saved
  -- listings" concept the product does not have and gave the table three
  -- overlapping states (row exists / starred / in pipeline) where there are
  -- only two facts worth recording.
  stage text
    check (stage is null or stage in
      ('interested', 'outreach_sent', 'scheduled', 'toured', 'deciding')),

  -- The star, tracked separately from `stage` on purpose.
  --
  -- Un-starring a listing you have already toured must leave it in the
  -- pipeline. If the star were just stage='saved', unfavouriting a toured
  -- listing would have to either move it backwards (losing the tour) or refuse
  -- (surprising). They are two independent facts about the same listing:
  -- "I marked this" and "I am this far along with it".
  --
  -- Consequence for the application: unfavouriting sets this false and leaves
  -- stage alone. While there is no board UI, a row left with is_favorite=false
  -- and stage IS NULL is invisible but still present, so the unfavourite
  -- handler should delete it in that case. That is transitional application
  -- behaviour, not a schema rule — once listings can live on a board without
  -- being starred, unfavouriting must stop deleting anything.
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
-- Partial: only rows actually in the pipeline, which is the tours view.
create index idx_saved_listings_user_stage on public.saved_listings (user_id, stage)
  where stage is not null;
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
