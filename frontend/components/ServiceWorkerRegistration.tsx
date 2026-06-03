'use client'

import { useEffect } from 'react'

/**
 * Registers /sw.js on the client. Required for the browser to fire
 * `beforeinstallprompt` (the "Add to Home Screen" prompt on Chrome/Android).
 *
 * Kept side-effect-only — no UI. Runs once per page load. The service worker
 * itself is a pass-through, so this is safe to ship without offline support.
 */
export function ServiceWorkerRegistration() {
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!('serviceWorker' in navigator)) return
    // Defer registration so it doesn't compete with initial render work.
    const handle = window.setTimeout(() => {
      navigator.serviceWorker.register('/sw.js').catch((err) => {
        console.warn('Service worker registration failed:', err)
      })
    }, 1000)
    return () => window.clearTimeout(handle)
  }, [])

  return null
}
