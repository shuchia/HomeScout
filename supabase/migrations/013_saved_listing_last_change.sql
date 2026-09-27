/* ============================================================================
   Surface "price changed since you saved this" on a saved listing
   Run in the Supabase SQL Editor.

   ADDITIVE AND SAFE. Two nullable columns on saved_listings. Independent of
   migration 012 (the cutover) — these can be applied in either order.

   WHY
   When a check finds the rent moved, the diff is written to analytics_events.
   That preserves the history, but analytics_events is service-role only and
   carries no index for this lookup, so the frontend cannot read it to render a
   marker. Storing the most recent material change on the row itself is what
   makes "rent is now $1,950, was $2,100" displayable.

   This is the smallest thing that supports an explicit marker. The
   alternatives were worse: a listing_previous column would push the decision
   about which fields are material into the frontend, and querying
   analytics_events per listing would need an index on a jsonb field for a
   read that happens on every board render.

   last_change holds the same shape the check already computes:
     {"rent": {"from": 2100, "to": 1950},
      "true_cost_monthly": {"from": 2480, "to": 2330}}

   Cleared when the user dismisses the marker, so it means "there is something
   unseen to tell this user", not "this listing has ever changed". The durable
   history stays in analytics_events.
   ========================================================================= */

alter table public.saved_listings
  add column if not exists last_change jsonb,
  add column if not exists last_change_at timestamptz;

comment on column public.saved_listings.last_change is
  'Most recent unacknowledged material change found by a check, as {field: {from, to}}. Cleared on dismiss; durable history lives in analytics_events.';
