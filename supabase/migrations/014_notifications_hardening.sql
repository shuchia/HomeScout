/* ============================================================================
   Harden notifications: close the anon insert hole, add the deep link
   Run in the Supabase SQL Editor.

   PARTLY DESTRUCTIVE — it drops one policy and rewrites one column's values.
   Safe because the only writer is the backend's service-role client
   (`supabase_admin`), which bypasses RLS entirely; grep confirms no anon-key
   path inserts notifications.

   WHY THE POLICY GOES
   001_initial_schema.sql granted:

     create policy "Service can insert notifications" on notifications
       for insert with check (true);

   The grant is to public, not to service_role. NEXT_PUBLIC_SUPABASE_ANON_KEY
   ships inside the browser bundle, so anyone holding it can insert a
   notification addressed to any user_id, with any title and body. That is a
   spoofing and phishing primitive, and the anon key is not a secret. The
   policy also buys nothing: the backend never needs it, because the service
   role is not subject to RLS.

   WHY type GETS A CONSTRAINT
   `type` was free text, so a typo produced a notification no surface knows
   how to render and nothing complained. The allowlist is what the frontend
   can render today plus the two tour kinds the reminder outbox will write.

   ORDERING TRAP
   Rows written by the old reminder task carry type = 'tour_reminder', which
   the allowlist does not include — the constraint would be rejected on
   existing data. The update below therefore runs BEFORE the constraint is
   added. That value is being split into a pre- and post-tour kind, and every
   row that exists today is the post-tour "how was it?" nudge, so they migrate
   to 'tour_reminder_post'.

   WHY saved_listing_id
   Reminders could not deep-link. The old task stored apartment_id, which is
   NULL for any listing added by URL, so those notifications pointed nowhere
   and deduplicated against each other. apartment_id stays for rows written
   before this; every new writer sets saved_listing_id.

   NOT ADDRESSED HERE
   Nothing in the frontend reads this table yet, so these rows remain
   write-only until the inbox and reminder surfaces land. Closing the hole is
   worth doing on its own regardless.
   ========================================================================= */

drop policy if exists "Service can insert notifications" on public.notifications;

create policy "Service inserts notifications" on public.notifications
  for insert to service_role with check (true);

alter table public.notifications
  add column if not exists saved_listing_id uuid
    references public.saved_listings(id) on delete cascade;

update public.notifications
set type = 'tour_reminder_post'
where type = 'tour_reminder';

alter table public.notifications
  drop constraint if exists notifications_type_check;

alter table public.notifications
  add constraint notifications_type_check check (type in (
    'listing_unavailable',
    'new_match',
    'tour_reminder_pre',
    'tour_reminder_post',
    'inbox_reply'
  ));

create index if not exists idx_notifications_saved_listing
  on public.notifications (saved_listing_id)
  where saved_listing_id is not null;

create index if not exists idx_notifications_user_created
  on public.notifications (user_id, created_at desc);

comment on column public.notifications.saved_listing_id is
  'Deep-link target. apartment_id is legacy and NULL for URL-added listings.';
