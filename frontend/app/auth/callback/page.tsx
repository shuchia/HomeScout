'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'

export default function AuthCallback() {
  const router = useRouter()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let redirected = false

    const safeRedirect = () => {
      if (redirected) return
      redirected = true
      router.replace('/')
    }

    // detectSessionInUrl (enabled on the Supabase client) automatically
    // processes auth tokens from the URL — hash fragments for implicit flow,
    // query params for PKCE. We do NOT call exchangeCodeForSession manually
    // because that races with detectSessionInUrl over the single-use code.
    //
    // Instead, we just listen for onAuthStateChange to confirm the session.
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event, session) => {
        if (session && (event === 'SIGNED_IN' || event === 'INITIAL_SESSION')) {
          safeRedirect()
        }
      }
    )

    // Also check if a session already exists (detectSessionInUrl may have
    // already processed it before our listener was set up)
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        safeRedirect()
      }
    })

    // Safety timeout — never leave the user stuck on this page
    const timeout = setTimeout(() => {
      if (!redirected) {
        console.warn('Auth callback: timeout reached, redirecting')
        setError('Sign-in is taking longer than expected. Redirecting...')
        setTimeout(safeRedirect, 1500)
      }
    }, 8000)

    return () => {
      redirected = true
      subscription.unsubscribe()
      clearTimeout(timeout)
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
