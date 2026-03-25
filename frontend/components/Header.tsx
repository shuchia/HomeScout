'use client'
import Link from 'next/link'
import { AuthButton } from './AuthButton'
import { UserMenu } from './UserMenu'
import { useAuth } from '@/contexts/AuthContext'

export function Header() {
  const { user } = useAuth()

  return (
    <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)] sticky top-0 z-40">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link href="/" className="text-2xl font-bold tracking-tight" style={{ color: 'var(--color-primary)' }}>
          snugd
        </Link>

        <nav className="hidden md:flex items-center gap-6">
          <Link href="/" className="text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors">
            Search
          </Link>
          {user && (
            <>
              <Link href="/favorites" className="text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors">
                Favorites
              </Link>
              <Link href="/tours" className="text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors">
                Tours
              </Link>
              <Link href="/compare" className="text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors">
                Compare
              </Link>
            </>
          )}
          <Link href="/pricing" className="text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors">
            Pricing
          </Link>
          <AuthButton />
          <UserMenu />
        </nav>

        <div className="flex md:hidden items-center gap-3">
          <AuthButton />
          <UserMenu />
        </div>
      </div>
    </header>
  )
}
