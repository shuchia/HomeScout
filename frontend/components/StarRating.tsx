'use client'

interface StarRatingProps {
  value: number | null
  onChange?: (rating: number) => void
  size?: 'sm' | 'md' | 'lg'
  readOnly?: boolean
}

const sizeClasses = {
  sm: 'text-lg',
  md: 'text-2xl',
  lg: 'text-3xl',
} as const

export default function StarRating({
  value,
  onChange,
  size = 'md',
  readOnly = false,
}: StarRatingProps) {
  const stars = [1, 2, 3, 4, 5]

  return (
    <div className="flex items-center gap-0.5" role="group" aria-label="Star rating">
      {stars.map((star) => {
        const filled = value !== null && star <= value
        return (
          <button
            key={star}
            type="button"
            disabled={readOnly}
            onClick={() => onChange?.(star)}
            className={`
              ${sizeClasses[size]}
              min-w-[2.5rem] min-h-[2.5rem]
              flex items-center justify-center
              transition-colors
              ${filled ? 'text-yellow-400' : 'text-gray-300'}
              ${readOnly ? 'cursor-default' : 'cursor-pointer hover:text-yellow-300 active:scale-110'}
              disabled:opacity-100
              select-none
            `}
            aria-label={`${star} star${star > 1 ? 's' : ''}`}
          >
            {filled ? '\u2605' : '\u2606'}
          </button>
        )
      })}
      {value !== null && (
        <span className="ml-1 text-sm text-gray-500">{value}/5</span>
      )}
    </div>
  )
}
