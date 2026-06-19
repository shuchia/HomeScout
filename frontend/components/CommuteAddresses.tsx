'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { listUserLocations, createUserLocation, deleteUserLocation } from '@/lib/api'
import { geocodeSearch, GeocodeSuggestion } from '@/lib/geocode'
import { UserLocation } from '@/types/apartment'

/**
 * Settings section for managing saved work/school addresses used by the commute
 * calculator. Geocoding reuses the existing Nominatim helper (geocodeSearch),
 * so the backend only ever stores lat/lng.
 */
export default function CommuteAddresses() {
  const [locations, setLocations] = useState<UserLocation[]>([])
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Add-form state
  const [type, setType] = useState<'work' | 'school'>('work')
  const [label, setLabel] = useState('')
  const [query, setQuery] = useState('')
  const [picked, setPicked] = useState<GeocodeSuggestion | null>(null)
  const [suggestions, setSuggestions] = useState<GeocodeSuggestion[]>([])
  const [geoLoading, setGeoLoading] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    try {
      setLocations(await listUserLocations())
    } finally {
      setLoading(false)
    }
  }

  const onQuery = useCallback((text: string) => {
    setQuery(text)
    setPicked(null)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (text.length < 3) {
      setSuggestions([])
      return
    }
    debounceRef.current = setTimeout(async () => {
      setGeoLoading(true)
      try {
        setSuggestions(await geocodeSearch(text))
      } finally {
        setGeoLoading(false)
      }
    }, 500)
  }, [])

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!picked) {
      setError('Pick an address from the suggestions.')
      return
    }
    if (!label.trim()) {
      setError('Give it a label, like “Office” or “Campus”.')
      return
    }
    setAdding(true)
    try {
      const loc = await createUserLocation({
        location_type: type,
        label: label.trim(),
        address: picked.display_name,
        latitude: picked.lat,
        longitude: picked.lng,
      })
      setLocations((prev) => [loc, ...prev])
      setLabel('')
      setQuery('')
      setPicked(null)
      setSuggestions([])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save location.')
    } finally {
      setAdding(false)
    }
  }

  async function handleDelete(id: string) {
    setLocations((prev) => prev.filter((l) => l.id !== id))
    try {
      await deleteUserLocation(id)
    } catch {
      load() // restore on failure
    }
  }

  return (
    <section className="bg-white rounded-lg border p-6 mb-6">
      <h2 className="text-lg font-semibold mb-1">Commute Addresses</h2>
      <p className="text-sm text-gray-500 mb-4">
        Add the places you commute to. We&rsquo;ll show drive, transit, and walk
        times from listings you tour, favorite, or compare.
      </p>

      {/* Saved list */}
      {loading ? (
        <div className="h-10 bg-gray-100 rounded animate-pulse mb-4" />
      ) : locations.length > 0 ? (
        <ul className="divide-y divide-gray-100 mb-5">
          {locations.map((loc) => (
            <li key={loc.id} className="flex items-center justify-between py-2.5">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">{loc.label}</span>
                  <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500">
                    {loc.location_type}
                  </span>
                </div>
                <p className="text-xs text-gray-500 truncate">{loc.address}</p>
              </div>
              <button
                type="button"
                onClick={() => handleDelete(loc.id)}
                className="text-xs text-red-600 hover:underline shrink-0 ml-3"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-gray-400 mb-5">No addresses saved yet.</p>
      )}

      {/* Add form */}
      <form onSubmit={handleAdd} className="space-y-3 border-t border-gray-100 pt-4">
        <div className="flex gap-2">
          <select
            value={type}
            onChange={(e) => setType(e.target.value as 'work' | 'school')}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
          >
            <option value="work">Work</option>
            <option value="school">School</option>
          </select>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Label (e.g. Office)"
            maxLength={80}
            className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
          />
        </div>

        <div className="relative">
          <input
            type="text"
            value={picked ? picked.display_name : query}
            onChange={(e) => onQuery(e.target.value)}
            placeholder="Search address…"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
          />
          {geoLoading && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">…</div>
          )}
          {!picked && suggestions.length > 0 && (
            <ul className="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
              {suggestions.map((s, i) => (
                <li key={i}>
                  <button
                    type="button"
                    onClick={() => {
                      setPicked(s)
                      setSuggestions([])
                    }}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 border-b border-gray-100 last:border-0"
                  >
                    {s.display_name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && <p className="text-xs text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={adding}
          className="bg-[var(--color-primary)] text-white px-4 py-2 rounded-lg text-sm hover:bg-[var(--color-primary-light)] disabled:opacity-50"
        >
          {adding ? 'Saving…' : 'Add address'}
        </button>
      </form>
    </section>
  )
}
