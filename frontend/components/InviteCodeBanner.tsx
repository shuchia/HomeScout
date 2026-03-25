'use client'
import { useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { redeemInviteCode } from '@/lib/api'

export function InviteCodeBanner() {
  const { user, isPro, refreshProfile } = useAuth()
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)
  const [dismissed, setDismissed] = useState(false)

  if (!user || isPro || dismissed) return null

  async function handleRedeem(e: React.FormEvent) {
    e.preventDefault()
    if (!code.trim()) return

    setLoading(true)
    setMessage(null)

    try {
      const result = await redeemInviteCode(code.trim())
      setMessage({ text: result.message, type: 'success' })
      setCode('')
      await refreshProfile()
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to redeem code'
      setMessage({ text: errorMessage, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl p-4 mb-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-[var(--color-text)]">Have an invite code?</p>
          <p className="text-xs text-[var(--color-text-muted)]">Enter it below to unlock Pro features for 90 days.</p>
        </div>
        <form onSubmit={handleRedeem} className="flex items-center gap-2">
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="BETA-XXXXXX"
            className="w-36 px-3 py-1.5 text-sm border border-[var(--color-border)] rounded-lg focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !code.trim()}
            className="px-4 py-1.5 text-sm font-medium text-white bg-[var(--color-primary)] rounded-lg hover:bg-[var(--color-primary-light)] disabled:opacity-50 transition-colors"
          >
            {loading ? 'Redeeming...' : 'Redeem'}
          </button>
          <button
            type="button"
            onClick={() => setDismissed(true)}
            className="text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] p-1"
            aria-label="Dismiss"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </form>
      </div>
      {message && (
        <p className={`text-sm mt-2 ${message.type === 'success' ? 'text-emerald-600' : 'text-red-600'}`}>
          {message.text}
        </p>
      )}
    </div>
  )
}
