'use client'
import { useState, useRef } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { submitFeedback } from '@/lib/api'

const TYPES = [
  { value: 'bug' as const, label: 'Bug' },
  { value: 'suggestion' as const, label: 'Idea' },
  { value: 'general' as const, label: 'General' },
]

export function FeedbackWidget() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [type, setType] = useState<'bug' | 'suggestion' | 'general'>('general')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState(false)
  const formRef = useRef<HTMLFormElement>(null)

  if (!user) return null

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!message.trim()) return

    setLoading(true)
    try {
      await submitFeedback({
        type,
        message: message.trim(),
        page_url: window.location.href,
      })
      setMessage('')
      setType('general')
      setOpen(false)
      setToast(true)
      setTimeout(() => setToast(false), 3000)
    } catch {
      // Silently fail for beta
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      {toast && (
        <div className="fixed bottom-20 right-6 z-[60] bg-emerald-600 text-white px-4 py-2 rounded-lg shadow-lg text-sm">
          Thanks for your feedback!
        </div>
      )}

      {open && (
        <div className="fixed bottom-20 right-6 z-[60] w-80 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl shadow-xl">
          <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
            <h3 className="font-semibold text-sm">Send Feedback</h3>
            <button onClick={() => setOpen(false)} className="text-[var(--color-text-muted)] hover:text-[var(--color-text)]">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <form ref={formRef} onSubmit={handleSubmit} className="p-4 space-y-3">
            <div className="flex gap-2">
              {TYPES.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => setType(t.value)}
                  className={`flex-1 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                    type === t.value
                      ? 'border-[var(--color-primary)] bg-[#2D6A4F10] text-[var(--color-primary)]'
                      : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-gray-400'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="What's on your mind?"
              rows={4}
              className="w-full px-3 py-2 text-sm border border-[var(--color-border)] rounded-lg focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent resize-none"
              required
            />

            <button
              type="submit"
              disabled={loading || !message.trim()}
              className="w-full py-2 text-sm font-medium text-white bg-[var(--color-primary)] rounded-lg hover:bg-[var(--color-primary-light)] disabled:opacity-50 transition-colors"
            >
              {loading ? 'Sending...' : 'Send Feedback'}
            </button>
          </form>
        </div>
      )}

      <button
        onClick={() => setOpen(!open)}
        className="fixed bottom-4 right-6 z-50 bg-[var(--color-primary)] text-white p-3 rounded-full shadow-lg hover:bg-[var(--color-primary-light)] transition-colors md:bottom-6"
        aria-label="Send feedback"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      </button>
    </>
  )
}
