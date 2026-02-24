/**
 * Module-level auth token store.
 *
 * AuthContext writes to this whenever the Supabase session changes
 * (sign-in, sign-out, token refresh). Non-React code like lib/api.ts
 * reads from it synchronously — no async getSession() calls needed.
 */

let _accessToken: string | null = null

export function setAccessToken(token: string | null) {
  _accessToken = token
}

export function getAccessToken(): string | null {
  return _accessToken
}
