'use client';

import { useState } from 'react';
import { ApartmentWithScore } from '@/types/apartment';
import ImageCarousel from './ImageCarousel';
import { FavoriteButton } from './FavoriteButton';
import { CompareButton } from './CompareButton';
import CostBreakdownPanel from './CostBreakdownPanel';
import UpgradePrompt from './UpgradePrompt';
import { useAuth } from '@/contexts/AuthContext';

interface ApartmentCardProps {
  apartment: ApartmentWithScore;
  moveInDate?: string;
  aiLoading?: boolean;
}

// Format rent as currency
const formatRent = (rent: number): string => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(rent);
};

// Format square footage
const formatSqft = (sqft: number): string => {
  return new Intl.NumberFormat('en-US').format(sqft);
};

// Get freshness badge based on confidence score
const getFreshnessBadge = (confidence?: number): { text: string; color: string } | null => {
  if (confidence === undefined || confidence >= 40) return null;
  return { text: 'May no longer be available', color: 'bg-orange-100 text-orange-800' };
};

// Get color class based on match score
const getScoreColor = (score: number): string => {
  if (score >= 85) return 'bg-emerald-500';
  if (score >= 70) return 'bg-[var(--color-primary)]';
  if (score >= 50) return 'bg-amber-500';
  return 'bg-gray-500';
};

const getLabelColor = (label: string): string => {
  switch (label) {
    case 'Excellent Match': return 'bg-emerald-500 text-white';
    case 'Great Match': return 'bg-[var(--color-primary)] text-white';
    case 'Good Match': return 'bg-slate-500 text-white';
    case 'Fair Match': return 'bg-gray-400 text-gray-800';
    default: return 'bg-gray-300 text-gray-600';
  }
};

