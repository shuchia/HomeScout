'use client'
import { Suspense, useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function SettingsContent() {
  const { user, profile, loading, isPro, tier, signOut, refreshProfile, accessToken } = useAuth()
  const searchParams = useSearchParams()

  useEffect(() => {
    if (searchParams.get('upgrade') === 'success') {
      refreshProfile()
    }
  }, [searchParams, refreshProfile])

  if (loading) return <div className="min-h-screen flex items-center justify-center">Loading...</div>
  if (!user) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-600">Please sign in to view settings.</p>
      </div>
    )
  }

  async function handleManageBilling() {
    if (!accessToken) return
    try {
      const res = await fetch(`${API_BASE}/api/billing/portal`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
      })
      if (!res.ok) return
      const { url } = await res.json()
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
    const [favs, searches] = await Promise.all([
      supabase.from('favorites').select('*').eq('user_id', user!.id),
      supabase.from('saved_searches').select('*').eq('user_id', user!.id),
    ])
    const blob = new Blob(
      [JSON.stringify({ favorites: favs.data, saved_searches: searches.data }, null, 2)],
      { type: 'application/json' }
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'homescout-data.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-12">
      <h1 className="text-2xl font-bold mb-8">Settings</h1>

      {searchParams.get('upgrade') === 'success' && (
        <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg mb-6">
          Welcome to Pro! You now have full access to all features.
        </div>
      )}

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

      {/* Subscription Section */}
      <section className="bg-white rounded-lg border p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">Subscription</h2>
        <div className="flex items-center justify-between">
          <div>
            <p className="font-medium capitalize">{tier} Plan</p>
            <p className="text-sm text-gray-500">
              {isPro ? 'Full access to all features' : 'Limited features'}
            </p>
          </div>
          {isPro ? (
            <button onClick={handleManageBilling} className="text-sm text-blue-600 hover:underline">
              Manage Billing
            </button>
          ) : (
            <a href="/pricing" className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700">
              Upgrade to Pro
            </a>
          )}
        </div>
      </section>

      {/* Data Section */}
      <section className="bg-white rounded-lg border p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">Your Data</h2>
        <button onClick={handleExportData} className="text-sm text-blue-600 hover:underline">
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
