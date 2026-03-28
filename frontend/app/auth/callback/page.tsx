'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'

export default function AuthCallback() {
  const router = useRouter()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let redirected = false
    let authSubscription: { unsubscribe: () => void } | null = null

    const safeRedirect = () => {
      if (redirected) return
      redirected = true
      authSubscription?.unsubscribe()
      router.replace('/')
    }

    // Safety: ALWAYS redirect within 5 seconds, no matter what
    const safetyTimeout = setTimeout(() => {
      if (!redirected) {
        console.warn('Auth callback timed out — redirecting')
        setError('Sign-in is taking too long. Redirecting...')
        setTimeout(safeRedirect, 1000)
      }
    }, 5000)

    // With detectSessionInUrl: true, Supabase auto-exchanges the PKCE code
    // during client init. Do NOT manually call exchangeCodeForSession —
    // that races with the auto-exchange and fails when the code is consumed.
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if (session) {
        safeRedirect()
      }
    })
    authSubscription = data.subscription

    // Also check if session is already available (exchange may have
    // completed before our listener was set up)
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) safeRedirect()
    }).catch(() => {})

    return () => {
      clearTimeout(safetyTimeout)
      authSubscription?.unsubscribe()
    }
  }, [router])

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        {error ? (
          <p className="text-red-600">{error}</p>
        ) : (
          <>
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--color-primary)] mx-auto mb-4"></div>
            <p>Signing you in...</p>
          </>
        )}
      </div>
    </div>
  )
}
