'use client'

import { useState } from 'react'
import { generateDecisionBrief } from '@/lib/api'
import UpgradePrompt from '@/components/UpgradePrompt'
import { Tour } from '@/types/tour'
import { Apartment } from '@/types/apartment'

interface DecisionBriefProps {
  isPro: boolean
  touredTours?: Tour[]
  apartments?: Record<string, Apartment>
}

interface ApartmentBrief {
  apartment_id: string
  ai_take: string
  strengths: string[]
  concerns: string[]
}

interface BriefResult {
  apartments: ApartmentBrief[]
  recommendation: { apartment_id: string; reasoning: string }
}

export default function DecisionBrief({ isPro, touredTours = [], apartments = {} }: DecisionBriefProps) {
  const [brief, setBrief] = useState<BriefResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleGenerate = async () => {
    try {
      setLoading(true)
      setError(null)
      const result = await generateDecisionBrief()
      setBrief(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate decision brief')
    } finally {
      setLoading(false)
    }
  }

  const getApartmentLabel = (apartmentId: string): string => {
    const apt = apartments[apartmentId]
    if (apt) return apt.address || apartmentId
    return apartmentId
  }

  const getTourRating = (apartmentId: string): number | null => {
    const tour = touredTours.find((t) => t.apartment_id === apartmentId)
    return tour?.tour_rating ?? null
  }

  if (!isPro) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Decision Brief</h3>
        <p className="text-xs text-gray-500 mb-3">
          Get an AI recommendation based on your tours, notes, and ratings.
        </p>
        <UpgradePrompt feature="AI decision briefs" />
      </div>
    )
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-1">Decision Brief</h3>
      <p className="text-xs text-gray-500 mb-3">
        AI analyzes your toured apartments, notes, and ratings to help you decide.
      </p>

      {!brief && !loading && (
        <button
          onClick={handleGenerate}
          className="w-full py-2 px-4 bg-[var(--color-primary)] text-white text-sm font-medium rounded-lg hover:bg-[var(--color-primary-light)] transition-colors"
        >
          Get AI Recommendation
        </button>
      )}

      {loading && (
        <div className="flex items-center justify-center py-6">
          <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-[var(--color-primary)] mr-2"></div>
          <span className="text-sm text-gray-500">Analyzing your tours...</span>
        </div>
      )}

      {error && (
        <div className="text-center py-3">
          <p className="text-sm text-red-600 mb-2">{error}</p>
          <button
            onClick={handleGenerate}
            className="text-sm text-[var(--color-primary)] hover:underline"
          >
            Try again
          </button>
        </div>
      )}

      {brief && (
        <div className="space-y-4">
          {/* Apartment Analysis Cards */}
          {brief.apartments.map((apt) => {
            const rating = getTourRating(apt.apartment_id)
            const isWinner = brief.recommendation.apartment_id === apt.apartment_id

            return (
              <div
                key={apt.apartment_id}
                className={`border rounded-lg p-3 ${
                  isWinner ? 'border-green-300 bg-green-50' : 'border-gray-200'
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {getApartmentLabel(apt.apartment_id)}
                    </p>
                    {rating !== null && (
                      <p className="text-xs text-gray-500">
                        Your rating: {rating}/5
                      </p>
                    )}
                  </div>
                  {isWinner && (
                    <span className="flex-shrink-0 ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                      Top Pick
                    </span>
                  )}
                </div>

                {/* AI Take */}
                <p className="text-xs text-gray-700 mb-2">{apt.ai_take}</p>

                {/* Strengths */}
                {apt.strengths.length > 0 && (
                  <div className="mb-1.5">
                    <ul className="space-y-0.5">
                      {apt.strengths.map((s, idx) => (
                        <li key={idx} className="text-xs flex items-start gap-1.5">
                          <span className="text-green-600 flex-shrink-0 font-bold">+</span>
                          <span className="text-gray-700">{s}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Concerns */}
                {apt.concerns.length > 0 && (
                  <div>
                    <ul className="space-y-0.5">
                      {apt.concerns.map((c, idx) => (
                        <li key={idx} className="text-xs flex items-start gap-1.5">
                          <span className="text-red-500 flex-shrink-0 font-bold">-</span>
                          <span className="text-gray-700">{c}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )
          })}

          {/* Recommendation Card */}
          <div className="border-2 border-green-300 bg-green-50 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-green-800 mb-1">
              Recommendation
            </h4>
            <p className="text-sm font-medium text-gray-900 mb-1">
              {getApartmentLabel(brief.recommendation.apartment_id)}
            </p>
            <p className="text-xs text-gray-700">{brief.recommendation.reasoning}</p>
          </div>

          {/* Regenerate */}
          <button
            onClick={handleGenerate}
            className="w-full py-1.5 text-xs text-[var(--color-primary)] hover:underline"
          >
            Regenerate brief
          </button>
        </div>
      )}
    </div>
  )
}
