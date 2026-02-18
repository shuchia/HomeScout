'use client'
import { useAuth } from '@/contexts/AuthContext'

export function AuthButton() {
  const { user, loading, signInWithGoogle } = useAuth()

  if (loading) {
    return <div className="w-20 h-9 bg-gray-200 animate-pulse rounded-lg"></div>
  }

  if (user) {
    return null // UserMenu will handle signed-in state
  }

  return (
    <button
      onClick={signInWithGoogle}
      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
    >
      Sign In
    </button>
  )
}
