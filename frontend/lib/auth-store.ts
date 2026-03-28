/**
 * Module-level auth token store.
 *
 * AuthContext writes to this whenever the Supabase session changes
 * (sign-in, sign-out, token refresh). Non-React code like lib/api.ts
 * reads from it synchronously — no async getSession() calls needed.
 *
 * Also provides proactive token refresh: before every authenticated
 * API call, the token is checked for expiry and refreshed if needed.
 */

import { supabase } from './supabase'

let _accessToken: string | null = null
let _expiresAt: number = 0 // Unix timestamp in seconds

export function setAccessToken(token: string | null, expiresAt?: number) {
  _accessToken = token
  _expiresAt = expiresAt ?? 0
}

export function getAccessToken(): string | null {
  return _accessToken
}

/** True if the token is missing or will expire within the next 60 seconds */
export function isTokenExpiringSoon(): boolean {
  if (!_accessToken || !_expiresAt) return true
  return Date.now() / 1000 > _expiresAt - 60
}

// Prevent concurrent refresh calls
let _refreshPromise: Promise<string | null> | null = null

/**
 * Refresh the token from Supabase and update the store.
 * Uses refreshSession() (network call) not getSession() (memory-only).
 * De-duplicated: concurrent calls share the same promise.
 *
 * Returns the new token on success, or NULL on failure.
 * On failure, clears the stale token so callers know auth is dead.
 */
export async function refreshAccessToken(): Promise<string | null> {
  if (_refreshPromise) return _refreshPromise

  _refreshPromise = (async () => {
    try {
      const { data: { session }, error } = await supabase.auth.refreshSession()
      if (session && !error) {
        _accessToken = session.access_token
        _expiresAt = session.expires_at ?? 0
        return session.access_token
      }
      // Refresh returned no session — refresh token is invalid/expired.
      // Clear the stale token so fetchWithAuth knows auth is dead.
      _accessToken = null
      _expiresAt = 0
      return null
    } catch {
      // Network error during refresh — clear stale token
      _accessToken = null
      _expiresAt = 0
      return null
    }
  })()

  try {
    return await _refreshPromise
  } finally {
    _refreshPromise = null
  }
}
