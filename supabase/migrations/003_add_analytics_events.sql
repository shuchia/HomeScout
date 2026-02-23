-- Analytics events table for tracking feature usage and conversion signals.
-- Query directly in Supabase SQL editor; no admin dashboard needed.

CREATE TABLE public.analytics_events (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_events_type_date ON analytics_events(event_type, created_at);
CREATE INDEX idx_events_user ON analytics_events(user_id);

ALTER TABLE analytics_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service can insert events" ON analytics_events FOR INSERT WITH CHECK (true);
CREATE POLICY "Service can read events" ON analytics_events FOR SELECT USING (true);
