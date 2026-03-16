'use client'

import Link from 'next/link'
import { Tour, TourStage } from '@/types/tour'
import { Apartment } from '@/types/apartment'

interface TourCardProps {
  tour: Tour
  apartment?: Apartment
}

const stageConfig: Record<TourStage, { label: string; color: string }> = {
  interested: { label: 'Interested', color: 'bg-blue-100 text-blue-800' },
  outreach_sent: { label: 'Outreach Sent', color: 'bg-yellow-100 text-yellow-800' },
  scheduled: { label: 'Scheduled', color: 'bg-purple-100 text-purple-800' },
  toured: { label: 'Toured', color: 'bg-green-100 text-green-800' },
  deciding: { label: 'Deciding', color: 'bg-orange-100 text-orange-800' },
}

const formatRent = (rent: number): string => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(rent)
}

function formatScheduledDate(date: string, time: string | null): string {
  const d = new Date(date + 'T00:00:00')
  const dateStr = d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
  if (time) {
    // time is HH:MM or HH:MM:SS
    const [h, m] = time.split(':')
    const hour = parseInt(h, 10)
    const ampm = hour >= 12 ? 'PM' : 'AM'
    const hour12 = hour % 12 || 12
    return `${dateStr} at ${hour12}:${m} ${ampm}`
  }
  return dateStr
}

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((star) => (
        <svg
          key={star}
          className={`h-4 w-4 ${star <= rating ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300'}`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
        </svg>
      ))}
    </div>
  )
}

export default function TourCard({ tour, apartment }: TourCardProps) {
  const stage = stageConfig[tour.stage]
  const notesCount = tour.notes.length
  const photosCount = tour.photos.length

  return (
    <Link
      href={`/tours/${tour.id}`}
      className="block bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow"
    >
      {/* Top row: address + stage badge */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-medium text-gray-900 truncate">
            {apartment ? apartment.address : 'Loading...'}
          </p>
          {apartment && (
            <p className="text-sm text-gray-500 mt-0.5">
              {formatRent(apartment.rent)}/mo
              <span className="mx-1.5 text-gray-300">|</span>
              {apartment.bedrooms === 0 ? 'Studio' : `${apartment.bedrooms} bed`}
              <span className="mx-1"> / </span>
              {apartment.bathrooms} bath
            </p>
          )}
        </div>
        <span className={`shrink-0 px-2.5 py-0.5 rounded-full text-xs font-medium ${stage.color}`}>
          {stage.label}
        </span>
      </div>

      {/* Scheduled date/time */}
      {tour.stage === 'scheduled' && tour.scheduled_date && (
        <div className="mt-2 flex items-center gap-1.5 text-sm text-purple-700">
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          {formatScheduledDate(tour.scheduled_date, tour.scheduled_time)}
        </div>
      )}

      {/* Tour rating */}
      {tour.stage === 'toured' && tour.tour_rating != null && (
        <div className="mt-2">
          <StarRating rating={tour.tour_rating} />
        </div>
      )}

      {/* Decision badge */}
      {tour.decision && (
        <div className="mt-2">
          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
            tour.decision === 'applied'
              ? 'bg-green-100 text-green-800'
              : 'bg-gray-100 text-gray-600'
          }`}>
            {tour.decision === 'applied' ? 'Applied' : 'Passed'}
          </span>
        </div>
      )}

      {/* Bottom row: notes/photos counts */}
      {(notesCount > 0 || photosCount > 0) && (
        <div className="mt-2 flex items-center gap-3 text-xs text-gray-400">
          {notesCount > 0 && (
            <span className="flex items-center gap-1">
              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              {notesCount} {notesCount === 1 ? 'note' : 'notes'}
            </span>
          )}
          {photosCount > 0 && (
            <span className="flex items-center gap-1">
              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              {photosCount} {photosCount === 1 ? 'photo' : 'photos'}
            </span>
          )}
        </div>
      )}
    </Link>
  )
}
