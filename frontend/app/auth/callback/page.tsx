'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'

export default function AuthCallback() {
  const router = useRouter()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let redirected = false
    let subscription: { unsubscribe: () => void } | null = null

    const safeRedirect = () => {
      if (redirected) return
      redirected = true
      subscription?.unsubscribe()
      router.replace('/')
    }

    async function handleCallback() {
      const params = new URLSearchParams(window.location.search)
      const code = params.get('code')

      if (!code) {
        // No code in URL — check if we already have a session (e.g., from hash fragment flow)
        const { data: { session } } = await supabase.auth.getSession()
        if (session) {
          safeRedirect()
        } else {
          setError('No authentication code found. Redirecting...')
          setTimeout(safeRedirect, 2000)
        }
        return
      }

      // Set up listener BEFORE exchanging code, so we don't miss the SIGNED_IN event
      const { data: { subscription: sub } } = supabase.auth.onAuthStateChange(
        (event, session) => {
          if (event === 'SIGNED_IN' && session) {
            safeRedirect()
          }
        }
      )
      subscription = sub

      // Exchange the PKCE code for a session.
      // detectSessionInUrl is disabled, so we are the sole consumer of this code.
      const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code)

      if (exchangeError) {
        console.error('Auth code exchange failed:', exchangeError.message)
        // Exchange failed — the onAuthStateChange listener won't fire.
        // Clean up and redirect with error.
        subscription?.unsubscribe()
        subscription = null
        setError('Sign-in failed. Please try again.')
        setTimeout(safeRedirect, 3000)
        return
      }

      // Exchange succeeded. The onAuthStateChange listener should fire SIGNED_IN
      // and call safeRedirect(). But add a safety timeout in case it doesn't.
      setTimeout(() => {
        if (!redirected) {
          // Listener didn't fire, but exchange succeeded — session should exist
          safeRedirect()
        }
      }, 3000)
    }

    handleCallback()

    // Overall safety timeout — never leave the user stuck on this page
    const overallTimeout = setTimeout(() => {
      if (!redirected) {
        console.warn('Auth callback: overall timeout reached, redirecting')
        safeRedirect()
      }
    }, 10000)

    return () => {
      redirected = true
      subscription?.unsubscribe()
      clearTimeout(overallTimeout)
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
