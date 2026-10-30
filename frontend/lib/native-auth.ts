// OAuth inside the mobile apps.
//
// Google refuses sign-in from an embedded WebView (403 disallowed_useragent),
// and the app is one. So the provider page opens in the system browser sheet
// (SFSafariViewController / Chrome Custom Tabs), which Google allows, and
// comes back on snugd://auth/callback?code=…. The PKCE verifier was stored in
// this webview when the flow started, so the exchange happens here.
//
// Capacitor packages are imported lazily: they are only ever used in the app,
// and the website shouldn't load them.
import type { Provider } from '@supabase/supabase-js'
import { supabase } from '@/lib/supabase'
import { NATIVE_AUTH_CALLBACK } from '@/lib/native'

export async function nativeSignIn(provider: Provider) {
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider,
    options: { redirectTo: NATIVE_AUTH_CALLBACK, skipBrowserRedirect: true },
  })
  if (error || !data?.url) throw error ?? new Error('No sign-in URL')
  const { Browser } = await import('@capacitor/browser')
  await Browser.open({ url: data.url, presentationStyle: 'popover' })
}

/** Listen for the app being opened on the auth callback. Returns an unsubscribe. */
export function listenForNativeAuthCallback(onSignedIn: () => void, onError: (message: string) => void) {
  let removed = false
  let remove: (() => void) | null = null

  void (async () => {
    const [{ App }, { Browser }] = await Promise.all([import('@capacitor/app'), import('@capacitor/browser')])
    const handle = await App.addListener('appUrlOpen', async ({ url }) => {
      if (!url.startsWith(NATIVE_AUTH_CALLBACK)) return
      await Browser.close().catch(() => {}) // Android has already closed it
      const params = new URL(url).searchParams
      const code = params.get('code')
      if (!code) {
        onError(params.get('error_description') || 'Sign-in was cancelled.')
        return
      }
      const { error } = await supabase.auth.exchangeCodeForSession(code)
      if (error) onError(error.message)
      else onSignedIn()
    })
    if (removed) handle.remove()
    else remove = () => handle.remove()
  })()

  return () => {
    removed = true
    remove?.()
  }
}
