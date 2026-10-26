/* ============================================================================
   Waitlist: stop anyone reading it, and record the city people ask for
   Run in the Supabase SQL Editor — QA and prod. Apply BEFORE deploying the
   frontend that sends `city`: until the column exists, every waitlist insert
   fails and the form shows "Something went wrong".

   WHY THE POLICY GOES
   007_waitlist.sql created:

     create policy "Service can read waitlist" on waitlist
       for select using (true);

   A policy with no TO clause applies to public, so the anon key that ships in
   the snugd.ai bundle could read every row — emails and names. Confirmed on
   prod 2026-10-26 with a count-only request (content-range 0-0/2). Same
   mistake as 014 (notifications) and 015 (profiles). The backend reads with
   the service role, which bypasses RLS, so nothing loses access it needs.
   "Anyone can join waitlist" (insert) stays: the landing form uses it.

   WHY city
   Signup is open now, so the waitlist is no longer a queue for access. It
   collects demand for markets Snugd doesn't cover yet: "Not in your city
   yet? Tell us where."
   ============================================================================ */

drop policy if exists "Service can read waitlist" on public.waitlist;

alter table public.waitlist
  add column if not exists city text;
