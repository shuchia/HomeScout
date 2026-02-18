'use client'

import { useRouter } from 'next/navigation'
import { useComparison } from '@/hooks/useComparison'

/**
 * ComparisonBar - Sticky footer showing selected apartments for comparison
 * Shows 3 slots for apartments, with indicators for filled slots
 * Provides clear and compare buttons
 */
export function ComparisonBar() {
  const { apartmentIds, clearComparison } = useComparison()
  const router = useRouter()

  // Don't render if no apartments are selected
  if (apartmentIds.length === 0) return null

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-white border-t shadow-lg p-4 z-50">
      <div className="max-w-6xl mx-auto flex items-center justify-between">
        {/* Selection indicator */}
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-600">
            {apartmentIds.length} of 3 selected
          </span>
          {/* Visual slots for comparison */}
          <div className="flex gap-2">
            {[0, 1, 2].map(i => (
              <div
                key={i}
                className={`w-8 h-8 rounded border-2 flex items-center justify-center ${
                  apartmentIds[i]
                    ? 'bg-blue-100 border-blue-500'
                    : 'border-dashed border-gray-300'
                }`}
              >
                {apartmentIds[i] && (
                  <span className="text-blue-600 text-xs font-bold">{i + 1}</span>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex gap-3">
          <button
            onClick={clearComparison}
            className="px-4 py-2 text-gray-600 hover:text-gray-800 transition-colors"
          >
            Clear
          </button>
          <button
            onClick={() => router.push('/compare')}
            disabled={apartmentIds.length < 2}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium
                       hover:bg-blue-700 transition-colors
                       disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            Compare ({apartmentIds.length})
          </button>
        </div>
      </div>
    </div>
  )
}
