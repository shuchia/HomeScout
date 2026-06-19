'use client'

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import StarRating from '@/components/StarRating'
import TagPicker, { TagSuggestion } from '@/components/TagPicker'
import { TourScheduler } from '@/components/TourScheduler'
import CommutePanel, { CommutePrompt } from '@/components/CommutePanel'
import { useCommuteTimes } from '@/lib/useCommuteTimes'
import {
  getTour,
  updateTour,
  addTourNote,
  deleteTourNote,
  addTourTag,
  removeTourTag,
  getTagSuggestions,
  getApartmentsBatch,
  generateInquiryEmail,
  uploadTourPhoto,
  ApiError,
} from '@/lib/api'
import VoiceCapture from '@/components/VoiceCapture'
import UpgradePrompt from '@/components/UpgradePrompt'
import { Tour, TourStage, TourNote } from '@/types/tour'
import { Apartment } from '@/types/apartment'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const stageConfig: Record<TourStage, { label: string; color: string }> = {
  interested: { label: 'Interested', color: 'bg-emerald-100 text-[var(--color-primary-dark)]' },
  outreach_sent: { label: 'Outreach Sent', color: 'bg-yellow-100 text-yellow-800' },
  scheduled: { label: 'Scheduled', color: 'bg-purple-100 text-purple-800' },
  toured: { label: 'Toured', color: 'bg-green-100 text-green-800' },
  deciding: { label: 'Deciding', color: 'bg-orange-100 text-orange-800' },
}

const formatRent = (rent: number): string =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(rent)

const formatSqft = (sqft: number): string =>
  new Intl.NumberFormat('en-US').format(sqft)

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

// ---------------------------------------------------------------------------
// Tab types
// ---------------------------------------------------------------------------

