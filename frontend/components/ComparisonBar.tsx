'use client'

import { useRouter, usePathname } from 'next/navigation'
import { useComparison } from '@/hooks/useComparison'
import { useAuth } from '@/contexts/AuthContext'

/**
 * ComparisonBar - Sticky footer showing selected apartments for comparison
 * Shows 3 slots for apartments, with indicators for filled slots
 * Only visible to authenticated users. Hidden on the compare page itself.
 */
export function ComparisonBar() {
  const { apartmentIds, clearComparison } = useComparison()
  const { user } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  // Don't render if: no apartments selected, not signed in, or already on compare page
  if (apartmentIds.length === 0 || !user || pathname === '/compare') return null

  return (
    <div className="fixed bottom-16 md:bottom-0 left-0 right-0 bg-white border-t shadow-lg p-3 sm:p-4 z-50">
      <div className="max-w-6xl mx-auto flex items-center justify-between">
        {/* Selection indicator */}
        <div className="flex items-center gap-2 sm:gap-4">
          {/* Slots - compact on mobile */}
          <div className="flex gap-1.5 sm:gap-2">
            {[0, 1, 2].map(i => (
              <div
                key={i}
                className={`w-7 h-7 sm:w-8 sm:h-8 rounded border-2 flex items-center justify-center ${
                  apartmentIds[i]
                    ? 'bg-emerald-100 border-[var(--color-primary)]'
                    : 'border-dashed border-gray-300'
                }`}
              >
                {apartmentIds[i] && (
                  <span className="text-[var(--color-primary)] text-xs font-bold">{i + 1}</span>
                )}
              </div>
            ))}
          </div>
          <span className="text-xs sm:text-sm text-gray-600 hidden sm:inline">
            {apartmentIds.length} of 3 selected
          </span>
        </div>

        {/* Action buttons */}
        <div className="flex gap-2 sm:gap-3">
          <button
            onClick={clearComparison}
            className="hidden sm:block px-4 py-2 text-gray-600 hover:text-gray-800 transition-colors"
          >
            Clear
          </button>
          {/* Mobile: X button instead of Clear text */}
          <button
            onClick={clearComparison}
            className="sm:hidden p-2 text-gray-400 hover:text-gray-600"
            title="Clear comparison"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          <button
            onClick={() => router.push('/compare')}
            disabled={apartmentIds.length < 2}
            className="px-4 sm:px-6 py-2 bg-[var(--color-primary)] text-white rounded-lg text-sm sm:text-base font-medium
                       hover:bg-[var(--color-primary-light)] transition-colors
                       disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            Compare ({apartmentIds.length})
          </button>
        </div>
      </div>
    </div>
  )
}
