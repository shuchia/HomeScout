'use client'
import { Suspense } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { createBillingPortalSession } from '@/lib/api'
import CommuteAddresses from '@/components/CommuteAddresses'
import { AiConsentSetting } from '@/components/AiConsent'

function SettingsContent() {
  const { user, profile, loading, profileLoading, signOut } = useAuth()
  // No paid tier any more; billing stays reachable only so anyone still
  // holding a Stripe subscription can cancel it.
  const hasSubscription = !!profile?.subscription_status && profile.subscription_status !== 'canceled'

  if (loading) return <div className="min-h-screen flex items-center justify-center">Loading...</div>
  if (!user) {
    return (
      <div className="min-h-screen bg-[var(--color-bg)] flex items-center justify-center">
        <p className="text-gray-600">Please sign in to view settings.</p>
      </div>
    )
  }

  async function handleManageBilling() {
    try {
      const { url } = await createBillingPortalSession()
      if (url) window.location.href = url
    } catch (err) {
      console.error('Manage billing failed:', err)
    }
  }

  async function handleDeleteAccount() {
    if (!confirm('This will permanently delete your account, favorites, and saved searches. This cannot be undone.')) return
    signOut()
    window.location.href = '/'
  }

  async function handleExportData() {
    const { supabase } = await import('@/lib/supabase')
    const { listSavedListings } = await import('@/lib/api')

    // Saved listings come through the API rather than a direct table read:
    // `favorites` is being retired (migration 012) and a saved listing carries
    // its own copy of the listing, so the export is now self-contained instead
    // of a list of apartment ids that mean nothing outside our database.
    const [saved, searches] = await Promise.all([
      listSavedListings().catch(() => ({ saved_listings: [] })),
      supabase.from('saved_searches').select('*').eq('user_id', user!.id),
    ])
    const blob = new Blob(
      [JSON.stringify(
        { saved_listings: saved.saved_listings, saved_searches: searches.data },
        null,
        2,
      )],
      { type: 'application/json' }
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'snugd-data.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-12">
      <h1 className="text-2xl font-bold mb-8">Settings</h1>

      {/* Profile Section */}
      <section className="bg-white rounded-lg border p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">Profile</h2>
        <div className="flex items-center gap-4">
          {profile?.avatar_url && (
            <img src={profile.avatar_url} alt="" className="w-12 h-12 rounded-full" />
          )}
          <div>
            <p className="font-medium">{profile?.name || 'No name'}</p>
            <p className="text-sm text-gray-500">{profile?.email}</p>
          </div>
        </div>
      </section>

      {/* AI Section */}
      <section className="bg-white rounded-lg border p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">AI</h2>
        {profileLoading ? (
          <div className="h-9 bg-gray-100 rounded-lg animate-pulse" />
        ) : (
          <AiConsentSetting />
        )}
        {hasSubscription && (
          <button onClick={handleManageBilling} className="mt-4 text-sm text-[var(--color-primary)] hover:underline">
            Manage billing
          </button>
        )}
      </section>

      {/* Commute Addresses */}
      <CommuteAddresses />

      {/* Data Section */}
      <section className="bg-white rounded-lg border p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">Your Data</h2>
        <button onClick={handleExportData} className="text-sm text-[var(--color-primary)] hover:underline">
          Export my data (JSON)
        </button>
      </section>

      {/* Danger Zone */}
      <section className="bg-white rounded-lg border border-red-200 p-6">
        <h2 className="text-lg font-semibold text-red-600 mb-4">Danger Zone</h2>
        <button onClick={handleDeleteAccount} className="text-sm text-red-600 hover:underline">
          Delete my account
        </button>
      </section>
    </div>
  )
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading...</div>}>
      <SettingsContent />
    </Suspense>
  )
}
