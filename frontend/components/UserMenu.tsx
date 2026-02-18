'use client'
import { useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import Link from 'next/link'
import Image from 'next/image'

export function UserMenu() {
  const { user, profile, signOut } = useAuth()
  const [isOpen, setIsOpen] = useState(false)

  if (!user) return null

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 p-2 rounded-lg hover:bg-gray-100"
      >
        {profile?.avatar_url ? (
          <Image
            src={profile.avatar_url}
            alt={profile.name || 'User'}
            width={32}
            height={32}
            className="w-8 h-8 rounded-full"
          />
        ) : (
          <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white">
            {profile?.name?.[0] || user.email?.[0] || '?'}
          </div>
        )}
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border z-20">
            <div className="p-3 border-b">
              <p className="font-medium truncate">{profile?.name || 'User'}</p>
              <p className="text-sm text-gray-500 truncate">{user.email}</p>
            </div>
            <nav className="p-2">
              <Link
                href="/favorites"
                className="block px-3 py-2 rounded hover:bg-gray-100"
                onClick={() => setIsOpen(false)}
              >
                My Favorites
              </Link>
              <Link
                href="/searches"
                className="block px-3 py-2 rounded hover:bg-gray-100"
                onClick={() => setIsOpen(false)}
              >
                Saved Searches
              </Link>
              <button
                onClick={() => { signOut(); setIsOpen(false) }}
                className="w-full text-left px-3 py-2 rounded hover:bg-gray-100 text-red-600"
              >
                Sign Out
              </button>
            </nav>
          </div>
        </>
      )}
    </div>
  )
}
