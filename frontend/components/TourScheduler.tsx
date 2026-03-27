'use client'
import { useState } from 'react'
import { Tour } from '@/types/tour'
import { updateTour } from '@/lib/api'

interface TourSchedulerProps {
  tour: Tour
  onUpdate: (tour: Tour) => void
}

function formatDisplayDate(dateStr: string): string {
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

function formatDisplayTime(timeStr: string): string {
  const [h, m] = timeStr.split(':')
  const hour = parseInt(h, 10)
  const ampm = hour >= 12 ? 'PM' : 'AM'
  const display = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour
  return `${display}:${m} ${ampm}`
}

export function TourScheduler({ tour, onUpdate }: TourSchedulerProps) {
  const [editing, setEditing] = useState(false)
  const [date, setDate] = useState(tour.scheduled_date || '')
  const [time, setTime] = useState(tour.scheduled_time || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const hasSchedule = tour.scheduled_date

  async function handleSave() {
    if (!date) {
      setError('Please select a date')
      return
    }
    setSaving(true)
    setError('')
    try {
      const updates: Record<string, string> = {
        scheduled_date: date,
        stage: 'scheduled',
      }
      if (time) {
        updates.scheduled_time = time
      }
      const res = await updateTour(tour.id, updates as Parameters<typeof updateTour>[1])
      onUpdate(res.tour)
      setEditing(false)
    } catch {
      setError('Failed to save schedule')
    } finally {
      setSaving(false)
    }
  }

  async function handleClear() {
    setSaving(true)
    setError('')
    try {
      // Clear schedule by setting date/time to empty and reverting stage
      const res = await updateTour(tour.id, {
        scheduled_date: '',
        scheduled_time: '',
        stage: 'interested',
      } as Parameters<typeof updateTour>[1])
      onUpdate(res.tour)
      setDate('')
      setTime('')
      setEditing(false)
    } catch {
      setError('Failed to clear schedule')
    } finally {
      setSaving(false)
    }
  }

  // Display mode — show current schedule with edit button
  if (hasSchedule && !editing) {
    return (
      <div className="bg-purple-50 rounded-lg p-3">
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs font-medium text-purple-600 uppercase tracking-wide">Tour Scheduled</p>
          <button
            onClick={() => setEditing(true)}
            className="text-xs text-purple-600 hover:text-purple-800 underline"
          >
            Edit
          </button>
        </div>
        <p className="text-sm text-purple-800 font-medium">
          {formatDisplayDate(tour.scheduled_date!)}
          {tour.scheduled_time && (
            <span className="ml-1">at {formatDisplayTime(tour.scheduled_time)}</span>
          )}
        </p>
      </div>
    )
  }

  // No schedule yet — show prompt or form
  if (!hasSchedule && !editing) {
    return (
      <button
        onClick={() => setEditing(true)}
        className="w-full border-2 border-dashed border-purple-200 rounded-lg p-3 text-center hover:border-purple-400 hover:bg-purple-50 transition-colors"
      >
        <svg className="h-5 w-5 text-purple-400 mx-auto mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
        <span className="text-sm text-purple-600 font-medium">Schedule Tour</span>
      </button>
    )
  }

  // Edit mode — date/time picker form
  return (
    <div className="bg-purple-50 rounded-lg p-4 space-y-3">
      <p className="text-xs font-medium text-purple-600 uppercase tracking-wide">
        {hasSchedule ? 'Reschedule Tour' : 'Schedule Tour'}
      </p>

      <div className="flex gap-2">
        <div className="flex-1">
          <label htmlFor="tour-date" className="block text-xs text-gray-600 mb-1">Date</label>
          <input
            id="tour-date"
            type="date"
            value={date}
            onChange={(e) => { setDate(e.target.value); setError('') }}
            min={new Date().toISOString().split('T')[0]}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-purple-400 focus:border-transparent"
          />
        </div>
        <div className="flex-1">
          <label htmlFor="tour-time" className="block text-xs text-gray-600 mb-1">Time (optional)</label>
          <input
            id="tour-time"
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-purple-400 focus:border-transparent"
          />
        </div>
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex-1 px-3 py-2 bg-purple-600 text-white text-sm font-medium rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors"
        >
          {saving ? 'Saving...' : hasSchedule ? 'Update Schedule' : 'Schedule'}
        </button>
        {hasSchedule && (
          <button
            onClick={handleClear}
            disabled={saving}
            className="px-3 py-2 border border-gray-300 text-gray-600 text-sm rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            Clear
          </button>
        )}
        <button
          onClick={() => { setEditing(false); setDate(tour.scheduled_date || ''); setTime(tour.scheduled_time || '') }}
          disabled={saving}
          className="px-3 py-2 text-gray-500 text-sm hover:text-gray-700 disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
