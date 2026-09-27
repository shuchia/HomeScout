/* ============================================================================
   Saved listings — the user's own copy of a listing
   Run in the Supabase SQL Editor.

   ADDITIVE AND SAFE. Creates saved_listings and nothing else. No existing
   table is altered or dropped, and no deployed code reads it yet. The
   destructive half — repointing tour_notes/tour_photos/tour_tags and dropping
   favorites and tour_pipeline — is migration 012, which must run only AFTER
   the backend and frontend have moved onto saved_listings.

   All prose lives in this one block rather than interleaved through the
   statements: a lost newline anywhere in a `--` comment silently swallows the
   SQL that follows it on the same line, which is a miserable way to debug a
   hand-pasted migration.

   WHY THIS TABLE EXISTS
   favorites, tour_pipeline and notifications all stored apartment_id — a
   pointer into the scraped corpus — and re-joined it live on every read. So
   the corpus could silently rewrite a user's history, a listing outside the
   corpus could not be saved at all, and pruning corpus rows gutted user data
   without warning. The inversion: the user's saved copy IS the record, and the
   corpus becomes a refresh source. Favorites and tours were also two tables
   describing one thing, so they become one record.

   COLUMN NOTES
   apartment_id   Soft link to the corpus. Deliberately NOT a foreign key, so
                  pruning the corpus can never cascade into user data.
   listing        Replaced wholesale by each check against the source, which
                  runs when the user favourites, compares, or adds to tours.
                  Checking stops once `decision` is set, so a decided listing
                  freezes at the state it was decided on.
   listing_checked_at  NULL means never checked — still the corpus copy.
   availability_status A failed check records 'unknown', never 'live'.
   stage          NULL means not in the touring pipeline.
   is_favorite    Separate from stage on purpose: un-starring a listing you
                  have already toured must leave it in the pipeline. While
                  there is no board UI, the unfavourite handler should delete
                  rows left with is_favorite=false AND stage IS NULL. That is
                  transitional behaviour, not a schema rule.
   dedupe_key     Generated, not trigger-maintained, so it cannot drift. The
                  check constraint keeps it non-null; a NULL would silently
                  defeat the unique index. Known gap: the same listing saved
                  once from search (apartment_id) and once from a pasted URL
                  (source_url) yields two keys and two rows. The add-by-URL
                  path must resolve the URL against apartments.source_url and
                  set apartment_id when it matches.

   WHAT THIS DELIBERATELY DOES NOT STORE
   An earlier draft had six listing fields; three were cut. listing_captured_at
   duplicated created_at exactly. listing_refreshed_at was renamed to
   listing_checked_at. availability_checked_at merged into it, because one
   check answers both questions at the same instant.

   listing_as_saved — a frozen copy of the listing as first seen — is the one
   cut with a cost. The column is trivially re-addable but the data is not
   recoverable once `listing` has been overwritten, so the door closes
   gradually as people start saving. Two roadmap features want it ("the rent
   dropped since you saved this", and lease-vs-listing reconciliation) and
   neither exists. Insurance: log the diff each check already computes to
   analytics_events, which takes arbitrary JSON and needs no schema
   commitment. That preserves the change history, so adding the column later
   forfeits only the original first-seen state.
   ========================================================================= */

create table public.saved_listings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  apartment_id text,
  source text not null default 'corpus',
  source_url text,
  listing jsonb not null,
  listing_checked_at timestamptz,
  availability_status text not null default 'unknown' check (availability_status in ('live', 'gone', 'unknown')),
  stage text check (stage in ('interested', 'outreach_sent', 'scheduled', 'toured', 'deciding')),
  is_favorite boolean not null default false,
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
  dedupe_key text generated always as (coalesce(apartment_id, lower(source_url))) stored,
  constraint saved_listings_identifiable check (apartment_id is not null or source_url is not null)
);
create unique index idx_saved_listings_user_dedupe
  on public.saved_listings (user_id, dedupe_key);
create index idx_saved_listings_user on public.saved_listings (user_id);
create index idx_saved_listings_user_stage on public.saved_listings (user_id, stage)
  where stage is not null;
create index idx_saved_listings_user_favorite on public.saved_listings (user_id)
  where is_favorite;
create index idx_saved_listings_apartment on public.saved_listings (apartment_id)
  where apartment_id is not null;
comment on column public.saved_listings.listing is
  'The user''s copy of the listing, authoritative for display. The scraped corpus is only a refresh source.';
comment on column public.saved_listings.apartment_id is
  'Soft link to the scraped corpus. Intentionally not a FK — pruning the corpus must never touch user data.';
alter table public.saved_listings enable row level security;
create policy "Users manage own saved listings" on public.saved_listings
  for all using (auth.uid() = user_id);
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
