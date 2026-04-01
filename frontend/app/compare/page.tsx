'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Image from 'next/image'
import { useComparison } from '@/hooks/useComparison'
import { useAuth } from '@/contexts/AuthContext'
import UpgradePrompt from '@/components/UpgradePrompt'
import { compareApartments, ApiError, CompareResponse } from '@/lib/api'
import { Apartment, ComparisonAnalysis, SearchContext } from '@/types/apartment'

const formatRent = (rent: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(rent)

const formatSqft = (sqft: number): string =>
  new Intl.NumberFormat('en-US').format(sqft)

const getScoreColor = (score: number): string => {
  if (score >= 85) return 'bg-emerald-500'
  if (score >= 70) return 'bg-[var(--color-primary)]'
  if (score >= 50) return 'bg-yellow-500'
  return 'bg-gray-500'
}

export default function ComparePage() {
  const router = useRouter()
  const { user, loading: authLoading, signInWithGoogle, isPro, profileLoading } = useAuth()
  const { apartmentIds, removeFromCompare, clearComparison, searchContext } = useComparison()

  const [apartments, setApartments] = useState<Apartment[]>([])
  const [loading, setLoading] = useState(true)
  const [scoring, setScoring] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [preferences, setPreferences] = useState('')
  const [analysis, setAnalysis] = useState<ComparisonAnalysis | null>(null)

  // Pre-fill preferences from search context
  useEffect(() => {
    if (searchContext?.other_preferences) {
      setPreferences(searchContext.other_preferences)
    }
  }, [searchContext])

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
    setScoring(true)
    setError(null)

    try {
      const apiSearchContext: SearchContext | undefined = searchContext
        ? {
            city: searchContext.city,
            budget: searchContext.budget,
            bedrooms: searchContext.bedrooms,
            bathrooms: searchContext.bathrooms,
            property_type: searchContext.property_type,
            move_in_date: searchContext.move_in_date,
          }
        : undefined

      const response = await compareApartments(apartmentIds, preferences, apiSearchContext)
      setApartments(response.apartments)
      setAnalysis(response.comparison_analysis || null)
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

  const lowestRent = apartments.length > 0 ? Math.min(...apartments.map(a => a.rent)) : 0

  // Auth loading state
  if (authLoading) {
    return (
      <div className="min-h-screen bg-[var(--color-bg)] flex items-center justify-center">
        <div className="animate-pulse text-center">
          <div className="h-8 w-48 bg-gray-200 rounded mb-4 mx-auto"></div>
          <div className="h-4 w-32 bg-gray-200 rounded mx-auto"></div>
        </div>
      </div>
    )
  }

  // Auth gate
  if (!user) {
    return (
      <div className="min-h-screen bg-[var(--color-bg)] flex flex-col">
        <header className="bg-[var(--color-surface)] border border-[var(--color-border)]">
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
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Sign in to compare apartments</h2>
            <p className="text-gray-600 mb-6">Create an account to use the comparison tool.</p>
            <button
              onClick={signInWithGoogle}
              className="px-6 py-3 bg-[var(--color-primary)] text-white rounded-lg font-medium hover:bg-[var(--color-primary-light)] transition-colors"
            >
              Sign In with Google
            </button>
          </div>
        </main>
      </div>
    )
  }

  // Not enough apartments
  if (apartmentIds.length < 2 && !loading) {
    return (
      <div className="min-h-screen bg-[var(--color-bg)] flex flex-col">
        <header className="bg-[var(--color-surface)] border border-[var(--color-border)]">
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
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Select at least 2 apartments to compare</h2>
            <p className="text-gray-600 mb-6">Go back to search results and add apartments using the Compare button.</p>
            <Link href="/" className="inline-flex items-center gap-2 px-6 py-3 bg-[var(--color-primary)] text-white rounded-lg font-medium hover:bg-[var(--color-primary-light)] transition-colors">
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

  const winnerAptId = analysis?.winner?.apartment_id
  const winnerApt = apartments.find(a => a.id === winnerAptId)

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      {/* Header */}
      <header className="bg-[var(--color-surface)] border border-[var(--color-border)]">
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
              onClick={() => { clearComparison(); router.push('/') }}
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
            <svg className="h-5 w-5 text-[var(--color-primary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            Get AI Comparison
          </h2>
          <p className="text-gray-600 mb-4">
            Click Score for a deep head-to-head AI analysis. Optionally add your preferences for a personalized comparison.
          </p>
          {profileLoading ? (
            <div className="h-10 bg-gray-100 rounded-lg animate-pulse" />
          ) : isPro ? (
            <div className="flex gap-4">
              <input
                type="text"
                value={preferences}
                onChange={(e) => setPreferences(e.target.value)}
                placeholder="Optional: e.g., parking, quiet for WFH, near transit"
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent"
                onKeyDown={(e) => { if (e.key === 'Enter') handleScore() }}
              />
              <button
                onClick={handleScore}
                disabled={scoring}
                className="px-6 py-2 bg-[var(--color-primary)] text-white rounded-lg font-medium hover:bg-[var(--color-primary-light)] transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {scoring ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    Analyzing...
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
          ) : (
            <UpgradePrompt feature="AI comparison analysis" />
          )}
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
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[var(--color-primary)] mb-4"></div>
            <p className="text-gray-600">Loading apartments...</p>
          </div>
        )}

        {/* Winner Summary Card */}
        {analysis && winnerApt && (
          <div className="bg-white rounded-lg shadow-md p-6 mb-8 border-2 border-green-400">
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-green-600 font-bold text-lg">Winner</span>
                  <svg className="h-6 w-6 text-green-500" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                  </svg>
                </div>
                <h3 className="text-xl font-semibold text-gray-900">{winnerApt.address}</h3>
                <p className="text-gray-600 mt-1">{analysis.winner.reason}</p>
              </div>
            </div>
            <div className="flex gap-4 mt-4">
              {analysis.apartment_scores.map((score) => {
                const apt = apartments.find(a => a.id === score.apartment_id)
                const isWinner = score.apartment_id === winnerAptId
                return (
                  <div
                    key={score.apartment_id}
                    className={`flex-1 p-3 rounded-lg ${isWinner ? 'bg-green-50 border border-green-200' : 'bg-[var(--color-bg)]'}`}
                  >
                    <p className="text-sm text-gray-600 truncate">{apt?.address || score.apartment_id}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`text-2xl font-bold ${isWinner ? 'text-green-600' : 'text-gray-700'}`}>
                        {score.overall_score}
                      </span>
                      <span className="text-sm text-gray-500">/100</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Category Scores Grid */}
        {analysis && (
          <div className="bg-white rounded-lg shadow-md p-6 mb-8">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Category Breakdown</h3>
            <div className="space-y-4">
              {analysis.categories.map((category) => {
                const scores = analysis.apartment_scores.map(s => s.category_scores[category]?.score || 0)
                const maxScore = Math.max(...scores)

                return (
                  <div key={category} className="border-b border-gray-100 pb-4 last:border-0">
                    <h4 className="text-sm font-medium text-gray-900 mb-2">{category}</h4>
                    <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${apartments.length}, 1fr)` }}>
                      {analysis.apartment_scores.map((aptScore) => {
                        const catScore = aptScore.category_scores[category]
                        const isHighest = catScore && catScore.score === maxScore && scores.filter(s => s === maxScore).length === 1
                        return (
                          <div
                            key={aptScore.apartment_id}
                            className={`p-3 rounded-lg ${isHighest ? 'bg-green-50 border border-green-200' : 'bg-[var(--color-bg)]'}`}
                          >
                            <div className="flex items-center gap-2">
                              <span className={`inline-block px-2 py-0.5 rounded-full text-white text-sm font-bold ${getScoreColor(catScore?.score || 0)}`}>
                                {catScore?.score || 0}
                              </span>
                              {isHighest && (
                                <svg className="h-4 w-4 text-green-500" fill="currentColor" viewBox="0 0 24 24">
                                  <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                                </svg>
                              )}
                            </div>
                            <p className="text-xs text-gray-600 mt-1">{catScore?.note || ''}</p>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Mobile: Horizontal Swipe Cards */}
        {!loading && apartments.length > 0 && (
          <div className="md:hidden">
            <div className="flex gap-4 overflow-x-auto snap-x snap-mandatory pb-4 -mx-4 px-4">
              {apartments.map((apt) => {
                const aptScore = analysis?.apartment_scores.find(s => s.apartment_id === apt.id)
                const isWinner = apt.id === winnerAptId
                return (
                  <div
                    key={apt.id}
                    className={`flex-shrink-0 w-[85vw] snap-center bg-white rounded-xl shadow-md overflow-hidden ${isWinner ? 'ring-2 ring-green-400' : ''}`}
                  >
                    {/* Card Header */}
                    <div className="relative">
                      {apt.images && apt.images.length > 0 && (
                        <div className="relative w-full h-40">
                          <Image src={apt.images[0]} alt={apt.address} fill className="object-cover" sizes="85vw" />
                        </div>
                      )}
                      <button
                        onClick={() => removeFromCompare(apt.id)}
                        className="absolute top-2 right-2 bg-white/80 backdrop-blur rounded-full p-1.5 text-gray-500 hover:text-red-500"
                      >
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                      {isWinner && (
                        <div className="absolute top-2 left-2 bg-green-500 text-white text-xs font-bold px-2 py-1 rounded-full flex items-center gap-1">
                          <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                          </svg>
                          Winner
                        </div>
                      )}
                    </div>

                    <div className="p-4 space-y-3">
                      <div>
                        <h3 className="font-semibold text-gray-900 text-sm leading-tight">{apt.address}</h3>
                        {apt.neighborhood && <p className="text-xs text-gray-500 mt-0.5">{apt.neighborhood}</p>}
                      </div>

                      {/* Score */}
                      {aptScore && (
                        <div className="flex items-center gap-2">
                          <span className={`inline-block px-3 py-1 rounded-full text-white text-sm font-bold ${getScoreColor(aptScore.overall_score)}`}>
                            {aptScore.overall_score}%
                          </span>
                          <span className="text-xs text-gray-500">Overall Score</span>
                        </div>
                      )}

                      {/* Key Stats */}
                      <div className="grid grid-cols-3 gap-2 text-center">
                        <div className="bg-gray-50 rounded-lg p-2">
                          <p className={`text-sm font-bold ${apt.rent === lowestRent ? 'text-green-600' : 'text-gray-900'}`}>{formatRent(apt.rent)}</p>
                          <p className="text-xs text-gray-500">/mo{apt.rent === lowestRent ? ' ★' : ''}</p>
                        </div>
                        <div className="bg-gray-50 rounded-lg p-2">
                          <p className="text-sm font-bold text-gray-900">{apt.bedrooms === 0 ? 'Studio' : `${apt.bedrooms} bed`}</p>
                          <p className="text-xs text-gray-500">{apt.bathrooms} bath</p>
                        </div>
                        <div className="bg-gray-50 rounded-lg p-2">
                          <p className="text-sm font-bold text-gray-900">{apt.sqft ? formatSqft(apt.sqft) : 'N/A'}</p>
                          <p className="text-xs text-gray-500">sqft</p>
                        </div>
                      </div>

                      {/* True Cost */}
                      {apt.true_cost_monthly && (
                        <div className="flex items-center justify-between bg-amber-50 rounded-lg px-3 py-2">
                          <span className="text-xs text-amber-700">Est. True Cost</span>
                          <span className="text-sm font-semibold text-amber-800">{formatRent(apt.true_cost_monthly)}/mo</span>
                        </div>
                      )}

                      {/* Availability */}
                      <AvailabilityCell availableDate={apt.available_date} sourceUrl={apt.source_url} />

                      {/* Amenities (top 5 + expand) */}
                      <AmenitiesList amenities={apt.amenities} />

                      {/* AI Analysis */}
                      {aptScore && (
                        <div className="border-t pt-3">
                          <p className="text-xs text-gray-600 italic">&quot;{aptScore.reasoning}&quot;</p>
                          {aptScore.highlights.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-2">
                              {aptScore.highlights.map((h, i) => (
                                <span key={i} className="text-xs bg-green-50 text-green-700 px-2 py-0.5 rounded-full">&#10003; {h}</span>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* View Listing */}
                      {apt.source_url ? (
                        <a
                          href={apt.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block w-full text-center px-4 py-2.5 bg-[var(--color-primary)] text-white rounded-lg text-sm font-medium hover:bg-[var(--color-primary-light)] transition-colors"
                        >
                          View Original Listing &#8599;
                        </a>
                      ) : (
                        <span className="block w-full text-center px-4 py-2.5 bg-gray-100 text-gray-400 rounded-lg text-sm">No listing link</span>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
            {/* Scroll hint */}
            <p className="text-center text-xs text-gray-400 mt-1">Swipe to compare &rarr;</p>
          </div>
        )}

        {/* Desktop: Comparison Table */}
        {!loading && apartments.length > 0 && (
          <div className="hidden md:block bg-white rounded-lg shadow-md overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="bg-[var(--color-bg)] px-6 py-4 text-left text-sm font-semibold text-gray-900 w-40">Property</th>
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
                          {apt.images && apt.images.length > 0 && (
                            <div className="relative w-full h-32 mb-3">
                              <Image src={apt.images[0]} alt={apt.address} fill className="object-cover rounded-lg" sizes="33vw" />
                            </div>
                          )}
                          <h3 className="font-semibold text-gray-900 text-sm">
                            {apt.id === winnerAptId && <span className="text-green-500 mr-1">&#9733;</span>}
                            {apt.address}
                          </h3>
                          <p className="text-xs text-gray-500">{apt.neighborhood}</p>
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {/* Overall Score Row */}
                  {analysis && (
                    <tr>
                      <td className="bg-[var(--color-bg)] px-6 py-4 text-sm font-medium text-gray-900">Overall Score</td>
                      {apartments.map((apt) => {
                        const aptScore = analysis.apartment_scores.find(s => s.apartment_id === apt.id)
                        const isWinner = apt.id === winnerAptId
                        return (
                          <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200">
                            <span className={`inline-block px-3 py-1 rounded-full text-white text-sm font-bold ${getScoreColor(aptScore?.overall_score || 0)} ${isWinner ? 'ring-2 ring-offset-2 ring-green-400' : ''}`}>
                              {aptScore?.overall_score || 0}%
                            </span>
                          </td>
                        )
                      })}
                    </tr>
                  )}

                  {/* Rent Row */}
                  <tr>
                    <td className="bg-[var(--color-bg)] px-6 py-4 text-sm font-medium text-gray-900">Rent</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className={`px-6 py-4 text-center border-l border-gray-200 ${apt.rent === lowestRent ? 'bg-green-50' : ''}`}>
                        <span className={`text-lg font-bold ${apt.rent === lowestRent ? 'text-green-600' : 'text-gray-900'}`}>{formatRent(apt.rent)}</span>
                        <span className="text-sm text-gray-500">/mo</span>
                        {apt.rent === lowestRent && <span className="block text-xs text-green-600 font-medium mt-1">Lowest</span>}
                      </td>
                    ))}
                  </tr>

                  {/* True Cost Row */}
                  <tr>
                    <td className="bg-[var(--color-bg)] px-6 py-4 text-sm font-medium text-gray-900">Est. True Cost</td>
                    {apartments.map((apt) => (
                      <td key={`truecost-${apt.id}`} className="px-6 py-4 text-center border-l border-gray-200">
                        {apt.true_cost_monthly ? (
                          <div>
                            <span className="font-semibold">
                              {formatRent(apt.true_cost_monthly)}/mo
                            </span>
                            {apt.true_cost_monthly > apt.rent && (
                              <span className="block text-xs text-amber-600">
                                +{formatRent(apt.true_cost_monthly - apt.rent)} over rent
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-gray-400">&mdash;</span>
                        )}
                      </td>
                    ))}
                  </tr>

                  {/* Bedrooms Row */}
                  <tr>
                    <td className="bg-[var(--color-bg)] px-6 py-4 text-sm font-medium text-gray-900">Bedrooms</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200 text-gray-700">
                        {apt.bedrooms === 0 ? 'Studio' : `${apt.bedrooms} bed`}
                      </td>
                    ))}
                  </tr>

                  {/* Bathrooms Row */}
                  <tr>
                    <td className="bg-[var(--color-bg)] px-6 py-4 text-sm font-medium text-gray-900">Bathrooms</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200 text-gray-700">{apt.bathrooms} bath</td>
                    ))}
                  </tr>

                  {/* Square Footage Row */}
                  <tr>
                    <td className="bg-[var(--color-bg)] px-6 py-4 text-sm font-medium text-gray-900">Size</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200 text-gray-700">{apt.sqft ? `${formatSqft(apt.sqft)} sqft` : 'N/A'}</td>
                    ))}
                  </tr>

                  {/* Property Type Row */}
                  <tr>
                    <td className="bg-[var(--color-bg)] px-6 py-4 text-sm font-medium text-gray-900">Type</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200 text-gray-700">{apt.property_type}</td>
                    ))}
                  </tr>

                  {/* Available Date Row */}
                  <tr>
                    <td className="bg-[var(--color-bg)] px-6 py-4 text-sm font-medium text-gray-900">Available</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200">
                        <AvailabilityCell availableDate={apt.available_date} sourceUrl={apt.source_url} />
                      </td>
                    ))}
                  </tr>

                  {/* Amenities Row - capped to 5 with expand */}
                  <tr>
                    <td className="bg-[var(--color-bg)] px-6 py-4 text-sm font-medium text-gray-900 align-top">Amenities</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 border-l border-gray-200">
                        <AmenitiesList amenities={apt.amenities} />
                      </td>
                    ))}
                  </tr>

                  {/* Distance Row (proximity search) */}
                  {searchContext?.near_label && (
                    <tr>
                      <td className="bg-[var(--color-bg)] px-6 py-4 text-sm font-medium text-gray-900">Distance</td>
                      {apartments.map((apt) => (
                        <td key={`dist-${apt.id}`} className="px-6 py-4 text-center border-l border-gray-200 text-gray-700">
                          {(apt as any).distance_miles != null
                            ? `${(apt as any).distance_miles} mi`
                            : '—'}
                        </td>
                      ))}
                    </tr>
                  )}

                  {/* AI Reasoning Row */}
                  {analysis && (
                    <tr>
                      <td className="bg-[var(--color-bg)] px-6 py-4 text-sm font-medium text-gray-900 align-top">AI Analysis</td>
                      {apartments.map((apt) => {
                        const aptScore = analysis.apartment_scores.find(s => s.apartment_id === apt.id)
                        return (
                          <td key={apt.id} className="px-6 py-4 border-l border-gray-200">
                            {aptScore && (
                              <>
                                <p className="text-sm text-gray-700 italic mb-3">&quot;{aptScore.reasoning}&quot;</p>
                                {aptScore.highlights.length > 0 && (
                                  <ul className="space-y-1">
                                    {aptScore.highlights.map((highlight, index) => (
                                      <li key={index} className="flex items-start gap-2 text-sm text-gray-600">
                                        <svg className="h-4 w-4 text-green-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                        </svg>
                                        {highlight}
                                      </li>
                                    ))}
                                  </ul>
                                )}
                              </>
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  )}

                  {/* View Listing Row */}
                  <tr>
                    <td className="bg-[var(--color-bg)] px-6 py-4 text-sm font-medium text-gray-900">Actions</td>
                    {apartments.map((apt) => (
                      <td key={apt.id} className="px-6 py-4 text-center border-l border-gray-200">
                        {apt.source_url ? (
                          <a
                            href={apt.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-2 px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg text-sm font-medium hover:bg-[var(--color-primary-light)] transition-colors"
                          >
                            View Original Listing
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                            </svg>
                          </a>
                        ) : (
                          <span className="text-sm text-gray-400">No listing link</span>
                        )}
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
          <p className="text-center text-sm text-gray-500">Powered by Claude AI &middot; Built with Next.js and FastAPI</p>
        </div>
      </footer>
    </div>
  )
}

function AmenitiesList({ amenities }: { amenities: string[] }) {
  const [expanded, setExpanded] = useState(false)
  const LIMIT = 5
  const visible = expanded ? amenities : amenities.slice(0, LIMIT)
  const remaining = amenities.length - LIMIT

  return (
    <div className="flex flex-wrap gap-1 justify-center">
      {visible.map((amenity) => (
        <span key={amenity} className="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded-full">{amenity}</span>
      ))}
      {remaining > 0 && !expanded && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="px-2 py-1 bg-gray-200 text-gray-700 text-xs rounded-full font-medium hover:bg-gray-300 transition-colors"
        >
          +{remaining} more
        </button>
      )}
      {expanded && remaining > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="px-2 py-1 bg-gray-200 text-gray-700 text-xs rounded-full font-medium hover:bg-gray-300 transition-colors"
        >
          Show less
        </button>
      )}
    </div>
  )
}

function AvailabilityCell({ availableDate, sourceUrl }: { availableDate?: string; sourceUrl?: string | null }) {
  if (!availableDate || availableDate.trim() === '') {
    return <span className="text-gray-400">&mdash;</span>
  }

  if (availableDate === 'Unavailable') {
    return (
      <div>
        <span className="text-sm text-orange-600 font-medium">No units available</span>
        {sourceUrl && (
          <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="block text-xs text-[var(--color-primary)] hover:underline mt-0.5">
            Check listing &rarr;
          </a>
        )}
      </div>
    )
  }

  const ViewUnitsLink = () => sourceUrl ? (
    <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="block text-xs text-[var(--color-primary)] hover:underline mt-0.5">
      View units &rarr;
    </a>
  ) : null

  if (availableDate === 'Now') {
    return (
      <div>
        <span className="text-sm text-green-600 font-medium">Available now</span>
        <ViewUnitsLink />
      </div>
    )
  }

  const parsed = new Date(availableDate)
  if (isNaN(parsed.getTime())) {
    return <span className="text-gray-400">&mdash;</span>
  }

  const isPast = parsed <= new Date()
  if (isPast) {
    return (
      <div>
        <span className="text-sm text-green-600 font-medium">Available now</span>
        <ViewUnitsLink />
      </div>
    )
  }

  return (
    <div>
      <span className="text-sm text-gray-700">
        {parsed.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
      </span>
      <ViewUnitsLink />
    </div>
  )
}
