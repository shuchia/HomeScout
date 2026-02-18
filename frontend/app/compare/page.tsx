'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Image from 'next/image'
import { useComparison } from '@/hooks/useComparison'
import { compareApartments, ApiError } from '@/lib/api'
import { ApartmentWithScore } from '@/types/apartment'

// Format rent as currency
const formatRent = (rent: number): string => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(rent)
}

// Format square footage
const formatSqft = (sqft: number): string => {
  return new Intl.NumberFormat('en-US').format(sqft)
}

// Get color class based on match score
const getScoreColor = (score: number): string => {
  if (score >= 85) return 'bg-green-500'
  if (score >= 70) return 'bg-blue-500'
  if (score >= 50) return 'bg-yellow-500'
  return 'bg-gray-500'
}

export default function ComparePage() {
  const router = useRouter()
  const { apartmentIds, removeFromCompare, clearComparison } = useComparison()

  const [apartments, setApartments] = useState<ApartmentWithScore[]>([])
  const [loading, setLoading] = useState(true)
  const [scoring, setScoring] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [preferences, setPreferences] = useState('')

  // Load apartments when page loads or IDs change
  useEffect(() => {
    async function loadApartments() {
      if (apartmentIds.length < 2) {
        setLoading(false)
        return
      }

      setLoading(true)
      setError(null)

      try {
        // Fetch apartments without scoring initially
        const response = await compareApartments(apartmentIds)
        setApartments(response.apartments)
      } catch (err) {
        if (err instanceof ApiError) {
          setError(err.message)
        } else {
          setError('Failed to load apartments')
        }
      } finally {
        setLoading(false)
      }
    }

    loadApartments()
  }, [apartmentIds])

  // Handle scoring with preferences
  const handleScore = async () => {
    if (!preferences.trim()) return

    setScoring(true)
    setError(null)

    try {
      const response = await compareApartments(apartmentIds, preferences)
      setApartments(response.apartments)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message)
      } else {
        setError('Failed to score apartments')
      }
    } finally {
      setScoring(false)
    }
  }

  // Find the lowest rent for highlighting
  const lowestRent = apartments.length > 0
    ? Math.min(...apartments.map(a => a.rent))
    : 0

  // Find the highest score for highlighting
  const highestScore = apartments.length > 0 && apartments[0].match_score > 0
    ? Math.max(...apartments.map(a => a.match_score))
    : 0

  // Not enough apartments selected
  if (apartmentIds.length < 2 && !loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col">
        <header className="bg-white shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
            <div className="flex items-center gap-4">
              <Link href="/" className="text-gray-600 hover:text-gray-900">
                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
              </Link>
              <h1 className="text-2xl font-bold text-gray-900">Compare Apartments</h1>
            </div>
          </div>
        </header>

        <main className="flex-1 flex items-center justify-center">
          <div className="text-center p-8">
            <svg className="h-16 w-16 text-gray-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">
              Select at least 2 apartments to compare
            </h2>
            <p className="text-gray-600 mb-6">
              Go back to search results and add apartments using the Compare button.
            </p>
            <Link
              href="/"
              className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              Search Apartments
            </Link>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link href="/" className="text-gray-600 hover:text-gray-900">
                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
              </Link>
              <h1 className="text-2xl font-bold text-gray-900">Compare Apartments</h1>
            </div>
            <button
              onClick={() => {
                clearComparison()
                router.push('/')
              }}
              className="text-gray-600 hover:text-gray-900 text-sm"
            >
              Clear All
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* AI Scoring Section */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <svg className="h-5 w-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            Get AI Recommendations
          </h2>
          <p className="text-gray-600 mb-4">
            Tell us what matters most to you and Claude AI will score each apartment based on your preferences.
          </p>
          <div className="flex gap-4">
            <input
              type="text"
              value={preferences}
              onChange={(e) => setPreferences(e.target.value)}
              placeholder="e.g., I need in-unit laundry and a quiet neighborhood for working from home"
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && preferences.trim()) {
                  handleScore()
                }
              }}
            />
            <button
              onClick={handleScore}
              disabled={scoring || !preferences.trim()}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {scoring ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                  Scoring...
                </>
              ) : (
                <>
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  Score
                </>
              )}
            </button>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <div className="flex items-center gap-2">
              <svg className="h-5 w-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-red-700">{error}</p>
            </div>
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mb-4"></div>
            <p className="text-gray-600">Loading apartments...</p>
          </div>
        )}

        {/* Comparison Table */}
        {!loading && apartments.length > 0 && (
          <div className="bg-white rounded-lg shadow-md overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="bg-gray-50 px-6 py-4 text-left text-sm font-semibold text-gray-900 w-40">
                      Property
                    </th>
                    {apartments.map((apt) => (
                      <th key={apt.id} className="px-6 py-4 text-center border-l border-gray-200">
                        <div className="relative">
                          <button
                            onClick={() => removeFromCompare(apt.id)}
                            className="absolute -top-2 right-0 text-gray-400 hover:text-red-500"
                            title="Remove from comparison"
                          >
                            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                          {/* Apartment Image */}
                          {apt.images && apt.images.length > 0 && (
                            <div className="relative w-full h-32 mb-3">
                              <Image
                                src={apt.images[0]}
                                alt={apt.address}
                                fill
                                className="object-cover rounded-lg"
                                sizes="(max-width: 768px) 100vw, 33vw"
                              />
                            </div>
                          )}
                          <h3 className="font-semibold text-gray-900 text-sm">{apt.address}</h3>
                          <p className="text-xs text-gray-500">{apt.neighborhood}</p>
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {/* AI Score Row */}
                  {apartments[0]?.match_score > 0 && (
                    <tr>
                      <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">
                        AI Score
                      </td>
                      {apartments.map((apt) => (
                        <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200">
                          <span
                            className={`inline-block px-3 py-1 rounded-full text-white text-sm font-bold ${getScoreColor(apt.match_score)} ${
                              apt.match_score === highestScore ? 'ring-2 ring-offset-2 ring-green-400' : ''
                            }`}
                          >
                            {apt.match_score}%
                          </span>
                        </td>
                      ))}
                    </tr>
                  )}

                  {/* Rent Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">
                      Rent
                    </td>
                    {apartments.map((apt) => (
                      <td
                        key={apt.id}
                        className={`px-6 py-4 text-center border-l border-gray-200 ${
                          apt.rent === lowestRent ? 'bg-green-50' : ''
                        }`}
                      >
                        <span className={`text-lg font-bold ${apt.rent === lowestRent ? 'text-green-600' : 'text-gray-900'}`}>
                          {formatRent(apt.rent)}
                        </span>
                        <span className="text-sm text-gray-500">/mo</span>
                        {apt.rent === lowestRent && (
                          <span className="block text-xs text-green-600 font-medium mt-1">Lowest</span>
                        )}
                      </td>
                    ))}
                  </tr>

                  {/* Bedrooms Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">
                      Bedrooms
                    </td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200 text-gray-700">
                        {apt.bedrooms === 0 ? 'Studio' : `${apt.bedrooms} bed`}
                      </td>
                    ))}
                  </tr>

                  {/* Bathrooms Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">
                      Bathrooms
                    </td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200 text-gray-700">
                        {apt.bathrooms} bath
                      </td>
                    ))}
                  </tr>

                  {/* Square Footage Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">
                      Size
                    </td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200 text-gray-700">
                        {formatSqft(apt.sqft)} sqft
                      </td>
                    ))}
                  </tr>

                  {/* Property Type Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">
                      Type
                    </td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200 text-gray-700">
                        {apt.property_type}
                      </td>
                    ))}
                  </tr>

                  {/* Available Date Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">
                      Available
                    </td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200 text-gray-700">
                        {new Date(apt.available_date).toLocaleDateString('en-US', {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                        })}
                      </td>
                    ))}
                  </tr>

                  {/* Amenities Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900 align-top">
                      Amenities
                    </td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 border-l border-gray-200">
                        <div className="flex flex-wrap gap-1 justify-center">
                          {apt.amenities.map((amenity) => (
                            <span
                              key={amenity}
                              className="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded-full"
                            >
                              {amenity}
                            </span>
                          ))}
                        </div>
                      </td>
                    ))}
                  </tr>

                  {/* AI Reasoning Row (only if scored) */}
                  {apartments[0]?.reasoning && (
                    <tr>
                      <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900 align-top">
                        AI Analysis
                      </td>
                      {apartments.map((apt) => (
                        <td key={apt.id} className="px-6 py-4 border-l border-gray-200">
                          <p className="text-sm text-gray-700 italic mb-3">&quot;{apt.reasoning}&quot;</p>
                          {apt.highlights && apt.highlights.length > 0 && (
                            <ul className="space-y-1">
                              {apt.highlights.map((highlight, index) => (
                                <li key={index} className="flex items-start gap-2 text-sm text-gray-600">
                                  <svg
                                    className="h-4 w-4 text-green-500 flex-shrink-0 mt-0.5"
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                  >
                                    <path
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
                                      strokeWidth={2}
                                      d="M5 13l4 4L19 7"
                                    />
                                  </svg>
                                  {highlight}
                                </li>
                              ))}
                            </ul>
                          )}
                        </td>
                      ))}
                    </tr>
                  )}

                  {/* View Listing Row */}
                  <tr>
                    <td className="bg-gray-50 px-6 py-4 text-sm font-medium text-gray-900">
                      Actions
                    </td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200">
                        <a
                          href={`/apartment/${apt.id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
                        >
                          View Details
                          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                          </svg>
                        </a>
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="bg-white border-t mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <p className="text-center text-sm text-gray-500">
            Powered by Claude AI &middot; Built with Next.js and FastAPI
          </p>
        </div>
      </footer>
    </div>
  )
}
