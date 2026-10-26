/* ============================================================================
   AI consent column + close the profile self-upgrade hole
   Run in the Supabase SQL Editor. Apply BEFORE deploying the backend that
   reads ai_consent_at — until the column exists the consent lookup errors,
   fails closed, and AI is off for everyone.

   WHY ai_consent_at
   AI is now free for every signed-in user, and the app stores require
   permission before a user's data goes to a third-party AI provider
   (Anthropic for scoring/compare/tours, OpenAI for voice transcription).
   NULL = never agreed. The backend checks it before every Claude call
   (TierService.has_ai_consent); the frontend asks once and writes it.

   WHY THE POLICY GOES
   002_add_tier_columns.sql granted:

     CREATE POLICY "Service can update profiles" ON profiles
       FOR UPDATE USING (true) WITH CHECK (true);

   The grant is to public, not to service_role — the same mistake 014 fixed
   for notifications. The service role bypasses RLS, so the policy never did
   anything for the backend; it only widened what anon-key callers can do.

   WHY THE COLUMN GRANTS
   "Users update own profile" (001) lets a user update every column of their
   own row, user_tier and pro_expires_at included. With the anon key that
   ships in the browser bundle, anyone signed in could make themselves Pro.
   The tier no longer gates AI, but the columns still feed billing and the
   beta report, and nothing a user writes should be able to set them.

   Table-level UPDATE overrides column-level grants, so it is revoked first
   and then granted back for exactly the columns the client writes:
   has_completed_onboarding (OnboardingWalkthrough) and ai_consent_at (the
   consent prompt), plus name / avatar_url / email_notifications, which are
   the user's own preferences. Every other write goes through the backend's
   service-role client.
   ============================================================================ */

alter table public.profiles
  add column if not exists ai_consent_at timestamptz;

drop policy if exists "Service can update profiles" on public.profiles;

revoke update on public.profiles from anon, authenticated;
grant update (name, avatar_url, email_notifications, has_completed_onboarding, ai_consent_at)
  on public.profiles to authenticated;
