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
    contentInset: 'automatic',
  },
}

export default config
