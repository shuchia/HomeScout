-- Add monetization columns to profiles
ALTER TABLE public.profiles ADD COLUMN user_tier TEXT NOT NULL DEFAULT 'free';
ALTER TABLE public.profiles ADD COLUMN stripe_customer_id TEXT;
ALTER TABLE public.profiles ADD COLUMN subscription_status TEXT;
ALTER TABLE public.profiles ADD COLUMN current_period_end TIMESTAMPTZ;

-- Index for quick tier lookups
CREATE INDEX idx_profiles_tier ON profiles(user_tier);
CREATE INDEX idx_profiles_stripe ON profiles(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;

-- Update RLS: allow service role to update tier (for Stripe webhooks)
CREATE POLICY "Service can update profiles" ON profiles
  FOR UPDATE USING (true) WITH CHECK (true);