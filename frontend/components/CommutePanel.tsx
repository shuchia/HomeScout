'use client'

import Link from 'next/link'
import { CommuteTime } from '@/types/apartment'

const fmt = (m?: number | null): string | null => (m == null ? null : `${m} min`)

/** One-line "12 min drive · 24 min transit · 35 min walk" summary. Exported so
 *  the compare table can reuse the same formatting. */
export function commuteModeLine(c: CommuteTime): string {
  const parts = [
    fmt(c.minutes_drive) && `${fmt(c.minutes_drive)} drive`,
    fmt(c.minutes_transit) && `${fmt(c.minutes_transit)} transit`,
    fmt(c.minutes_walk) && `${fmt(c.minutes_walk)} walk`,
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : 'No route found'
}

/**
 * Renders commute times from one apartment to the user's saved locations.
 * Presentational only — returns null when there's nothing to show.
 * Styling mirrors CostBreakdownPanel for visual consistency.
 */
export default function CommutePanel({ commutes }: { commutes?: CommuteTime[] | null }) {
  if (!commutes || commutes.length === 0) return null
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
        Commute
      </h3>
      <ul className="space-y-1.5">
        {commutes.map((c) => (
          <li key={`${c.location_type}-${c.label}`} className="flex flex-col">
            <span className="text-sm font-medium text-gray-800">{c.label}</span>
            <span className="text-xs text-gray-600">{commuteModeLine(c)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * Subtle prompt shown once on a view when the signed-in user hasn't saved any
 * work/school addresses yet. Views render this when hasLocations === false.
 */
export function CommutePrompt() {
  return (
    <p className="text-xs text-gray-400">
      <Link href="/settings" className="text-[var(--color-primary)] hover:underline">
        Add a work or school address
      </Link>{' '}
      to see commute times.
    </p>
  )
}
