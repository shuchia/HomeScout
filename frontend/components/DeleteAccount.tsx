'use client'
import { useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { deleteAccount } from '@/lib/api'

// In-app account deletion (App Store guideline 5.1.1(v)). Two steps, no
// browser confirm(): the second step spells out what goes, and nothing is
// deleted until "Delete permanently" is pressed.
export function DeleteAccount() {
  const { signOut } = useAuth()
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleDelete() {
    setDeleting(true)
    setError(null)
    try {
      await deleteAccount()
      // The server-side user is gone, so a normal sign-out's server call would
      // fail; clear the stored session locally and wait for it before leaving,
      // or the next page load finds a token for an account that doesn't exist.
      const { supabase } = await import('@/lib/supabase')
      await supabase.auth.signOut({ scope: 'local' }).catch(() => {})
      signOut()
      window.location.href = '/?account=deleted'
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong. Please try again.')
      setDeleting(false)
    }
  }

  if (!confirming) {
    return (
      <button onClick={() => setConfirming(true)} className="text-sm text-red-600 hover:underline">
        Delete my account
      </button>
    )
  }

  return (
    <div role="alertdialog" aria-labelledby="delete-account-title" className="space-y-3">
      <p id="delete-account-title" className="text-sm font-semibold text-red-700">Delete your Snugd account?</p>
      <p className="text-sm text-gray-700">
        This permanently deletes your account, favorites, tours, notes, voice recordings, photos and commute
        addresses. It can&apos;t be undone. Use Export my data above first if you want a copy.
      </p>
      {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
      <div className="flex gap-3">
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-medium hover:bg-red-700 disabled:opacity-60"
        >
          {deleting ? 'Deleting…' : 'Delete permanently'}
        </button>
        <button
          onClick={() => { setConfirming(false); setError(null) }}
          disabled={deleting}
          className="px-4 py-2 rounded-lg border text-sm"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
