'use client'
import { useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import { Suspense } from 'react'

function CallbackHandler() {
  const router = useRouter()
  const searchParams = useSearchParams()

  useEffect(() => {
    async function handleCallback() {
      // PKCE flow: exchange the code from the URL query params
      const code = searchParams.get('code')
      if (code) {
        const { error } = await supabase.auth.exchangeCodeForSession(code)
        if (error) {
          console.error('Auth code exchange failed:', error)
        }
        router.replace('/')
        return
      }

      // Implicit flow fallback: tokens arrive in the URL hash.
      // The Supabase client picks these up automatically, so just
      // wait for the SIGNED_IN event.
      const { data: { subscription } } = supabase.auth.onAuthStateChange((event) => {
        if (event === 'SIGNED_IN') {
          router.replace('/')
        }
      })

      // Safety timeout — if nothing fires within 5s, go home anyway
      const timeout = setTimeout(() => router.replace('/'), 5000)

      return () => {
        subscription.unsubscribe()
        clearTimeout(timeout)
      }
    }

    handleCallback()
  }, [router, searchParams])

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
        <p>Signing you in...</p>
      </div>
    </div>
  )
}

export default function AuthCallback() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p>Signing you in...</p>
        </div>
      </div>
    }>
      <CallbackHandler />
    </Suspense>
  )
}
