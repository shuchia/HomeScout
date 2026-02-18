'use client'
import { useState } from 'react'
import { useFavorites } from '@/hooks/useFavorites'
import { useAuth } from '@/contexts/AuthContext'

interface FavoriteButtonProps {
  apartmentId: string
  className?: string
}

export function FavoriteButton({ apartmentId, className = '' }: FavoriteButtonProps) {
  const { user, signInWithGoogle } = useAuth()
  const { isFavorite, addFavorite, removeFavorite } = useFavorites()
  const [loading, setLoading] = useState(false)

  const favorited = isFavorite(apartmentId)

  async function handleClick() {
    if (!user) {
      signInWithGoogle()
      return
    }

    setLoading(true)
    if (favorited) {
      await removeFavorite(apartmentId)
    } else {
      await addFavorite(apartmentId)
    }
    setLoading(false)
  }

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      className={`p-2 rounded-full transition-colors ${
        favorited
          ? 'bg-red-100 text-red-600 hover:bg-red-200'
          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
      } disabled:opacity-50 ${className}`}
      title={favorited ? 'Remove from favorites' : 'Add to favorites'}
    >
      <svg
        className="w-5 h-5"
        fill={favorited ? 'currentColor' : 'none'}
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
        />
      </svg>
    </button>
  )
}
