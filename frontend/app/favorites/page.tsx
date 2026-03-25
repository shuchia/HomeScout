'use client'
import { useEffect, useState } from 'react'
import { useFavorites } from '@/hooks/useFavorites'
import { useAuth } from '@/contexts/AuthContext'
import ApartmentCard from '@/components/ApartmentCard'
import { TourPrompt } from '@/components/TourPrompt'
import Link from 'next/link'
import { Apartment, ApartmentWithScore } from '@/types/apartment'
import { listTours } from '@/lib/api'

// Convert a basic Apartment to ApartmentWithScore with default values
function toApartmentWithScore(apartment: Apartment): ApartmentWithScore {
  return {
    ...apartment,
    match_score: 100, // Favorited = 100% match
    reasoning: "You saved this apartment to your favorites.",
    highlights: ["Saved to favorites"]
  }
}

export default function FavoritesPage() {
  const { user, loading: authLoading, signInWithGoogle } = useAuth()
  const { favorites, loading } = useFavorites()
  const [touringApartmentIds, setTouringApartmentIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (!user) return
    listTours()
      .then(({ tours }) => {
        setTouringApartmentIds(new Set(tours.map(t => t.apartment_id)))
      })
      .catch(() => {
        // Silently fail — tour status is non-critical
      })
  }, [user])

  if (authLoading) {
    return (
      <div className="max-w-6xl mx-auto p-6">
        <div className="animate-pulse">
          <div className="h-8 w-48 bg-gray-200 rounded mb-6"></div>
          <div className="grid gap-6 sm:grid-cols-2">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-64 bg-gray-200 rounded-lg"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="max-w-6xl mx-auto p-6 text-center py-20">
        <h1 className="text-2xl font-bold mb-4">My Favorites</h1>
        <p className="text-gray-600 mb-6">Sign in to save your favorite apartments.</p>
        <button
          onClick={signInWithGoogle}
          className="px-6 py-3 bg-[var(--color-primary)] text-white rounded-lg hover:bg-[var(--color-primary-light)]"
        >
          Sign In with Google
        </button>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">My Favorites</h1>

      {loading ? (
        <div className="grid gap-6 sm:grid-cols-2">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-64 bg-gray-200 rounded-lg animate-pulse"></div>
          ))}
        </div>
      ) : favorites.length === 0 ? (
        <div className="text-center py-16">
          <div className="mx-auto w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
            <svg className="h-8 w-8 text-[var(--color-text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
            </svg>
          </div>
          <h3 className="text-lg font-medium text-[var(--color-text)] mb-2">
            No favorites yet
          </h3>
          <p className="text-[var(--color-text-secondary)] mb-4">
            Search for apartments and tap the heart icon to save your favorites here.
          </p>
          <Link
            href="/"
            className="inline-block px-6 py-2 bg-[var(--color-primary)] text-white rounded-lg hover:bg-[var(--color-primary-light)] transition-colors"
          >
            Start Searching
          </Link>
        </div>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2">
          {favorites.map(fav => (
            <div key={fav.id} className="relative">
              {fav.is_available === false && (
                <div className="absolute inset-0 bg-white/80 z-10 flex items-center justify-center rounded-lg">
                  <span className="px-3 py-1 bg-red-100 text-red-800 rounded-full text-sm font-medium">
                    No longer available
                  </span>
                </div>
              )}
              {fav.apartment ? (
                <>
                  <ApartmentCard apartment={toApartmentWithScore(fav.apartment)} />
                  <div className="mt-2">
                    <TourPrompt
                      apartmentId={fav.apartment_id}
                      alreadyInTours={touringApartmentIds.has(fav.apartment_id)}
                    />
                  </div>
                </>
              ) : (
                <div className="bg-gray-100 rounded-lg p-4 h-64 flex items-center justify-center">
                  <p className="text-gray-500 text-sm">
                    Apartment {fav.apartment_id} not found
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
