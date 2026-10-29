// The iOS and Android apps (mobile/) are a Capacitor shell that loads this
// same site. Capacitor injects `window.Capacitor` before any page script runs,
// so this is reliable at module load. On the server and in a normal browser it
// is false.

/** Where the OAuth provider sends the user back to inside the app. Registered
 * as a URL scheme in mobile/ios and mobile/android, and must be in Supabase's
 * Auth → Redirect URLs. */
export const NATIVE_AUTH_CALLBACK = 'snugd://auth/callback'

export function isNativeApp(): boolean {
  if (typeof window === 'undefined') return false
  const cap = (window as unknown as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor
  return !!cap?.isNativePlatform?.()
}
