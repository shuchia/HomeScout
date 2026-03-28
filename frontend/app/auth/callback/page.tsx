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

    async function handleCallback() {
      try {
        // Exchange PKCE code for session
        const params = new URLSearchParams(window.location.search)
        const code = params.get('code')

        if (code) {
          const { error } = await supabase.auth.exchangeCodeForSession(code)
          if (error) {
            console.error('Auth code exchange failed:', error.message)
            // Exchange failed, but check if session exists anyway
            // (detectSessionInUrl may have handled it)
            const { data: { session } } = await supabase.auth.getSession()
            if (session) {
              safeRedirect()
              return
            }
            setError('Sign-in failed. Please try again.')
            setTimeout(safeRedirect, 2000)
            return
          }
        }

        // Code exchanged (or no code). Check for session.
        const { data: { session } } = await supabase.auth.getSession()
        if (session) {
          safeRedirect()
          return
        }

        // No session yet — wait for auth state change
        const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
          if (session) {
            subscription.unsubscribe()
            safeRedirect()
          }
        })

        // Safety timeout
        setTimeout(() => {
          subscription.unsubscribe()
          safeRedirect()
        }, 5000)
      } catch (err) {
        console.error('Auth callback error:', err)
        setError('Sign-in failed. Redirecting...')
        setTimeout(safeRedirect, 2000)
      }
    }

    handleCallback()
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
