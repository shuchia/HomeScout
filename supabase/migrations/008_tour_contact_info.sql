-- Migration 008: Add contact info fields to tour_pipeline
-- Allows users to store property contact phone/email per tour,
-- with optional auto-population from scraped apartment data.

ALTER TABLE tour_pipeline
  ADD COLUMN IF NOT EXISTS contact_phone TEXT,
  ADD COLUMN IF NOT EXISTS contact_email TEXT;
