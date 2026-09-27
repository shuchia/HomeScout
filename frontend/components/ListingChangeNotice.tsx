'use client'
import { ListingChanges, AvailabilityStatus } from '@/types/savedListing'

const FIELD_LABELS: Record<string, string> = {
  rent: 'Rent',
  true_cost_monthly: 'True monthly cost',
  true_cost_move_in: 'Move-in cost',
  available_date: 'Available',
  bedrooms: 'Bedrooms',
  bathrooms: 'Bathrooms',
  sqft: 'Square feet',
}

const MONEY_FIELDS = new Set(['rent', 'true_cost_monthly', 'true_cost_move_in'])

function format(field: string, value: number | string | null): string {
  if (value === null || value === undefined || value === '') return '—'
  if (MONEY_FIELDS.has(field) && typeof value === 'number') {
    return `$${value.toLocaleString()}`
  }
  return String(value)
}

interface Props {
  changes: ListingChanges | null
  availability: AvailabilityStatus
  checkedAt: string | null
  onDismiss?: () => void
}

/**
 * Tells the user what moved since they saved a listing.
 *
 * Deliberately explicit rather than quietly updating the card. The price on a
 * saved listing is something the user has already reasoned about — it feeds
 * their comparison and their true-cost figure — so changing it underneath them
 * without saying so would undermine exactly the precision the product claims.
 *
 * Three distinct states, and conflating the last two would be the bug worth
 * avoiding:
 *   gone    — the source confirmed it is no longer listed
 *   unknown — we could not reach the source, and know nothing new
 *   live    — confirmed, with any material changes listed
 */
export function ListingChangeNotice({ changes, availability, checkedAt, onDismiss }: Props) {
  if (availability === 'gone') {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
        <span className="font-medium">No longer listed.</span>{' '}
        This listing was taken down at the source
        {checkedAt ? ` (checked ${new Date(checkedAt).toLocaleDateString()})` : ''}.
      </div>
    )
  }

  const entries = changes ? Object.entries(changes) : []
  if (entries.length === 0) return null

  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="font-medium">Changed since you saved this.</span>
          <ul className="mt-1 space-y-0.5">
            {entries.map(([field, change]) => (
              <li key={field}>
                {FIELD_LABELS[field] ?? field}:{' '}
                <span className="line-through opacity-70">{format(field, change.from)}</span>
                {' → '}
                <span className="font-medium">{format(field, change.to)}</span>
              </li>
            ))}
          </ul>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="shrink-0 text-amber-700 hover:text-amber-900 cursor-pointer"
            aria-label="Dismiss"
            title="Dismiss"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}
