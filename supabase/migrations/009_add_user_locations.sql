-- ============================================
-- USER LOCATIONS (work/school addresses for commute calculator)
-- Run this in Supabase SQL Editor
-- ============================================

create table public.user_locations (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,

  location_type text not null check (location_type in ('work', 'school')),
  label text not null,
  address text not null,
  latitude double precision,
  longitude double precision,
  is_primary boolean default false,

  created_at timestamptz default now(),

  -- A user can't save two locations under the same label.
  unique(user_id, label)
);

create index idx_user_locations_user on user_locations(user_id);

-- ============================================
-- ROW LEVEL SECURITY
-- ============================================
-- The backend reads/writes via the service-role key (bypasses RLS); these
-- policies protect direct client access, mirroring favorites/saved_searches.
alter table public.user_locations enable row level security;

create policy "Users manage own locations" on user_locations
  for all using (auth.uid() = user_id);
