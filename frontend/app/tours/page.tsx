'use client'

import { useEffect, useState, useMemo, useCallback } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { listTours, getApartmentsBatch } from '@/lib/api'
import { Tour, TourStage } from '@/types/tour'
import { Apartment } from '@/types/apartment'
import TourCard from '@/components/TourCard'
import Link from 'next/link'

type Tab = 'today' | 'upcoming' | 'all'

const stageOrder: TourStage[] = ['interested', 'outreach_sent', 'scheduled', 'toured', 'deciding']
const stageLabels: Record<TourStage, string> = {
  interested: 'Interested',
  outreach_sent: 'Outreach Sent',
  scheduled: 'Scheduled',
  toured: 'Toured',
  deciding: 'Deciding',
}

function isToday(dateStr: string): boolean {
  const today = new Date()
  const date = new Date(dateStr + 'T00:00:00')
  return (
    date.getFullYear() === today.getFullYear() &&
    date.getMonth() === today.getMonth() &&
    date.getDate() === today.getDate()
  )
}

function isFuture(dateStr: string): boolean {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const date = new Date(dateStr + 'T00:00:00')
  return date > today
}

export default function ToursPage() {
  const { user, loading: authLoading, signInWithGoogle } = useAuth()
  const [tours, setTours] = useState<Tour[]>([])
  const [apartments, setApartments] = useState<Record<string, Apartment>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('today')

  const fetchTours = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await listTours()
      setTours(data.tours)

      // Fetch apartment data for all tours
      const apartmentIds = [...new Set(data.tours.map((t) => t.apartment_id))]
      if (apartmentIds.length > 0) {
        const aptData = await getApartmentsBatch(apartmentIds)
        const aptMap: Record<string, Apartment> = {}
        for (const apt of aptData) {
          aptMap[apt.id] = apt
        }
        setApartments(aptMap)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tours')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (user) {
      fetchTours()
    }
  }, [user, fetchTours])

  // Filtered tours by tab
  const todayTours = useMemo(
    () =>
      tours
        .filter((t) => t.scheduled_date && isToday(t.scheduled_date))
        .sort((a, b) => (a.scheduled_time || '').localeCompare(b.scheduled_time || '')),
    [tours]
  )

  const upcomingTours = useMemo(
    () =>
      tours
        .filter((t) => t.scheduled_date && isFuture(t.scheduled_date) && !isToday(t.scheduled_date))
        .sort((a, b) => (a.scheduled_date || '').localeCompare(b.scheduled_date || '')),
    [tours]
  )

  const toursByStage = useMemo(() => {
    const grouped: Partial<Record<TourStage, Tour[]>> = {}
    for (const tour of tours) {
      if (!grouped[tour.stage]) grouped[tour.stage] = []
      grouped[tour.stage]!.push(tour)
    }
    return grouped
  }, [tours])

  // Needs action: tours in "interested" stage with email draft ready
  const needsAction = useMemo(
    () => tours.filter((t) => t.stage === 'interested' && t.inquiry_email_draft),
    [tours]
  )

  // Ready to decide: 2+ tours in "toured" stage
  const touredTours = useMemo(() => tours.filter((t) => t.stage === 'toured'), [tours])
  const readyToDecide = touredTours.length >= 2

  // Auto-select best tab
  useEffect(() => {
    if (!loading && tours.length > 0) {
      if (todayTours.length > 0) {
        setActiveTab('today')
      } else if (upcomingTours.length > 0) {
        setActiveTab('upcoming')
      } else {
        setActiveTab('all')
      }
    }
  }, [loading, tours.length, todayTours.length, upcomingTours.length])

  // Auth loading skeleton
  if (authLoading) {
    return (
      <div className="max-w-lg mx-auto p-4">
        <div className="animate-pulse">
          <div className="h-8 w-32 bg-gray-200 rounded mb-6"></div>
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-24 bg-gray-200 rounded-lg"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  // Auth gate
  if (!user) {
    return (
      <div className="max-w-lg mx-auto p-4 text-center py-20">
        <h1 className="text-2xl font-bold mb-4">My Tours</h1>
        <p className="text-gray-600 mb-6">Sign in to manage your apartment tours.</p>
        <button
          onClick={signInWithGoogle}
          className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          Sign In with Google
        </button>
      </div>
    )
  }

  return (
    <div className="max-w-lg mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">My Tours</h1>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 bg-gray-200 rounded-lg animate-pulse"></div>
          ))}
        </div>
      ) : error ? (
        <div className="text-center py-12">
          <p className="text-red-600 mb-4">{error}</p>
          <button
            onClick={fetchTours}
            className="text-blue-600 hover:underline"
          >
            Try again
          </button>
        </div>
      ) : tours.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-600 mb-4">
            You haven&apos;t started touring any apartments yet.
          </p>
          <Link href="/favorites" className="text-blue-600 hover:underline">
            Browse your favorites to get started
          </Link>
        </div>
      ) : (
        <>
          {/* Needs Action Banner */}
          {needsAction.length > 0 && (
            <div className="mb-4 bg-blue-50 border border-blue-200 rounded-lg p-3">
              <p className="text-sm font-medium text-blue-800">
                {needsAction.length} {needsAction.length === 1 ? 'apartment has' : 'apartments have'} an email draft ready to send
              </p>
            </div>
          )}

          {/* Ready to Decide Banner */}
          {readyToDecide && (
            <div className="mb-4 bg-orange-50 border border-orange-200 rounded-lg p-3">
              <p className="text-sm font-medium text-orange-800">
                You&apos;ve toured {touredTours.length} apartments &mdash; ready to make a decision?
              </p>
            </div>
          )}

          {/* Tabs */}
          <div className="flex border-b border-gray-200 mb-4">
            {([
              { key: 'today' as Tab, label: 'Today', count: todayTours.length },
              { key: 'upcoming' as Tab, label: 'Upcoming', count: upcomingTours.length },
              { key: 'all' as Tab, label: 'All', count: tours.length },
            ]).map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex-1 py-2.5 text-sm font-medium text-center border-b-2 transition-colors ${
                  activeTab === tab.key
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                {tab.label}
                {tab.count > 0 && (
                  <span className={`ml-1.5 inline-flex items-center justify-center px-1.5 py-0.5 rounded-full text-xs ${
                    activeTab === tab.key
                      ? 'bg-blue-100 text-blue-600'
                      : 'bg-gray-100 text-gray-500'
                  }`}>
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          {activeTab === 'today' && (
            todayTours.length === 0 ? (
              <p className="text-center text-gray-500 py-8 text-sm">No tours scheduled for today.</p>
            ) : (
              <div className="space-y-3">
                {todayTours.map((tour) => (
                  <TourCard key={tour.id} tour={tour} apartment={apartments[tour.apartment_id]} />
                ))}
              </div>
            )
          )}

          {activeTab === 'upcoming' && (
            upcomingTours.length === 0 ? (
              <p className="text-center text-gray-500 py-8 text-sm">No upcoming tours scheduled.</p>
            ) : (
              <div className="space-y-3">
                {upcomingTours.map((tour) => (
                  <TourCard key={tour.id} tour={tour} apartment={apartments[tour.apartment_id]} />
                ))}
              </div>
            )
          )}

          {activeTab === 'all' && (
            <div className="space-y-6">
              {stageOrder.map((stage) => {
                const stageTours = toursByStage[stage]
                if (!stageTours || stageTours.length === 0) return null
                return (
                  <div key={stage}>
                    <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">
                      {stageLabels[stage]} ({stageTours.length})
                    </h2>
                    <div className="space-y-3">
                      {stageTours.map((tour) => (
                        <TourCard key={tour.id} tour={tour} apartment={apartments[tour.apartment_id]} />
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}
    </div>
  )
}
