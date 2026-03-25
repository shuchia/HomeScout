'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { createTour, ApiError } from '@/lib/api'
import Link from 'next/link'

interface TourPromptProps {
  apartmentId: string
  alreadyInTours?: boolean
  onStarted?: () => void
}

export function TourPrompt({ apartmentId, alreadyInTours = false, onStarted }: TourPromptProps) {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [inTours, setInTours] = useState(alreadyInTours)
  const [error, setError] = useState<string | null>(null)

  if (inTours) {
    return (
      <Link
        href="/tours"
        className="inline-flex items-center gap-1.5 text-green-600 bg-green-50 border border-green-200 rounded-lg px-3 py-1.5 text-sm hover:bg-green-100 transition-colors"
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
        In Tours
      </Link>
    )
  }

  async function handleClick() {
    setLoading(true)
    setError(null)
    try {
      await createTour(apartmentId)
      setInTours(true)
      if (onStarted) {
        onStarted()
      } else {
        router.push('/tours')
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setInTours(true)
      } else {
        setError('Could not start tour. Try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <button
        onClick={handleClick}
        disabled={loading}
        className="inline-flex items-center gap-1.5 text-[var(--color-primary)] border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 rounded-lg px-3 py-1.5 text-sm transition-colors disabled:opacity-50"
      >
        {loading ? (
          <>
            <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Starting...
          </>
        ) : (
          <>
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
            </svg>
            Start Touring
          </>
        )}
      </button>
      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
    </div>
  )
}
