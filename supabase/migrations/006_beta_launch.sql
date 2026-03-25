-- ============================================
-- INVITE CODES (admin-generated)
-- ============================================
create table public.invite_codes (
  code text primary key,
  max_uses integer not null default 1,
  times_used integer not null default 0,
  expires_at timestamptz,
  created_at timestamptz default now()
);

create table public.invite_redemptions (
  id uuid default gen_random_uuid() primary key,
  code text references invite_codes(code) not null,
  user_id uuid references auth.users(id) on delete cascade not null,
  redeemed_at timestamptz default now(),
  unique(code, user_id)
);

create index idx_invite_redemptions_user on invite_redemptions(user_id);

-- ============================================
-- PROFILES — add pro_expires_at and onboarding
-- ============================================
alter table public.profiles
  add column if not exists pro_expires_at timestamptz,
  add column if not exists has_completed_onboarding boolean not null default false;

-- ============================================
-- BETA FEEDBACK
-- ============================================
create table public.beta_feedback (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,
  type text not null check (type in ('bug', 'suggestion', 'general')),
  message text not null,
  screenshot_url text,
  page_url text,
  metadata jsonb default '{}',
  created_at timestamptz default now()
);

create index idx_beta_feedback_user on beta_feedback(user_id);
create index idx_beta_feedback_type on beta_feedback(type);

-- ============================================
-- ROW LEVEL SECURITY
-- ============================================
alter table invite_codes enable row level security;
create policy "Anyone can read invite codes" on invite_codes
  for select using (true);
create policy "Service can manage invite codes" on invite_codes
  for all using (true) with check (true);

alter table invite_redemptions enable row level security;
create policy "Users read own redemptions" on invite_redemptions
  for select using (auth.uid() = user_id);
create policy "Service can manage redemptions" on invite_redemptions
  for all using (true) with check (true);

alter table beta_feedback enable row level security;
create policy "Users insert own feedback" on beta_feedback
  for insert with check (auth.uid() = user_id);
create policy "Users read own feedback" on beta_feedback
  for select using (auth.uid() = user_id);
create policy "Service can read all feedback" on beta_feedback
  for select using (true);
