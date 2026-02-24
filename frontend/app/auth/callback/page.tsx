'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'

export default function AuthCallback() {
  const router = useRouter()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function handleCallback() {
      // Check for PKCE auth code in query params
      const params = new URLSearchParams(window.location.search)
      const code = params.get('code')

      if (code) {
        const { error } = await supabase.auth.exchangeCodeForSession(code)
        if (error) {
          console.error('Auth code exchange failed:', error)
          setError('Sign-in failed. Please try again.')
          setTimeout(() => router.replace('/'), 3000)
          return
        }
      }

      // For implicit flow, detectSessionInUrl handles the hash fragment
      // automatically. Wait briefly for onAuthStateChange to fire.

      // Either way, check if we now have a session
      const { data: { session } } = await supabase.auth.getSession()
      if (session) {
        router.replace('/')
        return
      }

      // If no session yet, wait for the auth state change
      const { data: { subscription } } = supabase.auth.onAuthStateChange((event) => {
        if (event === 'SIGNED_IN') {
          subscription.unsubscribe()
          router.replace('/')
        }
      })

      // Safety timeout
      setTimeout(() => {
        subscription.unsubscribe()
        router.replace('/')
      }, 5000)
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
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p>Signing you in...</p>
          </>
        )}
      </div>
    </div>
  )
}
