'use client'

import { useEffect, useState } from 'react'

/**
 * "Install Snugd" prompt — surfaces the native PWA install dialog on Chrome
 * (desktop + Android) when the browser fires `beforeinstallprompt`. iOS Safari
 * doesn't fire this event and has no programmatic install API, so we render
 * a static "Add to Home Screen" hint on iOS instead.
 *
 * Dismissals are remembered in localStorage so we don't nag users who said no.
 */

// Chrome's BeforeInstallPromptEvent isn't in the standard DOM types yet.
interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

const DISMISS_KEY = 'snugd-install-prompt-dismissed-at'
const DISMISS_TTL_MS = 1000 * 60 * 60 * 24 * 30 // 30 days

function isIos(): boolean {
  if (typeof navigator === 'undefined') return false
  const ua = navigator.userAgent
  // Detect iPhone/iPad (incl. iPadOS reporting as Mac with touch).
  return /iPad|iPhone|iPod/.test(ua) ||
    (ua.includes('Macintosh') && 'ontouchend' in document)
}

function isStandalone(): boolean {
  if (typeof window === 'undefined') return false
  // Both the modern (display-mode) and legacy (iOS Safari) checks.
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    // @ts-expect-error legacy iOS Safari standalone flag
    window.navigator.standalone === true
  )
}

function recentlyDismissed(): boolean {
  if (typeof window === 'undefined') return true
  const raw = window.localStorage.getItem(DISMISS_KEY)
  if (!raw) return false
  const ts = Number(raw)
  return Number.isFinite(ts) && Date.now() - ts < DISMISS_TTL_MS
}

export function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null)
  const [showIosHint, setShowIosHint] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    if (isStandalone() || recentlyDismissed()) {
      setDismissed(true)
      return
    }

    // Chrome / Android: capture the install prompt for later.
    const handler = (e: Event) => {
      e.preventDefault()
      setDeferredPrompt(e as BeforeInstallPromptEvent)
    }
    window.addEventListener('beforeinstallprompt', handler)

    // iOS Safari: show static hint after a short delay.
    if (isIos()) {
      const t = window.setTimeout(() => setShowIosHint(true), 4000)
      return () => {
        window.removeEventListener('beforeinstallprompt', handler)
        window.clearTimeout(t)
      }
    }

    return () => window.removeEventListener('beforeinstallprompt', handler)
  }, [])

  const handleDismiss = () => {
    setDismissed(true)
    try {
      window.localStorage.setItem(DISMISS_KEY, String(Date.now()))
    } catch {
      // localStorage unavailable — just hide for this session
    }
  }

  const handleInstall = async () => {
    if (!deferredPrompt) return
    await deferredPrompt.prompt()
    const { outcome } = await deferredPrompt.userChoice
    setDeferredPrompt(null)
    if (outcome === 'accepted') {
      setDismissed(true)
    } else {
      handleDismiss()
    }
  }

  if (dismissed) return null
  if (!deferredPrompt && !showIosHint) return null

  return (
    <div className="fixed bottom-20 left-3 right-3 md:bottom-6 md:left-auto md:right-6 md:w-80 z-40 bg-white border border-[var(--color-border)] rounded-2xl shadow-xl p-4">
      <div className="flex items-start gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/icons/icon-192.png"
          alt=""
          aria-hidden="true"
          className="w-10 h-10 rounded-lg flex-shrink-0"
        />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-[var(--color-text)]">Install Snugd</p>
          {deferredPrompt ? (
            <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
              Add to your home screen for one-tap access during apartment tours.
            </p>
          ) : (
            <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
              Tap the Share icon, then <span className="font-medium">Add to Home Screen</span>.
            </p>
          )}
          <div className="flex gap-2 mt-3">
            {deferredPrompt && (
              <button
                type="button"
                onClick={handleInstall}
                className="text-xs font-medium px-3 py-1.5 rounded-lg bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-light)] transition"
              >
                Install
              </button>
            )}
            <button
              type="button"
              onClick={handleDismiss}
              className="text-xs font-medium px-3 py-1.5 rounded-lg text-[var(--color-text-secondary)] hover:bg-gray-100 transition"
            >
              Not now
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
