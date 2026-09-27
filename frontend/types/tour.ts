import { Apartment } from './apartment'
import { AvailabilityStatus, ListingChanges } from './savedListing'

export type TourStage = 'interested' | 'outreach_sent' | 'scheduled' | 'toured' | 'deciding'

export interface TourNote {
  id: string
  content: string | null
  source: 'voice' | 'typed'
  transcription_status: string | null
  created_at: string
}

export interface TourPhoto {
  id: string
  thumbnail_url: string | null
  caption: string | null
  created_at: string
}

export interface TourTag {
  id: string
  tag: string
  sentiment: 'pro' | 'con'
}

export interface Tour {
  id: string
  /** Null for a listing added by URL, which has no corpus row behind it. */
  apartment_id: string | null
  /** The tour's own copy of the listing. Always present; no batch fetch needed. */
  listing: Apartment
  listing_checked_at: string | null
  availability_status: AvailabilityStatus
  /** Unacknowledged changes a source check found; null when there is nothing to show. */
  last_change: ListingChanges | null
  last_change_at: string | null
  is_favorite: boolean
  stage: TourStage
  inquiry_email_draft: string | null
  outreach_sent_at: string | null
  scheduled_date: string | null
  scheduled_time: string | null
  tour_rating: number | null
  toured_at: string | null
  notes: TourNote[]
  photos: TourPhoto[]
  tags: TourTag[]
  decision: 'applied' | 'passed' | null
  decision_reason: string | null
  contact_phone: string | null
  contact_email: string | null
  created_at: string
  updated_at: string
}