type Tab = 'info' | 'capture' | 'contact'

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function TourDetailPage() {
  const params = useParams()
  const router = useRouter()
  const tourId = params.id as string

  const { user, loading: authLoading, signInWithGoogle, isPro, profileLoading } = useAuth()

  const [tour, setTour] = useState<Tour | null>(null)
  const [apartment, setApartment] = useState<Apartment | null>(null)
  const [suggestions, setSuggestions] = useState<TagSuggestion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('info')

  // Note form state
  const [noteText, setNoteText] = useState('')
  const [addingNote, setAddingNote] = useState(false)

  // Mutation loading flags
  const [updatingRating, setUpdatingRating] = useState(false)
  const [updatingDecision, setUpdatingDecision] = useState(false)
  const [tagLoading, setTagLoading] = useState(false)

  // ------------------------------------------
  // Data fetching
  // ------------------------------------------

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const [tourRes, suggestionsRes] = await Promise.all([
        getTour(tourId),
        getTagSuggestions(),
      ])
      setTour(tourRes.tour)
      setSuggestions(suggestionsRes.suggestions)

      // Fetch apartment data
      const apartments = await getApartmentsBatch([tourRes.tour.apartment_id])
      if (apartments.length > 0) {
        setApartment(apartments[0])
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setError('Tour not found')
      } else {
        setError('Failed to load tour data')
      }
    } finally {
      setLoading(false)
    }
  }, [tourId])

  useEffect(() => {
    if (!authLoading && !user) return
    if (!authLoading) fetchData()
  }, [authLoading, user, fetchData])

  // ------------------------------------------
  // Transcription polling
  // ------------------------------------------

  const pendingCount = useMemo(
    () => tour?.notes?.filter((n) => n.transcription_status === 'pending').length ?? 0,
    [tour?.notes]
  )

  useEffect(() => {
    if (!pendingCount) return

    const interval = setInterval(async () => {
      try {
        const { tour: updated } = await getTour(tourId)
        setTour(updated)
        const stillPending = updated.notes?.filter((n) => n.transcription_status === 'pending')
        if (!stillPending?.length) clearInterval(interval)
      } catch {
        // Silently retry on next interval
      }
    }, 2000)

    return () => clearInterval(interval)
  }, [pendingCount, tourId])

  // ------------------------------------------
  // Mutation helpers
  // ------------------------------------------

  async function handleRatingChange(rating: number) {
    if (!tour) return
    setUpdatingRating(true)
    try {
      // Auto-advance stage to toured if currently scheduled or earlier
      const stageOrder: TourStage[] = ['interested', 'outreach_sent', 'scheduled', 'toured', 'deciding']
      const currentIdx = stageOrder.indexOf(tour.stage)
      const updates: Record<string, unknown> = { tour_rating: rating }
      if (currentIdx < stageOrder.indexOf('toured')) {
        updates.stage = 'toured'
      }
      const res = await updateTour(tourId, updates as Parameters<typeof updateTour>[1])
      setTour(res.tour)
    } catch {
      // Silently fail; user can retry
    } finally {
      setUpdatingRating(false)
    }
  }

  async function handleDecision(decision: 'applied' | 'passed' | null) {
    if (!tour) return
    setUpdatingDecision(true)
    try {
      const res = await updateTour(tourId, { decision: decision as string })
      setTour(res.tour)
    } catch {
      // Silently fail
    } finally {
      setUpdatingDecision(false)
    }
  }

  async function handleAddNote() {
    if (!tour || !noteText.trim()) return
    setAddingNote(true)
    try {
      await addTourNote(tourId, noteText.trim())
      setNoteText('')
      // Refresh tour to get updated notes
      const res = await getTour(tourId)
      setTour(res.tour)
    } catch {
      // Silently fail
    } finally {
      setAddingNote(false)
    }
  }

  async function handleDeleteNote(noteId: string) {
    if (!tour) return
    try {
      await deleteTourNote(tourId, noteId)
      const res = await getTour(tourId)
      setTour(res.tour)
    } catch {
      // Silently fail
    }
  }

  async function handleVoiceNoteCreated() {
    try {
      const res = await getTour(tourId)
      setTour(res.tour)
    } catch {
      // Silently fail
    }
  }

  async function handleAddTag(tag: string, sentiment: 'pro' | 'con') {
    if (!tour) return
    setTagLoading(true)
    try {
      await addTourTag(tourId, tag, sentiment)
      const res = await getTour(tourId)
      setTour(res.tour)
    } catch {
      // Silently fail
    } finally {
      setTagLoading(false)
    }
  }

  async function handleRemoveTag(tagId: string) {
    if (!tour) return
    setTagLoading(true)
    try {
      await removeTourTag(tourId, tagId)
      const res = await getTour(tourId)
      setTour(res.tour)
    } catch {
      // Silently fail
    } finally {
      setTagLoading(false)
    }
  }

  // ------------------------------------------
  // Auth gate
  // ------------------------------------------

  if (authLoading) {
    return <LoadingSkeleton />
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-4">
        <div className="bg-white rounded-lg shadow p-6 text-center max-w-sm w-full">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Sign in required</h2>
          <p className="text-sm text-gray-500 mb-4">Sign in to view your tour details.</p>
          <button
            onClick={signInWithGoogle}
            className="w-full bg-[var(--color-primary)] text-white font-medium py-2.5 px-4 rounded-lg hover:bg-[var(--color-primary-light)] transition-colors"
          >
            Sign in with Google
          </button>
        </div>
      </div>
    )
  }

  if (loading) {
    return <LoadingSkeleton />
  }

  if (error || !tour) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-4">
        <div className="bg-white rounded-lg shadow p-6 text-center max-w-sm w-full">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">
            {error === 'Tour not found' ? 'Tour Not Found' : 'Error'}
          </h2>
          <p className="text-sm text-gray-500 mb-4">
            {error === 'Tour not found'
              ? 'This tour does not exist or you do not have access.'
              : 'Something went wrong loading the tour.'}
          </p>
          <Link
            href="/tours"
            className="inline-block bg-[var(--color-primary)] text-white font-medium py-2 px-4 rounded-lg hover:bg-[var(--color-primary-light)] transition-colors"
          >
            Back to Tours
          </Link>
        </div>
      </div>
    )
  }

  const stage = stageConfig[tour.stage]
  const showDecisionBar = tour.stage === 'toured' || tour.stage === 'deciding'

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* ---- Header ---- */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-20">
        <div className="flex items-center gap-3 px-4 py-3 max-w-2xl mx-auto">
          <Link
            href="/tours"
            className="shrink-0 p-1 -ml-1 text-gray-500 hover:text-gray-900 transition-colors"
            aria-label="Back to tours"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </Link>
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-gray-900 truncate text-sm">
              {apartment?.address ?? 'Loading address...'}
            </p>
            {apartment && (
              <p className="text-xs text-gray-500">
                {formatRent(apartment.rent)}/mo
              </p>
            )}
          </div>
          <span className={`shrink-0 px-2.5 py-0.5 rounded-full text-xs font-medium ${stage.color}`}>
            {stage.label}
          </span>
        </div>
      </header>

      {/* ---- Tab bar ---- */}
      <nav className="bg-white border-b border-gray-200 sticky top-[57px] z-10">
        <div className="flex max-w-2xl mx-auto">
          {(['info', 'capture', 'contact'] as Tab[]).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-2.5 text-sm font-medium text-center capitalize transition-colors
                ${activeTab === tab
                  ? 'text-[var(--color-primary)] border-b-2 border-[var(--color-primary)]'
                  : 'text-gray-500 hover:text-gray-700 border-b-2 border-transparent'
                }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </nav>

      {/* ---- Tab content ---- */}
      <main className={`flex-1 overflow-y-auto ${showDecisionBar ? 'pb-20' : 'pb-4'}`}>
        <div className="max-w-2xl mx-auto p-4">
          {activeTab === 'info' && (
            <InfoTab apartment={apartment} tour={tour} onTourUpdate={setTour} />
          )}
          {activeTab === 'capture' && (
            <CaptureTab
              tour={tour}
              tourId={tourId}
              suggestions={suggestions}
              updatingRating={updatingRating}
              onRatingChange={handleRatingChange}
              noteText={noteText}
              onNoteTextChange={setNoteText}
              addingNote={addingNote}
              onAddNote={handleAddNote}
              onDeleteNote={handleDeleteNote}
              onVoiceNoteCreated={handleVoiceNoteCreated}
              tagLoading={tagLoading}
              onAddTag={handleAddTag}
              onRemoveTag={handleRemoveTag}
            />
          )}
          {activeTab === 'contact' && (
            <ContactTab tour={tour} apartment={apartment} isPro={isPro} profileLoading={profileLoading} onTourUpdate={setTour} />
          )}
        </div>
      </main>

      {/* ---- Decision bar ---- */}
      {showDecisionBar && (
        <div className="fixed bottom-14 md:bottom-0 inset-x-0 bg-white border-t border-gray-200 z-40">
          <div className="max-w-2xl mx-auto px-3 py-2 md:px-4 md:py-3 flex gap-2">
            <button
              type="button"
              onClick={() => handleDecision(tour.decision === 'applied' ? null : 'applied')}
              disabled={updatingDecision}
              className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-colors
                ${tour.decision === 'applied'
                  ? 'bg-green-600 text-white'
                  : 'bg-green-50 text-green-700 border border-green-200 hover:bg-green-100'
                }
                disabled:opacity-50`}
            >
              Applied
            </button>
            <button
              type="button"
              onClick={() => handleDecision(tour.decision === 'passed' ? null : 'passed')}
              disabled={updatingDecision}
              className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-colors
                ${tour.decision === 'passed'
                  ? 'bg-gray-600 text-white'
                  : 'bg-gray-50 text-gray-700 border border-gray-200 hover:bg-gray-100'
                }
                disabled:opacity-50`}
            >
              Pass
            </button>
            <button
              type="button"
              onClick={() => handleDecision(null)}
              disabled={updatingDecision || tour.decision === null}
              className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-colors
                border border-gray-200 text-gray-600 hover:bg-gray-50
                ${tour.decision === null ? 'ring-2 ring-[var(--color-primary)] bg-emerald-50 text-[var(--color-primary)]' : ''}
                disabled:opacity-50`}
            >
              Undecided
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Info Tab
// ---------------------------------------------------------------------------

function InfoTab({ apartment, tour, onTourUpdate }: { apartment: Apartment | null; tour: Tour; onTourUpdate: (tour: Tour) => void }) {
  const [editingPhone, setEditingPhone] = useState(false)
  const [editingEmail, setEditingEmail] = useState(false)
  const [phoneValue, setPhoneValue] = useState(tour.contact_phone || '')
  const [emailValue, setEmailValue] = useState(tour.contact_email || '')

  // Commute times to the user's saved work/school addresses (hook must run
  // before the early return below).
  const { byApt, hasLocations } = useCommuteTimes(apartment ? [apartment.id] : [])

  async function savePhone(value: string) {
    const trimmed = value.trim()
    try {
      const res = await updateTour(tour.id, { contact_phone: trimmed })
      onTourUpdate(res.tour)
    } catch { /* silent */ }
    setEditingPhone(false)
  }

  async function saveEmail(value: string) {
    const trimmed = value.trim()
    try {
      const res = await updateTour(tour.id, { contact_email: trimmed })
      onTourUpdate(res.tour)
    } catch { /* silent */ }
    setEditingEmail(false)
  }

  // Sync local state when tour updates externally
  useEffect(() => {
    setPhoneValue(tour.contact_phone || '')
    setEmailValue(tour.contact_email || '')
  }, [tour.contact_phone, tour.contact_email])

  if (!apartment) {
    return <p className="text-sm text-gray-500">Apartment details not available.</p>
  }

  return (
    <div className="space-y-6">
      {/* Quick stats */}
      <div className="grid grid-cols-2 gap-3">
        <Stat label="Rent" value={`${formatRent(apartment.rent)}/mo`} />
        <Stat label="Bedrooms" value={apartment.bedrooms === 0 ? 'Studio' : String(apartment.bedrooms)} />
        <Stat label="Bathrooms" value={String(apartment.bathrooms)} />
        <Stat label="Size" value={apartment.sqft ? `${formatSqft(apartment.sqft)} sqft` : 'N/A'} />
        <Stat label="Type" value={apartment.property_type || 'N/A'} />
        <Stat label="Available" value={apartment.available_date || 'N/A'} />
      </div>

      {/* Commute times to saved work/school addresses */}
      {byApt[apartment.id]?.length ? (
        <CommutePanel commutes={byApt[apartment.id]} />
      ) : hasLocations === false ? (
        <CommutePrompt />
      ) : null}

      {/* Contact Info */}
      <section>
        <h3 className="text-sm font-semibold text-gray-900 mb-2">Property Contact</h3>
        <div className="space-y-2">
          {/* Phone */}
          <div className="flex items-center gap-2 bg-white rounded-lg border border-gray-200 p-3">
            <svg className="h-4 w-4 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
            </svg>
            {editingPhone ? (
              <input
                type="tel"
                value={phoneValue}
                onChange={(e) => setPhoneValue(e.target.value)}
                onBlur={() => savePhone(phoneValue)}
                onKeyDown={(e) => { if (e.key === 'Enter') savePhone(phoneValue) }}
                placeholder="Add phone number"
                className="flex-1 text-sm bg-transparent outline-none"
                autoFocus
              />
            ) : tour.contact_phone ? (
              <div className="flex-1 flex items-center justify-between">
                <a href={`tel:${tour.contact_phone}`} className="text-sm text-[var(--color-primary)] font-medium hover:underline">
                  {tour.contact_phone}
                </a>
                <button type="button" onClick={() => setEditingPhone(true)} className="text-gray-400 hover:text-gray-600">
                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                  </svg>
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setEditingPhone(true)}
                className="flex-1 text-sm text-gray-400 text-left hover:text-gray-600"
              >
                Add phone number
              </button>
            )}
          </div>

          {/* Email */}
          <div className="flex items-center gap-2 bg-white rounded-lg border border-gray-200 p-3">
            <svg className="h-4 w-4 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            {editingEmail ? (
              <input
                type="email"
                value={emailValue}
                onChange={(e) => setEmailValue(e.target.value)}
                onBlur={() => saveEmail(emailValue)}
                onKeyDown={(e) => { if (e.key === 'Enter') saveEmail(emailValue) }}
                placeholder="Add email address"
                className="flex-1 text-sm bg-transparent outline-none"
                autoFocus
              />
            ) : tour.contact_email ? (
              <div className="flex-1 flex items-center justify-between">
                <a href={`mailto:${tour.contact_email}`} className="text-sm text-[var(--color-primary)] font-medium hover:underline">
                  {tour.contact_email}
                </a>
                <button type="button" onClick={() => setEditingEmail(true)} className="text-gray-400 hover:text-gray-600">
                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                  </svg>
                </button>
              </div>
            ) : (
              // Most apartments.com listings don't expose a public email.
              // Surface the workaround instead of a dead "Add email" CTA.
              <span className="flex-1 text-xs text-gray-500 leading-snug">
                Most properties don&rsquo;t list a public email. Use the{' '}
                <span className="font-medium text-gray-700">Contact</span>{' '}
                tab to call, text, or send via apartments.com&rsquo;s form.{' '}
                <button
                  type="button"
                  onClick={() => setEditingEmail(true)}
                  className="underline underline-offset-2 hover:text-gray-700"
                >
                  Add manually
                </button>
              </span>
            )}
          </div>
        </div>
      </section>

      {/* Schedule Tour Section */}
      <TourScheduler tour={tour} onUpdate={onTourUpdate} />

      {/* Amenities */}
      {apartment.amenities.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-gray-900 mb-2">Amenities</h3>
          <div className="flex flex-wrap gap-2">
            {apartment.amenities.map((amenity) => (
              <span
                key={amenity}
                className="inline-block px-2.5 py-1 bg-gray-100 text-gray-700 text-xs rounded-full"
              >
                {amenity}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Description */}
      {apartment.description && (
        <section>
          <h3 className="text-sm font-semibold text-gray-900 mb-2">Description</h3>
          <p className="text-sm text-gray-600 whitespace-pre-line leading-relaxed">
            {apartment.description}
          </p>
        </section>
      )}

      {/* Images */}
      {apartment.images.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-gray-900 mb-2">Photos</h3>
          <div className="grid grid-cols-2 gap-2">
            {apartment.images.map((url, i) => (
              <div key={i} className="aspect-video bg-gray-200 rounded-lg overflow-hidden">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={url}
                  alt={`Photo ${i + 1}`}
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-sm font-semibold text-gray-900 mt-0.5">{value}</p>
    </div>
  )
}

function formatTime(time: string): string {
  const [h, m] = time.split(':')
  const hour = parseInt(h, 10)
  const ampm = hour >= 12 ? 'PM' : 'AM'
  const hour12 = hour % 12 || 12
  return `${hour12}:${m} ${ampm}`
}

// ---------------------------------------------------------------------------
// Capture Tab
// ---------------------------------------------------------------------------

interface CaptureTabProps {
  tour: Tour
  tourId: string
  suggestions: TagSuggestion[]
  updatingRating: boolean
  onRatingChange: (rating: number) => void
  noteText: string
  onNoteTextChange: (text: string) => void
  addingNote: boolean
  onAddNote: () => void
  onDeleteNote: (noteId: string) => void
  onVoiceNoteCreated: () => void
  tagLoading: boolean
  onAddTag: (tag: string, sentiment: 'pro' | 'con') => void
  onRemoveTag: (tagId: string) => void
}

function CaptureTab({
  tour,
  tourId,
  suggestions,
  updatingRating,
  onRatingChange,
  noteText,
  onNoteTextChange,
  addingNote,
  onAddNote,
  onDeleteNote,
  onVoiceNoteCreated,
  tagLoading,
  onAddTag,
  onRemoveTag,
}: CaptureTabProps) {
  // Photo upload — local to this tab. Reuses onVoiceNoteCreated as a generic
  // "refetch the tour" trigger after a successful upload.
  const photoInputRef = useRef<HTMLInputElement | null>(null)
  const [uploadingPhoto, setUploadingPhoto] = useState(false)
  const [photoError, setPhotoError] = useState<string | null>(null)

  const handlePhotoSelected = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      // Reset input so selecting the same file twice re-fires onChange
      if (e.target) e.target.value = ''
      if (!file) return

      if (!file.type.startsWith('image/')) {
        setPhotoError('Please choose an image file.')
        return
      }
      if (file.size > 10 * 1024 * 1024) {
        setPhotoError('Image too large (max 10 MB).')
        return
      }

      setPhotoError(null)
      setUploadingPhoto(true)
      try {
        await uploadTourPhoto(tourId, file)
        onVoiceNoteCreated()
      } catch {
        setPhotoError('Upload failed. Please try again.')
      } finally {
        setUploadingPhoto(false)
      }
    },
    [tourId, onVoiceNoteCreated],
  )

  return (
    <div className="space-y-6">
      {/* Rating */}
      <section>
        <h3 className="text-sm font-semibold text-gray-900 mb-2">Rating</h3>
        <StarRating
          value={tour.tour_rating}
          onChange={onRatingChange}
          size="lg"
          readOnly={updatingRating}
        />
      </section>

      {/* Tags */}
      <section>
        <h3 className="text-sm font-semibold text-gray-900 mb-2">Quick Tags</h3>
        <TagPicker
          tags={tour.tags}
          suggestions={suggestions}
          onAdd={onAddTag}
          onRemove={onRemoveTag}
          loading={tagLoading}
        />
      </section>

      {/* Notes */}
      <section>
        <h3 className="text-sm font-semibold text-gray-900 mb-2">Notes</h3>
        <div className="space-y-3">
          {/* Add note form */}
          <div className="flex gap-2">
            <textarea
              value={noteText}
              onChange={(e) => onNoteTextChange(e.target.value)}
              placeholder="Add a note..."
              rows={2}
              className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm
                focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent
                resize-none"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  onAddNote()
                }
              }}
            />
            <button
              type="button"
              onClick={onAddNote}
              disabled={addingNote || !noteText.trim()}
              className="self-end shrink-0 bg-[var(--color-primary)] text-white px-4 py-2 rounded-lg text-sm
                font-medium hover:bg-[var(--color-primary-light)] transition-colors
                disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {addingNote ? '...' : 'Add'}
            </button>
          </div>

          {/* Voice capture */}
          <VoiceCapture tourId={tourId} onNoteCreated={onVoiceNoteCreated} />

          {/* Existing notes */}
          {tour.notes.length > 0 ? (
            <ul className="space-y-2">
              {tour.notes.map((note) => (
                <NoteItem
                  key={note.id}
                  note={note}
                  onDelete={() => onDeleteNote(note.id)}
                />
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400">No notes yet.</p>
          )}
        </div>
      </section>

      {/* Photos */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-gray-900">Photos</h3>
          <button
            type="button"
            onClick={() => photoInputRef.current?.click()}
            disabled={uploadingPhoto}
            className="text-xs font-medium text-[var(--color-primary)] disabled:text-gray-400 disabled:cursor-not-allowed"
          >
            {uploadingPhoto ? 'Uploading…' : '+ Add Photo'}
          </button>
        </div>
        <input
          ref={photoInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={handlePhotoSelected}
        />
        {tour.photos.length > 0 ? (
          <div className="grid grid-cols-3 gap-2">
            {tour.photos.map((photo) => (
              <div key={photo.id} className="aspect-square bg-gray-200 rounded-lg overflow-hidden">
                {photo.thumbnail_url ? (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img
                    src={photo.thumbnail_url}
                    alt={photo.caption || 'Tour photo'}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-gray-400">
                    <svg className="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <button
            type="button"
            onClick={() => photoInputRef.current?.click()}
            disabled={uploadingPhoto}
            className="w-full border-2 border-dashed border-gray-200 rounded-lg p-6 text-center hover:bg-gray-50 active:bg-gray-100 transition-colors disabled:cursor-not-allowed"
          >
            <svg className="h-8 w-8 text-gray-300 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <p className="text-sm text-gray-500">
              {uploadingPhoto ? 'Uploading…' : 'No photos yet — tap to add one'}
            </p>
          </button>
        )}
        {photoError && (
          <p className="text-xs text-red-500 mt-2">{photoError}</p>
        )}
      </section>
    </div>
  )
}

function NoteItem({ note, onDelete }: { note: TourNote; onDelete: () => void }) {
  const renderContent = () => {
    if (note.source === 'voice') {
      if (note.transcription_status === 'pending') {
        return (
          <span className="text-gray-400 italic animate-pulse text-sm">Transcribing...</span>
        )
      }
      if (note.transcription_status === 'failed') {
        return (
          <span className="text-red-500 text-sm">Transcription failed</span>
        )
      }
      return (
        <p className="text-sm text-gray-700 whitespace-pre-line">{note.content}</p>
      )
    }
    return (
      <p className="text-sm text-gray-700 whitespace-pre-line">{note.content}</p>
    )
  }

  return (
    <li className="bg-white border border-gray-200 rounded-lg p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2 min-w-0 flex-1">
          {/* Source icon */}
          {note.source === 'voice' ? (
            <svg className="h-4 w-4 text-[var(--color-primary)] mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
            </svg>
          ) : (
            <svg className="h-4 w-4 text-gray-400 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
            </svg>
          )}
          {renderContent()}
        </div>
        <button
          type="button"
          onClick={onDelete}
          className="shrink-0 p-1 text-gray-300 hover:text-red-500 transition-colors"
          aria-label="Delete note"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      </div>
      <p className="text-xs text-gray-400 mt-1.5">{formatDate(note.created_at)}</p>
    </li>
  )
}

// ---------------------------------------------------------------------------
// Email Tab
// ---------------------------------------------------------------------------

// apartments.com's contact form caps the message field at 400 chars. The
// backend prompt now asks Claude for ≤320 chars, so in the common case
// this function is a no-op and what we paste is the AI's full message.
// The trim below is defensive — if a regenerate ever runs long, we cut
// at the last sentence boundary (period / question / exclamation) before
// the limit so the pasted text never ends mid-word like "this prope…".
const SHORT_MESSAGE_MAX_CHARS = 380

function buildShortMessage(emailBody: string): string {
  if (!emailBody) return ''
  const body = emailBody.trim()
  if (body.length <= SHORT_MESSAGE_MAX_CHARS) return body

  // Find the last full sentence that fits. Look for `.`, `!`, `?`
  // followed by whitespace or end-of-string.
  const window = body.slice(0, SHORT_MESSAGE_MAX_CHARS)
  const sentenceEnd = Math.max(
    window.lastIndexOf('. '),
    window.lastIndexOf('! '),
    window.lastIndexOf('? '),
    window.lastIndexOf('.\n'),
    window.lastIndexOf('!\n'),
    window.lastIndexOf('?\n'),
  )
  if (sentenceEnd > SHORT_MESSAGE_MAX_CHARS * 0.5) {
    // Found a sentence break in the back half — clean cut, keep the
    // terminating punctuation, drop everything after.
    return body.slice(0, sentenceEnd + 1).trim()
  }
  // No reasonable sentence boundary — fall back to a word boundary so we
  // at least don't slice mid-word.
  const wordBreak = window.lastIndexOf(' ')
  if (wordBreak > SHORT_MESSAGE_MAX_CHARS * 0.5) {
    return body.slice(0, wordBreak).trim() + '…'
  }
  // Truly nothing to grab — bail at the hard limit. Rare.
  return body.slice(0, SHORT_MESSAGE_MAX_CHARS - 1).trim() + '…'
}

// Normalize "(412) 231-9292" → "+14122319292" for tel:/sms: links
function normalizePhoneForLink(raw: string | null | undefined): string | null {
  if (!raw) return null
  const digits = raw.replace(/\D/g, '')
  if (digits.length === 10) return `+1${digits}`
  if (digits.length === 11 && digits.startsWith('1')) return `+${digits}`
  return digits ? `+${digits}` : null
}

function ContactTab({
  tour,
  apartment,
  isPro,
  profileLoading,
  onTourUpdate,
}: {
  tour: Tour
  apartment: Apartment | null
  isPro: boolean
  profileLoading?: boolean
  onTourUpdate: (tour: Tour) => void
}) {
  // After-action confirmation was replaced with a pre-action hint
  // (rendered below the buttons). We still surface a banner if the
  // clipboard write actually fails — rare, but the user shouldn't be
  // left assuming the message landed when it didn't.
  const [clipboardError, setClipboardError] = useState<string | null>(null)
  // Brief in-place "Copied!" feedback for the small Copy link next to
  // the message preview — that one stays in view, so a 1.5s flash there
  // is actually useful (vs. the apartments.com buttons where the user's
  // focus has already moved to the new tab).
  const [previewCopied, setPreviewCopied] = useState(false)
  // Editable copy of the draft body. Initialized from the saved draft;
  // user edits live here, debounced-saved on textarea blur. All copy
  // actions use this value (not the original draft) so what gets pasted
  // reflects the user's tweaks.
  const [editedBody, setEditedBody] = useState('')
  const [savingDraft, setSavingDraft] = useState(false)
  const [emailLoading, setEmailLoading] = useState(false)
  const [emailError, setEmailError] = useState<string | null>(null)
  const [markingSent, setMarkingSent] = useState(false)

  // The AI-drafted inquiry email drives all three contact paths (call
  // script reference, SMS body, apartments.com form message).
  const emailDraft = tour.inquiry_email_draft
  let emailSubject = ''
  let savedBody = ''
  if (emailDraft) {
    const doubleNewline = emailDraft.indexOf('\n\n')
    if (doubleNewline !== -1) {
      const firstLine = emailDraft.slice(0, doubleNewline)
      emailSubject = firstLine.startsWith('Subject: ') ? firstLine.slice(9) : firstLine
      savedBody = emailDraft.slice(doubleNewline + 2)
    } else {
      savedBody = emailDraft
    }
  }

  // Sync the editable textarea state with the saved draft whenever the
  // saved draft changes (initial load, after a Regenerate). Without this
  // a regenerated draft would silently vanish from the textarea.
  useEffect(() => {
    setEditedBody(savedBody)
  }, [savedBody])

  // Effective body: what the user is currently editing. Falls back to
  // the saved body if state hasn't been initialized yet.
  const effectiveBody = editedBody || savedBody
  const isEdited = editedBody !== savedBody && editedBody.length > 0

  const phoneForLink = normalizePhoneForLink(tour.contact_phone || apartment?.contact_phone)
  const phoneDisplay = tour.contact_phone || apartment?.contact_phone || null
  const sourceUrl = apartment?.source_url || null
  const shortMessage = effectiveBody ? buildShortMessage(effectiveBody) : ''
  const shortMessageTruncated = effectiveBody.length > shortMessage.length

  // Opens the apartments.com listing in a new tab with the short version
  // of (the user-edited) message already in the clipboard. The URL is
  // suffixed with a fragment that targets the relevant CTA button on
  // apartments.com — IDs verified against the live DOM (task #28). On
  // desktop the CTAs are in the sticky right rail and already above the
  // fold; the fragment mainly helps mobile, where the page content sits
  // above the CTA stack. The fragment scrolls the button into view but
  // does NOT auto-click — the user still taps to open the modal, then
  // pastes the pre-copied message.
  async function openListing(intent: 'contact' | 'tour') {
    if (!sourceUrl) return
    setClipboardError(null)
    // Fire-and-forget the persistence; we don't await before opening the
    // tab so the user gesture stays bound to window.open (popup-blocker
    // safety). The save happens server-side while the new tab loads.
    if (isEdited) void saveEditIfChanged()
    if (shortMessage) {
      try {
        await navigator.clipboard.writeText(shortMessage)
      } catch {
        setClipboardError(
          'Couldn’t copy automatically. Use the Copy link on the message below before going to apartments.com.'
        )
      }
    }
    // Anchor IDs verified against apartments.com's live DOM (Aera listing,
    // 2026-06-18). Both buttons live in <div class="ctaContainer"> within
    // the stickyContactRightRail; on desktop they're always in view, on
    // mobile this fragment scrolls them into view.
    const anchor = intent === 'tour' ? '#checkAvailabilityTourBtn' : '#sendMessageBtn'
    window.open(sourceUrl + anchor, '_blank', 'noopener,noreferrer')
  }

  // Explicit "Copy" button next to the message preview copies the FULL
  // draft (not the short version), since the user clicking that button
  // probably wants to use it in a longer-form channel like their own
  // email client.
  async function handleCopyMessage() {
    if (!effectiveBody) return
    setClipboardError(null)
    try {
      await navigator.clipboard.writeText(effectiveBody)
      setPreviewCopied(true)
      setTimeout(() => setPreviewCopied(false), 1500)
    } catch {
      setClipboardError('Couldn’t copy to clipboard. Select the message text and copy manually.')
    }
  }

  // Persist edits to the inquiry message when the user blurs the
  // textarea (or clicks an action button). Only saves if the body
  // actually changed from what's on the server.
  async function saveEditIfChanged() {
    if (!isEdited) return
    setSavingDraft(true)
    try {
      const newDraft = emailSubject
        ? `Subject: ${emailSubject}\n\n${editedBody}`
        : editedBody
      const res = await updateTour(tour.id, { inquiry_email_draft: newDraft })
      onTourUpdate(res.tour)
    } catch {
      // Silent — user's edits still live in local state for this session
    } finally {
      setSavingDraft(false)
    }
  }

  async function handleGenerate() {
    setEmailLoading(true)
    setEmailError(null)
    try {
      await generateInquiryEmail(tour.id)
      const res = await getTour(tour.id)
      onTourUpdate(res.tour)
    } catch (err) {
      if (err instanceof ApiError) {
        setEmailError(err.message)
      } else {
        setEmailError('Failed to generate message. Please try again.')
      }
    } finally {
      setEmailLoading(false)
    }
  }

  async function handleMarkOutreachSent() {
    setMarkingSent(true)
    try {
      const res = await updateTour(tour.id, { stage: 'outreach_sent' })
      onTourUpdate(res.tour)
    } catch {
      // Silently fail
    } finally {
      setMarkingSent(false)
    }
  }

  if (profileLoading) {
    return (
      <div className="py-8">
        <div className="h-10 bg-gray-100 rounded-lg animate-pulse" />
      </div>
    )
  }

  if (!isPro) {
    return (
      <div className="py-8">
        <UpgradePrompt feature="AI-generated inquiry messages and one-tap contact" />
      </div>
    )
  }

  // No draft yet — empty state explains the channel choices we unlock once
  // the message exists.
  if (!emailDraft) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <svg className="h-12 w-12 text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
        <h3 className="text-sm font-semibold text-gray-900 mb-1">No message draft yet</h3>
        <p className="text-sm text-gray-500 mb-4 text-center px-6">
          Snugd will draft a personalized inquiry you can use to call, text,
          or paste into the property&rsquo;s contact form on apartments.com.
        </p>
        {emailError && (
          <div className="mb-4 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
            {emailError}
          </div>
        )}
        <button
          type="button"
          onClick={handleGenerate}
          disabled={emailLoading}
          className="bg-[var(--color-primary)] text-white px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-[var(--color-primary-light)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {emailLoading ? (
            <>
              <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Generating&hellip;
            </>
          ) : (
            'Generate Inquiry Message'
          )}
        </button>
      </div>
    )
  }

  // Have a draft — three channel actions, message preview below.
  return (
    <div className="space-y-4">
      {/* Phone-first because apartments.com doesn't expose leasing-office
          emails; the message-and-form path is the explicit "I want to
          write" choice rather than the default. */}
      <div className="grid gap-2">
        {phoneForLink ? (
          <a
            href={`tel:${phoneForLink}`}
            className="flex items-center justify-center gap-2 bg-[var(--color-primary)] text-white px-4 py-3 rounded-lg text-sm font-semibold hover:bg-[var(--color-primary-light)] transition-colors"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
            </svg>
            Call {phoneDisplay}
          </a>
        ) : (
          <div className="flex items-center justify-center gap-2 bg-gray-50 text-gray-400 px-4 py-3 rounded-lg text-sm">
            No phone number on file for this property
          </div>
        )}

        {phoneForLink && shortMessage && (
          <a
            href={`sms:${phoneForLink}?body=${encodeURIComponent(shortMessage)}`}
            onClick={() => { if (isEdited) void saveEditIfChanged() }}
            className="flex items-center justify-center gap-2 bg-emerald-50 text-emerald-800 border border-emerald-200 px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-emerald-100 transition-colors"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            Text leasing office (draft pre-filled)
          </a>
        )}

        {sourceUrl && (
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => openListing('contact')}
              className="flex items-center justify-center gap-2 bg-gray-100 text-gray-800 border border-gray-200 px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-gray-200 transition-colors"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              Contact this property
            </button>
            <button
              type="button"
              onClick={() => openListing('tour')}
              className="flex items-center justify-center gap-2 bg-gray-100 text-gray-800 border border-gray-200 px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-gray-200 transition-colors"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              Schedule a tour
            </button>
          </div>
        )}
      </div>

      {/* Pre-action hint. Trimmed to a single line — char counts and
          form-limit mechanics aren't user-relevant; what is, is the
          paste gesture once they land on apartments.com. */}
      {sourceUrl && shortMessage && (
        <p className="text-xs text-gray-500 px-1 leading-snug">
          We&rsquo;ll copy your message and open apartments.com — paste it into
          the form with <span className="font-medium">long-press → Paste</span>{' '}
          or <span className="font-medium">Cmd/Ctrl + V</span>.
        </p>
      )}

      {/* Error banner — only shown if a clipboard write actually failed.
          Rare (clipboard API is well-supported in HTTPS contexts with a
          user gesture) but worth surfacing because the new tab is already
          opening and the user otherwise has no signal that they have
          nothing on their clipboard. */}
      {clipboardError && (
        <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5 text-sm text-amber-900">
          <svg className="h-5 w-5 mt-0.5 shrink-0 text-amber-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="flex-1 leading-snug">{clipboardError}</p>
          <button
            type="button"
            onClick={() => setClipboardError(null)}
            aria-label="Dismiss"
            className="text-amber-700 hover:text-amber-900 -m-1 p-1"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* Drafted message preview — what gets pre-filled into SMS and
          copied for the apartments.com form. Showing it inline lets the
          user review/edit context before sending. */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-gray-900">Drafted Message</h3>
            {isEdited && (
              <span className="text-[10px] uppercase tracking-wide text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                {savingDraft ? 'Saving…' : 'Edited'}
              </span>
            )}
          </div>
          <div className="flex gap-3 text-xs">
            <button
              type="button"
              onClick={handleCopyMessage}
              className="text-gray-500 hover:text-gray-800 underline-offset-2 hover:underline"
            >
              {previewCopied ? 'Copied!' : 'Copy'}
            </button>
            <button
              type="button"
              onClick={handleGenerate}
              disabled={emailLoading}
              className="text-gray-500 hover:text-gray-800 underline-offset-2 hover:underline disabled:opacity-50"
            >
              {emailLoading ? 'Regenerating…' : 'Regenerate'}
            </button>
          </div>
        </div>
        <div className="bg-gray-50 rounded-lg p-3">
          {emailSubject && (
            <>
              <p className="text-xs uppercase tracking-wide text-gray-500 mb-1">Subject</p>
              <p className="font-medium text-gray-900 mb-3">{emailSubject}</p>
            </>
          )}
          {/* Editable textarea. Edits are debounced-saved on blur via
              saveEditIfChanged(); they're also flushed when the user
              clicks any of the Contact/Schedule/SMS action buttons. */}
          <textarea
            value={editedBody}
            onChange={(e) => setEditedBody(e.target.value)}
            onBlur={saveEditIfChanged}
            rows={Math.min(12, Math.max(5, editedBody.split('\n').length + 1))}
            className="w-full bg-transparent text-gray-700 text-sm leading-relaxed resize-y focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)] rounded p-1 -m-1"
            placeholder="Your drafted message will appear here once generated."
          />
        </div>
      </div>

      {/* Fallback mailto: — only if the user manually entered a contact
          email on the Info tab. apartments.com itself almost never gives one. */}
      {tour.contact_email && (
        <a
          href={`mailto:${tour.contact_email}?subject=${encodeURIComponent(emailSubject)}&body=${encodeURIComponent(effectiveBody)}`}
          onClick={() => { if (isEdited) void saveEditIfChanged() }}
          className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-800 underline-offset-2 hover:underline"
        >
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
          Or open in email app ({tour.contact_email})
        </a>
      )}

      {tour.stage === 'interested' && (
        <button
          type="button"
          onClick={handleMarkOutreachSent}
          disabled={markingSent}
          className="w-full flex items-center justify-center gap-2 bg-yellow-50 text-yellow-800 border border-yellow-200 px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-yellow-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {markingSent ? (
            <>
              <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Updating&hellip;
            </>
          ) : (
            <>
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Mark Outreach as Sent
            </>
          )}
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function LoadingSkeleton() {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200 px-4 py-3">
        <div className="max-w-2xl mx-auto flex items-center gap-3">
          <div className="h-5 w-5 bg-gray-200 rounded animate-pulse" />
          <div className="flex-1 space-y-1.5">
            <div className="h-4 w-48 bg-gray-200 rounded animate-pulse" />
            <div className="h-3 w-24 bg-gray-200 rounded animate-pulse" />
          </div>
          <div className="h-5 w-16 bg-gray-200 rounded-full animate-pulse" />
        </div>
      </div>
      <div className="bg-white border-b border-gray-200 px-4">
        <div className="max-w-2xl mx-auto flex gap-4 py-3">
          <div className="h-4 w-12 bg-gray-200 rounded animate-pulse" />
          <div className="h-4 w-16 bg-gray-200 rounded animate-pulse" />
          <div className="h-4 w-12 bg-gray-200 rounded animate-pulse" />
        </div>
      </div>
      <div className="max-w-2xl mx-auto p-4 space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-20 bg-gray-200 rounded-lg animate-pulse" />
        ))}
      </div>
    </div>
  )
}
