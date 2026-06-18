'use client'

import { useEffect, useState } from 'react'
import { generateDayPlan } from '@/lib/api'
import UpgradePrompt from '@/components/UpgradePrompt'

// localStorage key for the day-plan starting address. Persisted across
// visits because users typically tour from the same place (hotel, current
// home, airport) — retyping it every time is friction. Stored per-browser,
// not per-user, since this is preferences not data.
const STARTING_ADDRESS_KEY = 'snugd-day-plan-starting-address'

interface DayPlannerProps {
  date: string              // ISO date (YYYY-MM-DD)
  tourIds: string[]         // tour IDs on this date
  isPro: boolean
  profileLoading?: boolean
}

interface DayPlanResult {
  tours_ordered: Array<Record<string, unknown>>
  travel_notes: string[]
  tips: string[]
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

export default function DayPlanner({ date, tourIds, isPro, profileLoading }: DayPlannerProps) {
  const [plan, setPlan] = useState<DayPlanResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [startingAddress, setStartingAddress] = useState('')

  // Hydrate the saved starting address on mount. Skip on the SSR pass
  // (window check) to avoid a hydration mismatch.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const saved = window.localStorage.getItem(STARTING_ADDRESS_KEY)
    if (saved) setStartingAddress(saved)
  }, [])

  const handleStartingAddressChange = (value: string) => {
    setStartingAddress(value)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STARTING_ADDRESS_KEY, value)
    }
  }

  const handleGeneratePlan = async () => {
    try {
      setLoading(true)
      setError(null)
      const result = await generateDayPlan(date, tourIds, startingAddress || undefined)
      setPlan(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate day plan')
    } finally {
      setLoading(false)
    }
  }

  if (!isPro && !profileLoading) {
    return (
      <div className="mb-4">
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">
            Day Plan &mdash; {formatDate(date)}
          </h3>
          <p className="text-xs text-gray-500 mb-3">
            {tourIds.length} tours on this day. Get an AI-optimized route and schedule.
          </p>
          <UpgradePrompt feature="AI day planning" inline />
        </div>
      </div>
    )
  }

  if (profileLoading) {
    return (
      <div className="mb-4">
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">
            Day Plan &mdash; {formatDate(date)}
          </h3>
          <div className="h-8 bg-gray-100 rounded-lg animate-pulse" />
        </div>
      </div>
    )
  }

  return (
    <div className="mb-4">
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-1">
          Day Plan &mdash; {formatDate(date)}
        </h3>
        <p className="text-xs text-gray-500 mb-3">
          {tourIds.length} tours scheduled. Let AI optimize your route.
        </p>

        {!plan && !loading && (
          <>
            {/* Optional starting point so the route optimizer can anchor
                the first leg. Persisted in localStorage — users typically
                tour from the same place (hotel/home/airport). */}
            <div className="mb-3">
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Starting from <span className="text-gray-400 font-normal">(optional)</span>
              </label>
              <input
                type="text"
                value={startingAddress}
                onChange={(e) => handleStartingAddressChange(e.target.value)}
                placeholder="e.g., 123 Main St, Pittsburgh PA, or hotel name"
                className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)] focus:border-[var(--color-primary)]"
              />
              <p className="text-[10px] text-gray-400 mt-0.5">Saved on this device for next time.</p>
            </div>
            <button
              onClick={handleGeneratePlan}
              className="w-full py-2 px-4 bg-[var(--color-primary)] text-white text-sm font-medium rounded-lg hover:bg-[var(--color-primary-light)] transition-colors"
            >
              Plan This Day
            </button>
          </>
        )}

        {loading && (
          <div className="flex items-center justify-center py-4">
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-[var(--color-primary)] mr-2"></div>
            <span className="text-sm text-gray-500">Generating plan...</span>
          </div>
        )}

        {error && (
          <div className="text-center py-3">
            <p className="text-sm text-red-600 mb-2">{error}</p>
            <button
              onClick={handleGeneratePlan}
              className="text-sm text-[var(--color-primary)] hover:underline"
            >
              Try again
            </button>
          </div>
        )}

        {plan && (
          <div className="space-y-4">
            {/* Ordered Tour List */}
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Suggested Order
              </h4>
              <ol className="space-y-2">
                {plan.tours_ordered.map((tour, idx) => (
                  <li key={idx} className="flex items-start gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full bg-emerald-100 text-[var(--color-primary)] text-xs font-bold flex items-center justify-center">
                      {idx + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">
                        {String(tour.address || tour.name || `Tour ${idx + 1}`)}
                      </p>
                      {tour.suggested_time ? (
                        <p className="text-xs text-gray-500">
                          {String(tour.suggested_time)}
                        </p>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ol>
            </div>

            {/* Travel Notes */}
            {plan.travel_notes && plan.travel_notes.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Travel Notes
                </h4>
                <ul className="space-y-1">
                  {plan.travel_notes.map((note, idx) => (
                    <li key={idx} className="text-xs text-gray-600 flex items-start gap-1.5">
                      <span className="text-gray-400 mt-0.5 flex-shrink-0">&#8226;</span>
                      {note}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Tips */}
            {plan.tips && plan.tips.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Tips
                </h4>
                <ul className="space-y-1">
                  {plan.tips.map((tip, idx) => (
                    <li key={idx} className="text-xs text-gray-600 flex items-start gap-1.5">
                      <span className="text-[var(--color-primary)] mt-0.5 flex-shrink-0">*</span>
                      {tip}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Download .ics placeholder */}
            <div className="pt-2 border-t border-gray-100">
              <button
                disabled
                className="w-full py-2 px-4 bg-gray-100 text-gray-400 text-sm font-medium rounded-lg cursor-not-allowed"
              >
                Download .ics (coming soon)
              </button>
            </div>

            {/* Regenerate */}
            <button
              onClick={handleGeneratePlan}
              className="w-full py-1.5 text-xs text-[var(--color-primary)] hover:underline"
            >
              Regenerate plan
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
