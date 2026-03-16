-- ============================================
-- Touring Pipeline Schema
-- Run this in Supabase SQL Editor
-- ============================================

-- ============================================
-- TOUR PIPELINE
-- ============================================
create table public.tour_pipeline (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,
  apartment_id text not null,
  stage text not null default 'interested'
    check (stage in ('interested', 'outreach_sent', 'scheduled', 'toured', 'deciding')),
  inquiry_email_draft text,
  outreach_sent_at timestamptz,
  scheduled_date date,
  scheduled_time time,
  tour_rating integer check (tour_rating >= 1 and tour_rating <= 5),
  toured_at timestamptz,
  decision text check (decision in ('applied', 'passed')),
  decision_reason text,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),

  unique(user_id, apartment_id)
);

create index idx_tour_pipeline_user on tour_pipeline(user_id);

-- ============================================
-- TOUR NOTES
-- ============================================
create table public.tour_notes (
  id uuid default gen_random_uuid() primary key,
  tour_pipeline_id uuid references tour_pipeline(id) on delete cascade not null,
  user_id uuid references auth.users(id) on delete cascade not null,
  content text,
  source text not null default 'typed'
    check (source in ('voice', 'typed')),
  audio_s3_key text,
  transcription_status text not null default 'complete'
    check (transcription_status in ('pending', 'complete', 'failed')),
  created_at timestamptz default now()
);

create index idx_tour_notes_pipeline on tour_notes(tour_pipeline_id);

-- ============================================
-- TOUR PHOTOS
-- ============================================
create table public.tour_photos (
  id uuid default gen_random_uuid() primary key,
  tour_pipeline_id uuid references tour_pipeline(id) on delete cascade not null,
  user_id uuid references auth.users(id) on delete cascade not null,
  s3_key text not null,
  thumbnail_url text,
  caption text,
  created_at timestamptz default now()
);

create index idx_tour_photos_pipeline on tour_photos(tour_pipeline_id);

-- ============================================
-- TOUR TAGS
-- ============================================
create table public.tour_tags (
  id uuid default gen_random_uuid() primary key,
  tour_pipeline_id uuid references tour_pipeline(id) on delete cascade not null,
  tag text not null,
  sentiment text not null
    check (sentiment in ('pro', 'con'))
);

create index idx_tour_tags_pipeline on tour_tags(tour_pipeline_id);

-- ============================================
-- ROW LEVEL SECURITY
-- ============================================
alter table tour_pipeline enable row level security;
alter table tour_notes enable row level security;
alter table tour_photos enable row level security;
alter table tour_tags enable row level security;

-- Tour pipeline: users manage own records
create policy "Users manage own tour pipeline" on tour_pipeline
  for all using (auth.uid() = user_id);

-- Service role can update tour_pipeline (for backend operations)
create policy "Service can manage tour pipeline" on tour_pipeline
  for all using (true) with check (true);

-- Tour notes: users manage own records
create policy "Users manage own tour notes" on tour_notes
  for all using (auth.uid() = user_id);

-- Tour photos: users manage own records
create policy "Users manage own tour photos" on tour_photos
  for all using (auth.uid() = user_id);

-- Tour tags: users manage via tour_pipeline ownership
create policy "Users manage own tour tags" on tour_tags
  for all using (
    exists (
      select 1 from tour_pipeline
      where tour_pipeline.id = tour_tags.tour_pipeline_id
        and tour_pipeline.user_id = auth.uid()
    )
  );

-- ============================================
-- UPDATED_AT TRIGGER
-- ============================================
create or replace function public.handle_tour_pipeline_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql security definer;

create trigger on_tour_pipeline_updated
  before update on tour_pipeline
  for each row execute procedure public.handle_tour_pipeline_updated_at();
