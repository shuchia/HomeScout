'use client'

import { useEffect } from 'react'
import { isNativeApp } from '@/lib/native'

/**
 * In the mobile apps the native launch screen stays up while this site loads
 * (mobile/capacitor.config.ts). Hide it once the page has rendered. No-op on
 * the website.
 */
export function NativeSplashHider() {
  useEffect(() => {
    if (!isNativeApp()) return
    import('@capacitor/splash-screen')
      .then(({ SplashScreen }) => SplashScreen.hide())
      .catch(() => {}) // falls back to launchShowDuration
  }, [])
  return null
}
