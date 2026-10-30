import type { CapacitorConfig } from '@capacitor/cli'

// The app is a native shell around the live site: every web deploy reaches
// the app with no store review. CAP_SERVER_URL points it elsewhere for
// development, e.g. CAP_SERVER_URL=http://localhost:3000 npx cap sync ios.
// (qa.snugd.ai sits behind Vercel Authentication, so the app can't load it.)
const serverUrl = process.env.CAP_SERVER_URL || 'https://snugd.ai'

const config: CapacitorConfig = {
  appId: 'ai.snugd.app',
  appName: 'Snugd',
  // Shown only if the site can't be reached at launch.
  webDir: 'www',
  server: {
    url: serverUrl,
    cleartext: serverUrl.startsWith('http://'),
  },
  ios: {
    // The page handles the notch itself (viewport-fit=cover + --safe-top /
    // --safe-bottom in globals.css). 'automatic' inset the scroll content
    // but not fixed elements, so content scrolled up behind the status bar.
    contentInset: 'never',
  },
  plugins: {
    // The green launch screen stays up while the site loads, instead of a
    // blank white WebView. The page hides it once it has rendered
    // (frontend/components/NativeSplashHider.tsx); the duration is only the
    // fallback if that never happens.
    SplashScreen: {
      launchAutoHide: true,
      launchShowDuration: 8000,
      launchFadeOutDuration: 200,
      backgroundColor: '#2D6A4F',
      showSpinner: false,
    },
  },
}

export default config
