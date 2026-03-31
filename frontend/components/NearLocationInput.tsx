'use client'

import { useState, useRef, useCallback, useEffect } from 'react'
import { geocodeSearch, GeocodeSuggestion } from '@/lib/geocode'

interface NearLocation {
  lat: number
  lng: number
  label: string
}

interface NearLocationInputProps {
  value: NearLocation | null
  onChange: (location: NearLocation | null) => void
}

export default function NearLocationInput({ value, onChange }: NearLocationInputProps) {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<GeocodeSuggestion[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [showDropdown, setShowDropdown] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const handleSearch = useCallback((text: string) => {
    setQuery(text)
    if (debounceRef.current) clearTimeout(debounceRef.current)

    if (text.length < 3) {
      setSuggestions([])
      setShowDropdown(false)
      return
    }

    debounceRef.current = setTimeout(async () => {
      setIsLoading(true)
      try {
        const results = await geocodeSearch(text)
        setSuggestions(results)
        setShowDropdown(results.length > 0)
      } finally {
        setIsLoading(false)
      }
    }, 500)
  }, [])

  const handleSelect = (suggestion: GeocodeSuggestion) => {
    const label = suggestion.display_name.split(',').slice(0, 2).join(',').trim()
    onChange({ lat: suggestion.lat, lng: suggestion.lng, label })
    setQuery(label)
    setShowDropdown(false)
    setSuggestions([])
  }

  const handleClear = () => {
    onChange(null)
    setQuery('')
    setSuggestions([])
    setShowDropdown(false)
  }

  return (
    <div ref={containerRef} className="relative">
      <label className="block text-sm font-medium text-gray-700 mb-1">
        Near <span className="text-gray-400 font-normal">(optional)</span>
      </label>
      <div className="relative">
        <input
          type="text"
          value={value ? value.label : query}
          onChange={(e) => {
            if (value) onChange(null)
            handleSearch(e.target.value)
          }}
          placeholder="e.g. Children's Hospital of Philadelphia"
          className="w-full border border-gray-300 rounded-lg px-3 py-2 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent"
        />
        {isLoading && (
          <div className="absolute right-8 top-1/2 -translate-y-1/2">
            <svg className="h-4 w-4 animate-spin text-gray-400" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          </div>
        )}
        {(value || query) && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            aria-label="Clear location"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>
      {showDropdown && suggestions.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
          {suggestions.map((s, i) => (
            <li key={i}>
              <button
                type="button"
                onClick={() => handleSelect(s)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 border-b border-gray-100 last:border-0"
              >
                {s.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
