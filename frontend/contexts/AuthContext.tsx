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
          const testProfile = typeof window !== 'undefined'
            ? localStorage.getItem('__test_auth_profile')
            : null
          if (testProfile) {
            try {
              setProfile(JSON.parse(testProfile) as Profile)
            } catch { /* ignore parse errors */ }
          }
          setLoading(false)
          return
        } catch { /* fall through */ }
      }
    }

    // 5-second timeout to prevent infinite loading on stale sessions
    const timeout = setTimeout(() => {
      if (mounted && loading) {
        console.warn('Auth initialization timed out — clearing stale session')
        supabase.auth.signOut().catch(() => {})
        applySession(null)
        setProfile(null)
        setLoading(false)
      }
    }, 5000)

    supabase.auth.getSession().then(({ data: { session: s } }) => {
      clearTimeout(timeout)
      if (mounted) {
        applySession(s)
        if (s?.user) fetchProfile(s.user.id)
        setLoading(false)
      }
    }).catch(() => {
      clearTimeout(timeout)
      if (mounted) {
        supabase.auth.signOut().catch(() => {})
        applySession(null)
        setLoading(false)
      }
    })

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, s) => {
        if (!mounted) return

        // Handle token refresh failure
        if (event === 'TOKEN_REFRESHED' && !s) {
          console.warn('Token refresh failed — signing out')
          applySession(null)
          setProfile(null)
          return
        }

        applySession(s)
        if (s?.user) {
          await fetchProfile(s.user.id)
        } else {
          setProfile(null)
        }
      }
    )

    return () => {
      mounted = false
      clearTimeout(timeout)
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
