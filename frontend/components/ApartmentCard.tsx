'use client';

import { ApartmentWithScore } from '@/types/apartment';
import ImageCarousel from './ImageCarousel';

interface ApartmentCardProps {
  apartment: ApartmentWithScore;
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

// Get color class based on match score
const getScoreColor = (score: number): string => {
  if (score >= 85) return 'bg-green-500';
  if (score >= 70) return 'bg-blue-500';
  if (score >= 50) return 'bg-yellow-500';
  return 'bg-gray-500';
};

export default function ApartmentCard({ apartment }: ApartmentCardProps) {
  const {
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
    <div className="bg-white rounded-lg shadow-md overflow-hidden transition hover:shadow-lg">
      {/* Image Carousel with Match Score Badge */}
      <div className="relative">
        <ImageCarousel images={images} alt={address} />

        {/* Match Score Badge */}
        <div
          className={`absolute top-3 right-3 ${getScoreColor(
            match_score
          )} text-white px-3 py-1 rounded-full font-bold text-sm shadow-md`}
        >
          {match_score}% Match
        </div>
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

        {/* Address and Neighborhood */}
        <div>
          <p className="text-gray-800 font-medium">{address}</p>
          <p className="text-sm text-gray-500">{neighborhood}</p>
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

        {/* Available Date */}
        <p className="text-sm text-gray-500">
          Available: {new Date(available_date).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
          })}
        </p>

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

        {/* AI Reasoning */}
        <div className="space-y-2">
          <p className="text-sm text-gray-700 italic">&quot;{reasoning}&quot;</p>

          {/* Highlights */}
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
      </div>
    </div>
  );
}
