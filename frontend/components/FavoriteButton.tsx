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

  async function handleClick(e: React.MouseEvent) {
    e.stopPropagation()
    e.preventDefault()

    console.log('FavoriteButton clicked!', { apartmentId, user: !!user, favorited })

    if (!user) {
      console.log('No user, triggering sign in...')
      signInWithGoogle()
      return
    }

    setLoading(true)
    try {
      if (favorited) {
        console.log('Removing favorite...')
        const result = await removeFavorite(apartmentId)
        console.log('Remove result:', result)
      } else {
        console.log('Adding favorite...')
        const result = await addFavorite(apartmentId)
        console.log('Add result:', result)
      }
    } catch (error) {
      console.error('Error toggling favorite:', error)
    }
    setLoading(false)
  }

  return (
    <button
      onClick={(e) => handleClick(e)}
      disabled={loading}
      className={`p-2 rounded-full transition-colors pointer-events-auto cursor-pointer ${
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
