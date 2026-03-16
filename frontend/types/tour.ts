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
  apartment_id: string
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
  created_at: string
  updated_at: string
}
