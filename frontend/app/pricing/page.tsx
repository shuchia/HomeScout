'use client'
import { useAuth } from '@/contexts/AuthContext'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function PricingPage() {
  const { user, isPro, loading } = useAuth()

  async function handleUpgrade() {
    const { data: { session } } = await (await import('@/lib/supabase')).supabase.auth.getSession()
    const res = await fetch(`${API_BASE}/api/billing/checkout`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}),
      },
    })
    const { url } = await res.json()
    if (url) window.location.href = url
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto px-4 py-16">
        <h1 className="text-3xl font-bold text-center mb-2">Choose Your Plan</h1>
        <p className="text-gray-600 text-center mb-12">Unlock AI-powered apartment matching</p>

        <div className="grid md:grid-cols-2 gap-8">
          {/* Free Plan */}
          <div className="bg-white rounded-xl border border-gray-200 p-8">
            <h2 className="text-xl font-semibold mb-1">Free</h2>
            <p className="text-3xl font-bold mb-6">$0<span className="text-base font-normal text-gray-500">/mo</span></p>
            <ul className="space-y-3 text-sm text-gray-600 mb-8">
              <li>3 searches per day</li>
              <li>Side-by-side comparison</li>
              <li>5 favorites</li>
              <li className="text-gray-400 line-through">AI match scoring</li>
              <li className="text-gray-400 line-through">AI comparison analysis</li>
              <li className="text-gray-400 line-through">Saved searches and alerts</li>
            </ul>
            {!user && (
              <p className="text-sm text-gray-500 text-center">Sign in to get started</p>
            )}
          </div>

          {/* Pro Plan */}
          <div className="bg-white rounded-xl border-2 border-blue-600 p-8 relative">
            <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-blue-600 text-white text-xs px-3 py-1 rounded-full">
              Recommended
            </span>
            <h2 className="text-xl font-semibold mb-1">Pro</h2>
            <p className="text-3xl font-bold mb-6">$12<span className="text-base font-normal text-gray-500">/mo</span></p>
            <ul className="space-y-3 text-sm text-gray-700 mb-8">
              <li>Unlimited searches</li>
              <li>AI match scoring (0-100)</li>
              <li>AI comparison analysis with winner picks</li>
              <li>Unlimited favorites</li>
              <li>Saved searches</li>
              <li>Daily email alerts for new matches</li>
            </ul>
            {isPro ? (
              <p className="text-center text-green-600 font-medium">Your current plan</p>
            ) : (
              <button
                onClick={handleUpgrade}
                disabled={!user || loading}
                className="w-full bg-blue-600 text-white py-3 rounded-lg hover:bg-blue-700 transition-colors font-medium disabled:opacity-50"
              >
                {user ? 'Upgrade to Pro' : 'Sign in to upgrade'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
