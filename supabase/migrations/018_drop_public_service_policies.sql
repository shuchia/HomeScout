/* ============================================================================
   Drop the remaining "Service can …" policies that were granted to everyone
   Run in the Supabase SQL Editor — QA and prod. Apply on QA BEFORE copying QA
   into prod, or the copy carries these policies across.

   WHY
   Same mistake as 014, 015 and 017: a policy with no TO clause applies to
   public, so the anon key that ships in every snugd.ai bundle gets it. These
   were meant for the backend, which uses the service role and bypasses RLS
   anyway — so none of them ever gave the backend anything. Found 2026-10-26
   by asking QA for row counts with the anon key:

     analytics_events    readable and writable by anyone (765 rows on QA)
     invite_codes        readable, insertable, updatable, deletable by anyone
     invite_redemptions  readable, insertable, deletable by anyone (16 rows)
     beta_feedback       every user's feedback readable by anyone
     saved_searches      UPDATE with CHECK (true): a signed-in user could
                         reassign a row to another user

   The frontend queries only profiles, saved_searches and waitlist directly;
   invites, feedback and analytics all go through the backend (service role).

   WHAT STAYS
   "Users read own redemptions", "Users insert own feedback", "Users read own
   feedback", "Users manage own searches", "Anyone can join waitlist".
   ============================================================================ */

drop policy if exists "Service can insert events"        on public.analytics_events;
drop policy if exists "Service can read events"          on public.analytics_events;
drop policy if exists "Anyone can read invite codes"     on public.invite_codes;
drop policy if exists "Service can manage invite codes"  on public.invite_codes;
drop policy if exists "Service can manage redemptions"   on public.invite_redemptions;
drop policy if exists "Service can read all feedback"    on public.beta_feedback;
drop policy if exists "Service can update saved_searches" on public.saved_searches;
