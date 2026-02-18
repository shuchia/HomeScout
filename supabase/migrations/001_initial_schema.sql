-- ============================================
-- HomeScout MVP User Features Schema
-- Run this in Supabase SQL Editor
-- ============================================

-- ============================================
-- PROFILES (extends auth.users)
-- ============================================
create table public.profiles (
  id uuid references auth.users(id) on delete cascade primary key,
  email text,
  name text,
  avatar_url text,
  email_notifications boolean default true,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Auto-create profile on signup
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, email, name, avatar_url)
  values (
    new.id,
    new.email,
    new.raw_user_meta_data->>'name',
    new.raw_user_meta_data->>'avatar_url'
  );
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- ============================================
-- FAVORITES
-- ============================================
create table public.favorites (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,
  apartment_id text not null,
  notes text,
  is_available boolean default true,
  created_at timestamptz default now(),

  unique(user_id, apartment_id)
);

create index idx_favorites_user on favorites(user_id);
create index idx_favorites_apartment on favorites(apartment_id);

-- ============================================
-- SAVED SEARCHES
-- ============================================
create table public.saved_searches (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,
  name text not null,

  city text not null,
  budget integer,
  bedrooms integer,
  bathrooms integer,
  property_type text,
  move_in_date date,
  preferences text,

  notify_new_matches boolean default true,
  last_checked_at timestamptz,

  created_at timestamptz default now()
);

create index idx_saved_searches_user on saved_searches(user_id);
create index idx_saved_searches_notify on saved_searches(notify_new_matches)
  where notify_new_matches = true;

-- ============================================
-- NOTIFICATIONS
-- ============================================
create table public.notifications (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,

  type text not null,
  title text not null,
  message text,

  apartment_id text,
  saved_search_id uuid references saved_searches(id) on delete set null,

  read boolean default false,
  emailed boolean default false,

  created_at timestamptz default now()
);

create index idx_notifications_user_unread on notifications(user_id, read)
  where read = false;

-- ============================================
-- ROW LEVEL SECURITY
-- ============================================
alter table profiles enable row level security;
alter table favorites enable row level security;
alter table saved_searches enable row level security;
alter table notifications enable row level security;

create policy "Users read own profile" on profiles
  for select using (auth.uid() = id);
create policy "Users update own profile" on profiles
  for update using (auth.uid() = id);

create policy "Users manage own favorites" on favorites
  for all using (auth.uid() = user_id);

create policy "Users manage own searches" on saved_searches
  for all using (auth.uid() = user_id);

create policy "Users read own notifications" on notifications
  for select using (auth.uid() = user_id);
create policy "Users update own notifications" on notifications
  for update using (auth.uid() = user_id);

create policy "Service can insert notifications" on notifications
  for insert with check (true);

-- ============================================
-- REALTIME
-- ============================================
alter publication supabase_realtime add table favorites;
alter publication supabase_realtime add table notifications;
