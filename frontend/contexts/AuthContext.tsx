'use client'
import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react'
import { User, Session } from '@supabase/supabase-js'
import { supabase, Profile } from '@/lib/supabase'
import { setAccessToken } from '@/lib/auth-store'

interface AuthContextType {
  user: User | null
  profile: Profile | null
  loading: boolean
  isPro: boolean
  tier: 'free' | 'pro' | 'anonymous'
  signInWithGoogle: () => Promise<void>
  signInWithApple: () => Promise<void>
  signOut: () => void
  refreshProfile: () => Promise<void>
  accessToken: string | null
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchProfile = useCallback(async (userId: string) => {
    try {
      const { data } = await supabase
        .from('profiles')
        .select('*')
        .eq('id', userId)
        .single()
      setProfile(data)
    } catch {
      // Profile fetch failed, leave as null
    }
  }, [])

  const applySession = useCallback((s: Session | null) => {
    setSession(s)
    setUser(s?.user ?? null)
    setAccessToken(s?.access_token ?? null)
  }, [])

  useEffect(() => {
    let mounted = true

    // E2E test auth bypass
    if (process.env.NODE_ENV !== 'production') {
      const testUser = typeof window !== 'undefined'
        ? localStorage.getItem('__test_auth_user')
        : null
      if (testUser) {
        try {
          setUser(JSON.parse(testUser) as User)
          setLoading(false)
          return
        } catch { /* fall through */ }
      }
    }

    // With the standard createClient (localStorage-based), getSession()
    // reads from localStorage synchronously — it does NOT hang.
    supabase.auth.getSession().then(({ data: { session: s } }) => {
      if (mounted) {
        applySession(s)
        if (s?.user) fetchProfile(s.user.id)
        setLoading(false)
      }
    }).catch(() => {
      if (mounted) setLoading(false)
    })

    // This listener fires on: SIGNED_IN, SIGNED_OUT, TOKEN_REFRESHED, USER_UPDATED.
    // With the standard client, TOKEN_REFRESHED fires reliably every ~55 minutes
    // (before the 1-hour access token expires).
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, s) => {
        if (mounted) {
          applySession(s)
          if (s?.user) {
            await fetchProfile(s.user.id)
          } else {
            setProfile(null)
          }
        }
      }
    )

    return () => {
      mounted = false
      subscription.unsubscribe()
    }
  }, [fetchProfile, applySession])

  async function signInWithGoogle() {
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/auth/callback` }
    })
  }

  async function signInWithApple() {
    await supabase.auth.signInWithOAuth({
      provider: 'apple',
      options: { redirectTo: `${window.location.origin}/auth/callback` }
    })
  }

  function signOut() {
    setProfile(null)
    applySession(null)
    if (typeof window !== 'undefined') {
      localStorage.removeItem('comparison-storage')
    }
    supabase.auth.signOut().catch(() => {})
  }

  const tier: 'free' | 'pro' | 'anonymous' = user ? (profile?.user_tier || 'free') : 'anonymous'
  const isPro = tier === 'pro'

  const refreshProfile = useCallback(async () => {
    if (user) await fetchProfile(user.id)
  }, [user, fetchProfile])

  const accessToken = session?.access_token ?? null

  return (
    <AuthContext.Provider value={{
      user, profile, loading, isPro, tier,
      signInWithGoogle, signInWithApple, signOut, refreshProfile,
      accessToken,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
