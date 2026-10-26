'use client'
import { useEffect, useRef } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { redeemInviteCode } from '@/lib/api'

// Invite codes unlock nothing now; redeeming one is how a sign-up gets
// credited to the channel that sent it. A visitor arriving on
// snugd.ai/?code=… has the code saved here, and it is redeemed the first
// time they are signed in — no copy and paste.
const KEY = 'snugd-pending-invite'

export function savePendingInvite(code: string) {
  try {
    localStorage.setItem(KEY, code.trim().toUpperCase())
  } catch {
    // Storage unavailable — the code can still be typed into the banner
  }
}

export function PendingInviteRedeemer() {
  const { user, refreshProfile } = useAuth()
  const attempted = useRef(false)

  useEffect(() => {
    if (!user || attempted.current) return
    let code: string | null = null
    try {
      code = localStorage.getItem(KEY)
    } catch {
      return
    }
    if (!code) return
    attempted.current = true

    redeemInviteCode(code)
      .then(() => refreshProfile())
      .catch(() => {
        // Invalid, used up, or already redeemed: nothing to retry.
      })
      .finally(() => {
        try {
          localStorage.removeItem(KEY)
        } catch {
          // Non-critical
        }
      })
  }, [user, refreshProfile])

  return null
}
