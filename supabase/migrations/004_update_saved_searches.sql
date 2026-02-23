-- ============================================
-- Update saved_searches for alert tracking
-- ============================================

-- Add columns for alert tracking and soft-disable
ALTER TABLE public.saved_searches ADD COLUMN IF NOT EXISTS last_alerted_at TIMESTAMPTZ;
ALTER TABLE public.saved_searches ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;

-- Allow the service role to update saved_searches (e.g., to set last_alerted_at)
CREATE POLICY "Service can update saved_searches" ON public.saved_searches
  FOR UPDATE USING (true) WITH CHECK (true);
