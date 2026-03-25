'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import StarRating from '@/components/StarRating'
import TagPicker, { TagSuggestion } from '@/components/TagPicker'
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

type Tab = 'info' | 'capture' | 'email'

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function TourDetailPage() {
  const params = useParams()
  const router = useRouter()
  const tourId = params.id as string

  const { user, loading: authLoading, signInWithGoogle, isPro } = useAuth()

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
          {(['info', 'capture', 'email'] as Tab[]).map((tab) => (
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
            <InfoTab apartment={apartment} tour={tour} />
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
          {activeTab === 'email' && (
            <EmailTab tour={tour} isPro={isPro} onTourUpdate={setTour} />
          )}
        </div>
      </main>

      {/* ---- Decision bar ---- */}
      {showDecisionBar && (
        <div className="fixed bottom-0 inset-x-0 bg-white border-t border-gray-200 z-20">
          <div className="max-w-2xl mx-auto px-4 py-3 flex gap-2">
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

function InfoTab({ apartment, tour }: { apartment: Apartment | null; tour: Tour }) {
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

      {/* Scheduled date if present */}
      {tour.scheduled_date && (
        <div className="bg-purple-50 rounded-lg p-3">
          <p className="text-xs font-medium text-purple-600 uppercase tracking-wide mb-1">Tour Scheduled</p>
          <p className="text-sm text-purple-800 font-medium">
            {new Date(tour.scheduled_date + 'T00:00:00').toLocaleDateString('en-US', {
              weekday: 'long',
              month: 'long',
              day: 'numeric',
            })}
            {tour.scheduled_time && (
              <span className="ml-1">
                at {formatTime(tour.scheduled_time)}
              </span>
            )}
          </p>
        </div>
      )}

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
        <h3 className="text-sm font-semibold text-gray-900 mb-2">Photos</h3>
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
          <div className="border-2 border-dashed border-gray-200 rounded-lg p-6 text-center">
            <svg className="h-8 w-8 text-gray-300 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <p className="text-sm text-gray-400">No photos yet</p>
            <p className="text-xs text-gray-300 mt-1">Photo upload coming soon</p>
          </div>
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

function EmailTab({ tour, isPro, onTourUpdate }: { tour: Tour; isPro: boolean; onTourUpdate: (tour: Tour) => void }) {
  const [copied, setCopied] = useState(false)
  const [emailLoading, setEmailLoading] = useState(false)
  const [emailError, setEmailError] = useState<string | null>(null)

  // Parse the draft into subject and body
  const emailDraft = tour.inquiry_email_draft
  let emailSubject = ''
  let emailBody = ''
  if (emailDraft) {
    const doubleNewline = emailDraft.indexOf('\n\n')
    if (doubleNewline !== -1) {
      const firstLine = emailDraft.slice(0, doubleNewline)
      emailSubject = firstLine.startsWith('Subject: ') ? firstLine.slice(9) : firstLine
      emailBody = emailDraft.slice(doubleNewline + 2)
    } else {
      emailBody = emailDraft
    }
  }

  async function handleCopy() {
    if (!emailDraft) return
    try {
      await navigator.clipboard.writeText(emailDraft)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard API may fail in some contexts
    }
  }

  async function handleGenerate() {
    setEmailLoading(true)
    setEmailError(null)
    try {
      const result = await generateInquiryEmail(tour.id)
      // Refresh tour data to pick up saved draft
      const res = await getTour(tour.id)
      onTourUpdate(res.tour)
    } catch (err) {
      if (err instanceof ApiError) {
        setEmailError(err.message)
      } else {
        setEmailError('Failed to generate email. Please try again.')
      }
    } finally {
      setEmailLoading(false)
    }
  }

  if (!isPro) {
    return (
      <div className="py-8">
        <UpgradePrompt feature="AI-generated inquiry emails" />
      </div>
    )
  }

  if (emailDraft) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900">Inquiry Email Draft</h3>
        </div>
        <div className="bg-gray-50 rounded-lg p-4">
          {emailSubject && (
            <p className="font-medium text-gray-900">{emailSubject}</p>
          )}
          <div className={`text-gray-700 whitespace-pre-wrap text-sm leading-relaxed ${emailSubject ? 'mt-3' : ''}`}>
            {emailBody}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleCopy}
            className="flex items-center gap-1.5 bg-[var(--color-primary)] text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-[var(--color-primary-light)] transition-colors"
          >
            {copied ? (
              <>
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Copied!
              </>
            ) : (
              <>
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                Copy
              </>
            )}
          </button>
          <button
            type="button"
            onClick={handleGenerate}
            disabled={emailLoading}
            className="flex items-center gap-1.5 bg-gray-100 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {emailLoading ? (
              <>
                <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Regenerating...
              </>
            ) : (
              'Regenerate'
            )}
          </button>
        </div>
      </div>
    )
  }

  // No draft yet - show generate button
  return (
    <div className="flex flex-col items-center justify-center py-12">
      <svg className="h-12 w-12 text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
      <h3 className="text-sm font-semibold text-gray-900 mb-1">No email draft yet</h3>
      <p className="text-sm text-gray-500 mb-4 text-center">
        Generate a personalized inquiry email for this listing.
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
            Generating...
          </>
        ) : (
          'Generate Inquiry Email'
        )}
      </button>
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
