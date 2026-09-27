import { Apartment } from './apartment'

/**
 * A change a source check found since the user last looked.
 * Keyed by field: { rent: { from: 2100, to: 1950 } }
 */
export interface ListingChange {
  from: number | string | null
  to: number | string | null
}

export type ListingChanges = Record<string, ListingChange>

/**
 * What the last check learned about the listing at its source.
 *
 * `unknown` is not a soft `gone` — it means the check could not reach the
 * source and we know nothing new. It must never be rendered as though the
 * listing were confirmed unavailable.
 */
export type AvailabilityStatus = 'live' | 'gone' | 'unknown'

/** Position in the touring pipeline. `null` means not in it. */
export type SavedListingStage =
  | 'interested'
  | 'outreach_sent'
  | 'scheduled'
  | 'toured'
  | 'deciding'

/**
 * The user's own copy of a listing.
 *
 * Replaces the old split between `favorites` and `tour_pipeline`. `isFavorite`
 * is the star and `stage` is pipeline position; they are independent, so
 * un-starring something you have toured leaves it in the pipeline.
 *
 * Must stay in sync with supabase/migrations/011 + 013 and
 * backend/app/routers/saved_listings.py.
 */
export interface SavedListing {
  id: string
  user_id: string
  apartment_id: string | null
  source: string
  source_url: string | null

  /** The listing itself, in Apartment shape. Patched by each check. */
  listing: Apartment

  /** Null until a check has run — still the copy taken from the corpus. */
  listing_checked_at: string | null
  availability_status: AvailabilityStatus

  /** Unacknowledged changes found by the last check; null when nothing to show. */
  last_change: ListingChanges | null
  last_change_at: string | null

  is_favorite: boolean
  stage: SavedListingStage | null

  inquiry_email_draft: string | null
  outreach_sent_at: string | null
  scheduled_date: string | null
  scheduled_time: string | null
  contact_phone: string | null
  contact_email: string | null
  tour_rating: number | null
  toured_at: string | null
  decision: 'applied' | 'passed' | null
  decision_reason: string | null

  created_at: string
  updated_at: string
}
