import { createBrowserClient } from '@supabase/ssr'

// Provide placeholder values for build time - actual values needed at runtime
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://placeholder.supabase.co'
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || 'placeholder-key'

export const supabase = createBrowserClient(supabaseUrl, supabaseAnonKey)

// Types for Supabase tables
export interface Profile {
  id: string
  email: string
  name: string | null
  avatar_url: string | null
  email_notifications: boolean
}

export interface Favorite {
  id: string
  user_id: string
  apartment_id: string
  notes: string | null
  is_available: boolean
  created_at: string
}

export interface SavedSearch {
  id: string
  user_id: string
  name: string
  city: string
  budget: number | null
  bedrooms: number | null
  bathrooms: number | null
  property_type: string | null
  preferences: string | null
  notify_new_matches: boolean
  created_at: string
}

export interface Notification {
  id: string
  user_id: string
  type: 'listing_unavailable' | 'new_match'
  title: string
  message: string | null
  apartment_id: string | null
  saved_search_id: string | null
  read: boolean
  created_at: string
}
