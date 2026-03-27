'use client'
import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react'
import { User, Session } from '@supabase/supabase-js'
import { supabase, Profile } from '@/lib/supabase'
import { setAccessToken } from '@/lib/auth-store'
import { useComparison } from '@/hooks/useComparison'

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
    setAccessToken(s?.access_token ?? null, s?.expires_at)
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
          const parsedUser = JSON.parse(testUser) as User
          const testProfile = typeof window !== 'undefined'
            ? localStorage.getItem('__test_auth_profile')
            : null
          let parsedProfile: Profile | null = null
          if (testProfile) {
            try {
              parsedProfile = JSON.parse(testProfile) as Profile
            } catch { /* ignore parse errors */ }
          }
          // Defer setState to avoid synchronous setState in effect
          queueMicrotask(() => {
            if (!mounted) return
            setUser(parsedUser)
            if (parsedProfile) setProfile(parsedProfile)
            setLoading(false)
          })
          return
        } catch { /* fall through */ }
      }
    }

    // 15-second timeout to prevent infinite loading on stale sessions
    // Don't sign out — just stop loading so the UI is usable
    const timeout = setTimeout(() => {
      if (mounted && loading) {
        console.warn('Auth initialization timed out — continuing without session')
        setLoading(false)
      }
    }, 15000)

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

        // Handle token refresh failure — don't sign out immediately,
        // keep the existing session so the UI stays usable
        if (event === 'TOKEN_REFRESHED' && !s) {
          console.warn('Token refresh failed — keeping existing session')
          return
        }

        // Only update session if we actually got a new one,
        // don't clear on transient null during refresh
        if (s) {
          applySession(s)
          await fetchProfile(s.user.id)
        } else if (event === 'SIGNED_OUT') {
          applySession(null)
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
    useComparison.getState().clearComparison()
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
