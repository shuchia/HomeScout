'use client'

import { useComparison } from '@/hooks/useComparison'

interface CompareButtonProps {
  apartmentId: string
  className?: string
}

/**
 * CompareButton - Toggle button to add/remove an apartment from comparison
 * Shows different states: in comparison, can add, or at max capacity
 */
export function CompareButton({ apartmentId, className = '' }: CompareButtonProps) {
  const { addToCompare, removeFromCompare, isInComparison, apartmentIds } = useComparison()
  const inComparison = isInComparison(apartmentId)
  const canAddMore = apartmentIds.length < 3

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation() // Prevent card click events
    if (inComparison) {
      removeFromCompare(apartmentId)
    } else if (canAddMore) {
      addToCompare(apartmentId)
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={!inComparison && !canAddMore}
      className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
        inComparison
          ? 'bg-blue-100 text-blue-700 hover:bg-blue-200'
          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
      } disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
      title={
        inComparison
          ? 'Remove from comparison'
          : canAddMore
          ? 'Add to comparison'
          : 'Maximum 3 apartments can be compared'
      }
    >
      {inComparison ? (
        <span className="flex items-center gap-1">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          Comparing
        </span>
      ) : (
        <span className="flex items-center gap-1">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Compare
        </span>
      )}
    </button>
  )
}
