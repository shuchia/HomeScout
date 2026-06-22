import { useState, useEffect } from 'react'
import { getCommuteTimes, listUserLocations } from '@/lib/api'
import { CommuteTime } from '@/types/apartment'
import { useAuth } from '@/contexts/AuthContext'

/**
 * Shared hook for the commute calculator on the shortlist views (tour detail,
 * compare, favorites). Resolves whether the user has any saved locations, and
 * if so fetches commute times for the given apartments.
 *
 * Returns:
 *  - byApt:        apartment_id -> CommuteTime[]
 *  - hasLocations: null while unknown, false if signed-out / no saved addresses
 *  - loading:      true while fetching
 */
export function useCommuteTimes(apartmentIds: string[]) {
  const { user } = useAuth()
  const [byApt, setByApt] = useState<Record<string, CommuteTime[]>>({})
  const [hasLocations, setHasLocations] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(false)

  // Stable dependency so the effect doesn't re-run on array identity changes.
  const key = apartmentIds.slice().sort().join(',')

  useEffect(() => {
    let cancelled = false

    if (!user) {
      setHasLocations(false)
      setByApt({})
      return
    }
    if (!key) return

    setLoading(true)
    ;(async () => {
      try {
        const locs = await listUserLocations()
        if (cancelled) return
        setHasLocations(locs.length > 0)
        if (locs.length === 0) {
          setByApt({})
          return
        }
        const times = await getCommuteTimes(key.split(','))
        if (!cancelled) setByApt(times)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
    // `key` encodes apartmentIds; `user` gates the whole thing.
  }, [key, user])

  return { byApt, hasLocations, loading }
}
