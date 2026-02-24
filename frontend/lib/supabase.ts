import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://placeholder.supabase.co'
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || 'placeholder-key'

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    // Use localStorage for session persistence (reliable auto-refresh).
    // The @supabase/ssr cookie-based approach requires Next.js middleware
    // we don't have, causing stale tokens and hanging getSession() calls.
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
})

// Types for Supabase tables
export interface Profile {
  id: string
  email: string
  name: string | null
  avatar_url: string | null
  email_notifications: boolean
  user_tier: 'free' | 'pro'
  subscription_status: string | null
  current_period_end: string | null
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