export default function ApartmentCard({ apartment, moveInDate, aiLoading }: ApartmentCardProps) {
  const { tier, profileLoading } = useAuth();
  const [showBreakdown, setShowBreakdown] = useState(false);
  const {
    id,
    address,
    rent,
    bedrooms,
    bathrooms,
    sqft,
    property_type,
    available_date,
    amenities,
    neighborhood,
    images,
    match_score,
    reasoning,
    highlights,
  } = apartment;

  return (
    <div className="bg-[var(--color-surface)] rounded-xl shadow-sm border border-[var(--color-border)] overflow-hidden transition hover:shadow-md">
      {/* Image Carousel with Match Score Badge and Favorite Button */}
      <div className="relative">
        <ImageCarousel images={images} alt={address} />

        {/* Favorite Button */}
        <div className="absolute top-2 left-2 z-30 pointer-events-auto">
          <FavoriteButton apartmentId={id} />
        </div>

        {/* Match Score Badge */}
        {aiLoading ? (
          <div className="absolute top-3 right-3 bg-gray-300 animate-pulse px-3 py-1 rounded-full w-24 h-7" />
        ) : match_score != null ? (
          <div
            className={`absolute top-3 right-3 ${getScoreColor(
              match_score
            )} text-white px-3 py-1 rounded-full font-bold text-sm shadow-md`}
          >
            {match_score}% Match
          </div>
        ) : apartment.heuristic_score != null ? (
          <div
            className={`absolute top-3 right-3 ${getScoreColor(
              apartment.heuristic_score
            )} text-white px-3 py-1 rounded-full font-bold text-sm shadow-md`}
          >
            {apartment.heuristic_score}% Match
          </div>
        ) : apartment.match_label ? (
          <div className={`absolute top-3 right-3 ${getLabelColor(apartment.match_label)} px-3 py-1 rounded-full font-bold text-sm shadow-md`}>
            {apartment.match_label}
          </div>
        ) : null}
      </div>

      {/* Card Content */}
      <div className="p-4 space-y-3">
        {/* Rent and Property Type */}
        <div className="flex justify-between items-start">
          <div>
            <p className="text-2xl font-bold text-gray-900">
              {formatRent(rent)}
              <span className="text-sm font-normal text-gray-500">/mo</span>
            </p>
            <p className="text-sm text-gray-600">{property_type}</p>
          </div>
        </div>

        {/* Per Person Pricing Badge */}
        {apartment.pricing_model === 'per_person' && (
          <span className="inline-block bg-purple-100 text-purple-700 text-xs font-medium px-2 py-0.5 rounded">
            Per Person Pricing
          </span>
        )}

        {/* True Cost Estimate */}
        {apartment.true_cost_monthly != null && apartment.true_cost_monthly > rent && (
          <div className="space-y-1">
            <button
              onClick={() => setShowBreakdown(!showBreakdown)}
              className="text-left w-full group"
            >
              <p className="text-sm text-gray-500">
                Est. True Cost:{' '}
                <span className="font-semibold text-gray-700">
                  {formatRent(apartment.true_cost_monthly)}{apartment.pricing_model === 'per_person' ? '/person' : '/mo'}
                </span>
              </p>
              <p className="text-xs text-amber-600 group-hover:text-amber-700 transition">
                +{formatRent(apartment.true_cost_monthly - rent)}{apartment.pricing_model === 'per_person' ? '/person' : '/mo'} in fees &amp; utilities
                <span className="ml-1">{showBreakdown ? '\u25B2' : '\u25BC'}</span>
              </p>
            </button>

            {showBreakdown && (
              apartment.cost_breakdown ? (
                <CostBreakdownPanel breakdown={apartment.cost_breakdown} pricingModel={apartment.pricing_model} bedrooms={apartment.bedrooms} />
              ) : (
                <UpgradePrompt
                  feature="full cost breakdown"
                  inline
                />
              )
            )}
          </div>
        )}

        {/* Address and Neighborhood */}
        <div>
          <p className="text-gray-800 font-medium">{address}</p>
          <p className="text-sm text-gray-500">{neighborhood}</p>
          {apartment.distance_miles != null && (
            <p className="text-xs text-gray-500 mt-0.5 flex items-center gap-1">
              <svg className="h-3 w-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              {apartment.distance_miles} mi away
            </p>
          )}
        </div>

        {/* Beds, Baths, Sqft */}
        <div className="flex gap-4 text-sm text-gray-600">
          <span className="flex items-center gap-1">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
            </svg>
            {bedrooms === 0 ? 'Studio' : `${bedrooms} bed`}
          </span>
          <span className="flex items-center gap-1">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            {bathrooms} bath
          </span>
          <span className="flex items-center gap-1">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
            </svg>
            {formatSqft(sqft)} sqft
          </span>
        </div>

        {/* Availability */}
        {(() => {
          const hasDate = available_date && available_date.trim() !== ''
          if (!hasDate) return null  // No data — don't show anything

          const isUnavailable = available_date === 'Unavailable'
          if (isUnavailable) {
            return (
              <div className="flex items-center gap-2">
                <span className="text-sm text-orange-600 font-medium">No units available</span>
                {apartment.source_url && (
                  <a href={apartment.source_url} target="_blank" rel="noopener noreferrer" className="text-xs text-[var(--color-primary)] hover:underline">
                    Check listing &rarr;
                  </a>
                )}
              </div>
            )
          }

          const isNow = available_date === 'Now'
          const parsedDate = !isNow ? new Date(available_date) : null
          const isValidDate = parsedDate && !isNaN(parsedDate.getTime())
          const isPast = isValidDate && parsedDate <= new Date()
          const isAvailableNow = isNow || isPast

          return (
            <div className="space-y-0.5">
              {isAvailableNow ? (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-green-600 font-medium">Available now</span>
                  {apartment.source_url && (
                    <a href={apartment.source_url} target="_blank" rel="noopener noreferrer" className="text-xs text-[var(--color-primary)] hover:underline">
                      View units &rarr;
                    </a>
                  )}
                </div>
              ) : isValidDate ? (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-600">
                    Available {parsedDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                  </span>
                  {apartment.source_url && (
                    <a href={apartment.source_url} target="_blank" rel="noopener noreferrer" className="text-xs text-[var(--color-primary)] hover:underline">
                      View units &rarr;
                    </a>
                  )}
                </div>
              ) : null}

              {/* Move-in date mismatch indicator */}
              {moveInDate && isValidDate && !isPast && (() => {
                const parsedMoveIn = new Date(moveInDate)
                if (!isNaN(parsedMoveIn.getTime()) && parsedDate > parsedMoveIn) {
                  return <p className="text-xs text-amber-600">&#9888; Available after your move-in date</p>
                }
                return null
              })()}
            </div>
          )
        })()}

        {/* Freshness Badge */}
        {getFreshnessBadge(apartment.freshness_confidence) && (
          <span className={`inline-block px-2 py-1 text-xs rounded-full ${getFreshnessBadge(apartment.freshness_confidence)!.color}`}>
            {getFreshnessBadge(apartment.freshness_confidence)!.text}
          </span>
        )}

        {/* Amenities Tags */}
        <div className="flex flex-wrap gap-1.5">
          {amenities.slice(0, 5).map((amenity) => (
            <span
              key={amenity}
              className="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded-full"
            >
              {amenity}
            </span>
          ))}
          {amenities.length > 5 && (
            <span className="px-2 py-1 bg-gray-100 text-gray-500 text-xs rounded-full">
              +{amenities.length - 5} more
            </span>
          )}
        </div>

        {/* Divider */}
        <hr className="border-gray-200" />

        {/* AI Score Loading Skeleton */}
        {aiLoading && (
          <div className="space-y-2 animate-pulse">
            <div className="flex items-center gap-2">
              <div className="h-6 w-16 bg-gray-200 rounded-full" />
              <div className="h-4 w-24 bg-gray-100 rounded" />
            </div>
            <div className="h-3 w-full bg-gray-100 rounded" />
            <div className="h-3 w-3/4 bg-gray-100 rounded" />
          </div>
        )}

        {/* AI Reasoning - Pro users see full insights, free users see upsell */}
        {!aiLoading && match_score != null && reasoning ? (
          <div className="space-y-2">
            <p className="text-sm text-gray-700 italic">&quot;{reasoning}&quot;</p>
            <ul className="space-y-1">
              {highlights.map((highlight, index) => (
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
          </div>
        ) : tier === 'free' && !profileLoading && apartment.heuristic_score != null ? (
          <a href="/pricing" className="flex items-center gap-2 text-sm text-amber-700 bg-amber-50 rounded-lg px-3 py-2 hover:bg-amber-100 transition">
            <svg className="h-4 w-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            Upgrade to Pro for AI-powered insights
          </a>
        ) : null}

        {/* Card Actions */}
        <div className="flex justify-end pt-2">
          <CompareButton apartmentId={id} />
        </div>
      </div>
    </div>
  );
}
