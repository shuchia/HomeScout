'use client'
import { useEffect, useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'

// AI is free for every signed-in user, but the user's data only goes to the
// AI providers once they agree (the app stores require that permission be
// asked for first). The backend enforces it against profiles.ai_consent_at;
// these components are how a user gives or withdraws it.

const DECLINED_KEY = 'snugd-ai-consent-declined'

function AiDisclosure() {
  return (
    <div className="space-y-2 text-sm text-[var(--color-text-secondary)]">
      <p>
        Snugd uses AI to score listings against what you&apos;re looking for, compare
        apartments, draft messages to landlords, plan tour days, and tidy up your tour notes.
      </p>
      <p>
        To do that, we send what each feature needs — your search preferences, the listings
        involved, and your tour notes — to <strong>Anthropic</strong> (Claude). Voice notes are
        transcribed by <strong>OpenAI</strong>.
      </p>
      <p>You can turn this off any time in Settings.</p>
    </div>
  )
}

export function AiConsentDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { setAiConsent } = useAuth()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!open) return null

  async function agree() {
    setSaving(true)
    setError(null)
    try {
      await setAiConsent(true)
      onClose()
    } catch {
      setError('Could not save that. Try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" role="dialog" aria-modal="true" aria-labelledby="ai-consent-title">
      <div className="w-full max-w-md rounded-2xl bg-[var(--color-surface)] p-6 shadow-xl">
        <h2 id="ai-consent-title" className="text-lg font-semibold text-[var(--color-text)] mb-3">
          Turn on AI features?
        </h2>
        <AiDisclosure />
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)]"
          >
            Not now
          </button>
          <button
            onClick={agree}
            disabled={saving}
            className="px-4 py-2 text-sm font-medium text-white bg-[var(--color-primary)] rounded-lg hover:bg-[var(--color-primary-light)] disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Agree and turn on'}
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * Asks once, after onboarding, for signed-in users who have not decided.
 * "Not now" is remembered on this device so it doesn't nag on every visit;
 * the inline prompts and Settings still offer it.
 */
export function AiConsentOnboarding() {
  const { user, profile, profileLoading } = useAuth()
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!user || profileLoading || !profile) return
    if (!profile.has_completed_onboarding || profile.ai_consent_at) return
    let declined = false
    try {
      declined = localStorage.getItem(DECLINED_KEY) === '1'
    } catch {
      // Storage unavailable — ask, and forget the answer
    }
    // Intentional: open once profile state settles (react-hooks v6).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (!declined) setOpen(true)
  }, [user, profile, profileLoading])

  function close() {
    setOpen(false)
    try {
      localStorage.setItem(DECLINED_KEY, '1')
    } catch {
      // Non-critical
    }
  }

  return <AiConsentDialog open={open} onClose={close} />
}

/**
 * Stands in where an AI feature would render for someone who can't use it
 * yet: sign in if anonymous, otherwise turn AI on.
 */
export default function AiConsentPrompt({
  feature,
  inline = false,
  className = '',
}: {
  feature: string
  inline?: boolean
  className?: string
}) {
  const { user, signInWithGoogle } = useAuth()
  const [open, setOpen] = useState(false)

  const action = user ? () => setOpen(true) : signInWithGoogle
  const label = user ? 'Turn on AI' : 'Sign in'
  const message = user ? `${feature} uses AI.` : `Sign in to use ${feature.toLowerCase()}.`

  return (
    <>
      {inline ? (
        <div className={`flex items-center gap-2 text-sm text-[var(--color-text-muted)] ${className}`}>
          <span>{message}</span>
          <button onClick={action} className="text-[var(--color-primary)] hover:underline font-medium">
            {label}
          </button>
        </div>
      ) : (
        <div className={`bg-emerald-50 border border-emerald-200 rounded-lg p-6 text-center ${className}`}>
          <p className="text-[var(--color-text-secondary)] mb-4">{message}</p>
          <button
            onClick={action}
            className="inline-block bg-[var(--color-primary)] text-white px-6 py-2 rounded-lg hover:bg-[var(--color-primary-light)] transition-colors font-medium"
          >
            {label}
          </button>
        </div>
      )}
      <AiConsentDialog open={open} onClose={() => setOpen(false)} />
    </>
  )
}

/** Settings toggle: shows the disclosure and lets the user withdraw. */
export function AiConsentSetting() {
  const { aiEnabled, setAiConsent } = useAuth()
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)

  async function turnOff() {
    setSaving(true)
    try {
      await setAiConsent(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="font-medium text-[var(--color-text)]">AI features</p>
          <p className="text-sm text-[var(--color-text-muted)]">{aiEnabled ? 'On' : 'Off'}</p>
        </div>
        {aiEnabled ? (
          <button
            onClick={turnOff}
            disabled={saving}
            className="text-sm text-[var(--color-text-secondary)] border border-[var(--color-border)] px-4 py-2 rounded-lg hover:bg-[var(--color-bg)] disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Turn off'}
          </button>
        ) : (
          <button
            onClick={() => setOpen(true)}
            className="bg-[var(--color-primary)] text-white px-4 py-2 rounded-lg text-sm hover:bg-[var(--color-primary-light)]"
          >
            Turn on
          </button>
        )}
      </div>
      <div className="mt-3">
        <AiDisclosure />
      </div>
      <AiConsentDialog open={open} onClose={() => setOpen(false)} />
    </div>
  )
}
