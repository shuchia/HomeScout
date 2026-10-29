# Snugd mobile apps (Capacitor)

The iOS and Android apps are a native shell around the live site: the WebView
loads `https://snugd.ai`, so every web deploy reaches the apps without a store
review. Native code here is only what the web can't do.

| | |
|---|---|
| App id | `ai.snugd.app` |
| Loads | `https://snugd.ai` (override: `CAP_SERVER_URL`) |
| Offline fallback | `www/index.html` |
| iOS deps | Swift Package Manager (no CocoaPods) |

## Sign-in

Google refuses OAuth inside an embedded WebView (`disallowed_useragent`), so
in the app `signInWithGoogle` opens the provider in the system browser sheet
(`@capacitor/browser`) and Supabase redirects back to
**`snugd://auth/callback`**, which both platforms register as a URL scheme.
The app uses PKCE there (the website keeps the implicit flow), so the code in
that URL is useless to any other app claiming the scheme. See
`frontend/lib/native-auth.ts`.

`snugd://auth/callback` must be in each Supabase project's
**Auth → URL Configuration → Redirect URLs**.

## Run

```bash
cd mobile && npm install

# Against a local frontend (npm run dev in frontend/)
CAP_SERVER_URL=http://localhost:3000 npx cap sync ios
npx cap run ios            # or: npx cap open ios, then Run in Xcode

# Against prod
npx cap sync ios && npx cap open ios
```

`cap sync` bakes `server.url` into the native projects, so **re-run it without
`CAP_SERVER_URL` before any release build**. qa.snugd.ai sits behind Vercel
Authentication and can't be loaded by the app.

Android needs Android Studio (bundles the JDK and SDK): `npx cap open android`.

## Permissions

- iOS `Info.plist`: microphone (voice notes), camera and photo library (tour
  photos), `snugd` URL scheme.
- Android manifest: `RECORD_AUDIO`, `CAMERA`, `snugd://auth` intent filter.

The web code detects the app with `isNativeApp()` (`frontend/lib/native.ts`)
— used to hide the PWA install prompt and skip the service worker.
