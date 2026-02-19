'use client'
import { useFavorites } from '@/hooks/useFavorites'
import { useAuth } from '@/contexts/AuthContext'
import ApartmentCard from '@/components/ApartmentCard'
import Link from 'next/link'
import { Apartment, ApartmentWithScore } from '@/types/apartment'

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

  // Debug logging
  console.log('FavoritesPage render:', {
    user: user?.id,
    authLoading,
    loading,
    favoritesCount: favorites.length,
    favorites: favorites.map(f => ({ id: f.id, apartment_id: f.apartment_id, hasApartment: !!f.apartment }))
  })

  if (authLoading) {
    return (
      <div className="max-w-6xl mx-auto p-6">
        <div className="animate-pulse">
          <div className="h-8 w-48 bg-gray-200 rounded mb-6"></div>
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
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
          className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
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
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-64 bg-gray-200 rounded-lg animate-pulse"></div>
          ))}
        </div>
      ) : favorites.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-600 mb-4">You haven&apos;t saved any favorites yet.</p>
          <Link
            href="/"
            className="text-blue-600 hover:underline"
          >
            Start searching for apartments
          </Link>
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
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
                <ApartmentCard apartment={toApartmentWithScore(fav.apartment)} />
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
