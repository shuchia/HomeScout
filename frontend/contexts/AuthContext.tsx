'use client'
import { createContext, useContext, useEffect, useState, useCallback, useRef, ReactNode } from 'react'
import { User, Session } from '@supabase/supabase-js'
import { supabase, Profile } from '@/lib/supabase'
import { setAccessToken } from '@/lib/auth-store'
import { useComparison } from '@/hooks/useComparison'

interface AuthContextType {
  user: User | null
  profile: Profile | null
  loading: boolean
  profileLoading: boolean
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
  const [profileLoading, setProfileLoading] = useState(false)
  const loadingRef = useRef(true)

  const fetchProfile = useCallback(async (userId: string) => {
    setProfileLoading(true)
    try {
      const { data } = await supabase
        .from('profiles')
        .select('*')
        .eq('id', userId)
        .single()
      setProfile(data)
    } catch {
      // Profile fetch failed, leave as null
    } finally {
      setProfileLoading(false)
    }
  }, [])

  const applySession = useCallback((s: Session | null) => {
    setSession(s)
    setUser(s?.user ?? null)
    setAccessToken(s?.access_token ?? null, s?.expires_at)
  }, [])

  const finishLoading = useCallback(() => {
    loadingRef.current = false
    setLoading(false)
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
          queueMicrotask(() => {
            if (!mounted) return
            setUser(parsedUser)
            if (parsedProfile) setProfile(parsedProfile)
            finishLoading()
          })
          return
        } catch { /* fall through */ }
      }
    }

    // Safety timeout — guarantees the UI is never stuck loading
    const timeout = setTimeout(() => {
      if (mounted && loadingRef.current) {
        console.warn('Auth initialization timed out — continuing without session')
        finishLoading()
      }
    }, 5000)

    async function initializeAuth() {
      try {
        const { data: { session: cachedSession } } = await supabase.auth.getSession()

        if (!mounted) return

        if (!cachedSession) {
          applySession(null)
          return
        }

        // Check if the access token is expired or expiring soon
        const expiresAt = cachedSession.expires_at ?? 0
        const isExpired = Date.now() / 1000 > expiresAt - 60

        let activeSession: Session | null = cachedSession

        if (isExpired) {
          // Token expired during idle (e.g., overnight) — must refresh
          try {
            const { data: { session: refreshed }, error } = await supabase.auth.refreshSession()
            if (refreshed && !error) {
              activeSession = refreshed
            } else {
              // Refresh token also expired — session is permanently dead
              activeSession = null
              await supabase.auth.signOut().catch(() => {})
            }
          } catch {
            activeSession = null
            await supabase.auth.signOut().catch(() => {})
          }
        }

        if (!mounted) return

        if (activeSession) {
          applySession(activeSession)
          // Fetch profile but don't block loading on it
          fetchProfile(activeSession.user.id)
        } else {
          applySession(null)
          setProfile(null)
        }
      } catch {
        if (mounted) {
          applySession(null)
          setProfile(null)
        }
      } finally {
        // ALWAYS finish loading, no matter what happened above
        if (mounted) {
          clearTimeout(timeout)
          finishLoading()
        }
      }
    }

    initializeAuth()

    // Listen for auth state changes (sign-in, sign-out, token refresh)
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, s) => {
        if (!mounted) return

        if (event === 'SIGNED_OUT') {
          applySession(null)
          setProfile(null)
          return
        }

        if (event === 'TOKEN_REFRESHED' && !s) {
          // Refresh failed — session is dead, sign out
          applySession(null)
          setProfile(null)
          await supabase.auth.signOut().catch(() => {})
          return
        }

        // SIGNED_IN, TOKEN_REFRESHED (success), INITIAL_SESSION, USER_UPDATED
        if (s) {
          applySession(s)
          // Fire-and-forget profile fetch — don't block auth state updates
          fetchProfile(s.user.id)
        }
      }
    )

    return () => {
      mounted = false
      clearTimeout(timeout)
      subscription.unsubscribe()
    }
  }, [fetchProfile, applySession, finishLoading])

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
    setProfileLoading(false)
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
      user, profile, loading, profileLoading, isPro, tier,
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
