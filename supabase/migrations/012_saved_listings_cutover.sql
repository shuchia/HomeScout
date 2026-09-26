-- ============================================
-- Saved listings cutover
-- Run this in Supabase SQL Editor
-- ============================================
--
-- DESTRUCTIVE, AND ORDER-DEPENDENT. Run this ONLY after the backend and
-- frontend that read `saved_listings` are deployed. It drops `favorites` and
-- `tour_pipeline`, and repoints the tour children from tour_pipeline_id to
-- saved_listing_id.
--
-- Run it before that deploy and you take down: every /api/tours endpoint
-- (routers/tours.py, 39 references), tour_reminder_tasks, voice-note
-- transcription, the beta report, and the favorites page (useFavorites.ts
-- queries `favorites` directly through the anon key).
--
-- Migration 011 created saved_listings additively, so there is no rush.

-- ============================================
-- REPOINT TOUR CHILDREN
-- ============================================
-- notes/photos/tags belong to a saved listing now. Dropped and recreated
-- rather than altered, since their parent is going away.
drop table if exists public.tour_tags;
drop table if exists public.tour_notes;
drop table if exists public.tour_photos;

create table public.tour_notes (
  id uuid primary key default gen_random_uuid(),
  saved_listing_id uuid not null references public.saved_listings(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  content text,
  source text not null default 'typed' check (source in ('voice', 'typed')),
  audio_s3_key text,
  check (
    (source = 'typed' and content is not null) or
    (source = 'voice' and audio_s3_key is not null)
  ),
  transcription_status text not null default 'complete'
    check (transcription_status in ('pending', 'complete', 'failed')),
  created_at timestamptz not null default now()
);
create index idx_tour_notes_saved_listing on public.tour_notes (saved_listing_id);

create table public.tour_photos (
  id uuid primary key default gen_random_uuid(),
  saved_listing_id uuid not null references public.saved_listings(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  s3_key text not null,
  thumbnail_s3_key text,
  thumbnail_url text,
  caption text,
  created_at timestamptz not null default now()
);
create index idx_tour_photos_saved_listing on public.tour_photos (saved_listing_id);

create table public.tour_tags (
  id uuid primary key default gen_random_uuid(),
  saved_listing_id uuid not null references public.saved_listings(id) on delete cascade,
  tag text not null,
  sentiment text not null check (sentiment in ('pro', 'con')),
  unique(saved_listing_id, tag)
);
create index idx_tour_tags_saved_listing on public.tour_tags (saved_listing_id);

-- ============================================
-- DROP THE OLD TABLES
-- ============================================
drop table if exists public.tour_pipeline;
drop table if exists public.favorites;

-- ============================================
-- ROW LEVEL SECURITY — repointed children
-- ============================================
alter table public.tour_notes enable row level security;
alter table public.tour_photos enable row level security;
alter table public.tour_tags enable row level security;

-- Notes and photos check BOTH their own user_id and the parent's owner.
-- Carried over from 005, these checked user_id alone — which let a client
-- holding the anon key attach a note to somebody else's saved listing simply
-- by stamping its own user_id on the row. The backend never did that (it uses
-- the service-role client and verifies ownership itself), but the tables are
-- reachable directly from the browser, so the policy has to stand on its own.
create policy "Users manage own tour notes" on public.tour_notes
  for all using (
    auth.uid() = user_id
    and exists (
      select 1 from public.saved_listings s
      where s.id = tour_notes.saved_listing_id and s.user_id = auth.uid()
    )
  )
  with check (
    auth.uid() = user_id
    and exists (
      select 1 from public.saved_listings s
      where s.id = tour_notes.saved_listing_id and s.user_id = auth.uid()
    )
  );

create policy "Users manage own tour photos" on public.tour_photos
  for all using (
    auth.uid() = user_id
    and exists (
      select 1 from public.saved_listings s
      where s.id = tour_photos.saved_listing_id and s.user_id = auth.uid()
    )
  )
  with check (
    auth.uid() = user_id
    and exists (
      select 1 from public.saved_listings s
      where s.id = tour_photos.saved_listing_id and s.user_id = auth.uid()
    )
  );

create policy "Users manage own tour tags" on public.tour_tags
  for all using (
    exists (
      select 1 from public.saved_listings s
      where s.id = tour_tags.saved_listing_id
        and s.user_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1 from public.saved_listings s
      where s.id = tour_tags.saved_listing_id
        and s.user_id = auth.uid()
    )
  );
