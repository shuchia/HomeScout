-- ============================================
-- Tour apartment snapshot
-- Run this in Supabase SQL Editor
-- ============================================
--
-- tour_pipeline stores only apartment_id and re-joins the scraped corpus on
-- every read, so a tour has never owned the listing it is about. Three
-- consequences, all of which this migration exists to end:
--
--   1. The tour displays whatever the corpus says *now*, not what the user saw
--      when they toured. Since the re-seen scrape path never writes `rent`, a
--      tour can show a price that is neither current nor the one the user
--      decided against.
--   2. If the row is missing, reads degrade silently to "Unknown" and the
--      inquiry-email endpoint 404s outright.
--   3. A listing added by URL has no corpus row at all, so apartment_id cannot
--      by itself represent it. The snapshot is what makes add-by-URL possible.
--
-- The snapshot is the shape returned by ApartmentModel.to_dict(). It is also
-- the substrate for lease-vs-listing reconciliation later: "the listing said
-- water was included" requires having stored what the listing said at the time.

alter table public.tour_pipeline
  add column if not exists apartment_snapshot jsonb,
  add column if not exists snapshot_at timestamptz;

comment on column public.tour_pipeline.apartment_snapshot is
  'Listing data as of when the user added this tour (ApartmentModel.to_dict() shape). Authoritative for display; the live corpus is only a fallback for rows predating this column.';

comment on column public.tour_pipeline.snapshot_at is
  'When apartment_snapshot was captured.';

-- Partial index for finding rows that still need backfilling.
create index if not exists idx_tour_pipeline_missing_snapshot
  on public.tour_pipeline (id)
  where apartment_snapshot is null;
