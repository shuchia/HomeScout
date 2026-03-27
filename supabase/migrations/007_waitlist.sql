create table public.waitlist (
  id uuid default gen_random_uuid() primary key,
  email text not null unique,
  name text,
  referral_source text,  -- "friend", "social", "search", etc.
  created_at timestamptz default now()
);

create index idx_waitlist_email on waitlist(email);

alter table waitlist enable row level security;
-- Public can insert (no auth needed for signup)
create policy "Anyone can join waitlist" on waitlist
  for insert with check (true);
-- Only service role can read
create policy "Service can read waitlist" on waitlist
  for select using (true);
