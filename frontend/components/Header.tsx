'use client'
import Link from 'next/link'
import { AuthButton } from './AuthButton'
import { UserMenu } from './UserMenu'
import { useAuth } from '@/contexts/AuthContext'

export function Header() {
  const { user } = useAuth()

  return (
    <header className="border-b bg-white sticky top-0 z-40">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link href="/" className="text-xl font-bold text-blue-600">
          HomeScout
        </Link>

        <nav className="flex items-center gap-6">
          <Link href="/" className="text-gray-600 hover:text-gray-900">
            Search
          </Link>
          {user && (
            <>
              <Link href="/favorites" className="text-gray-600 hover:text-gray-900">
                Favorites
              </Link>
              <Link href="/compare" className="text-gray-600 hover:text-gray-900">
                Compare
              </Link>
            </>
          )}
          <AuthButton />
          <UserMenu />
        </nav>
      </div>
    </header>
  )
}
