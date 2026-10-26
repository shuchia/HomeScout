'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import LandingPage from '@/components/LandingPage'

// Supabase keeps the session under sb-<project>-auth-token. Seeing one means a
// returning user, so render nothing rather than flash the landing page while
// AuthContext confirms the session.
function hasStoredSession(): boolean {
  try {
    return Object.keys(localStorage).some(k => /^sb-.+-auth-token$/.test(k))
  } catch {
    return false
  }
}

/**
 * The front door: visitors get the landing page, signed-in users go straight
 * to search. The app itself lives at /search, so "Start searching" works
 * without signing in.
 */
export default function Home() {
  const { user, loading } = useAuth()
  const router = useRouter()
  const [returning, setReturning] = useState(false)

  useEffect(() => {
    // Intentional: localStorage is only readable after mount (react-hooks v6).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setReturning(hasStoredSession())
  }, [])

  useEffect(() => {
    if (user) router.replace('/search')
  }, [user, router])

  if (user || (loading && returning)) return null
  return <LandingPage />
}
