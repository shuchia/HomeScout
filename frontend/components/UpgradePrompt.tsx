'use client'
import Link from 'next/link'

interface UpgradePromptProps {
  feature: string
  inline?: boolean
  className?: string
}

export default function UpgradePrompt({ feature, inline = false, className = '' }: UpgradePromptProps) {
  if (inline) {
    return (
      <div className={`flex items-center gap-2 text-sm text-gray-500 ${className}`}>
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
        <span>Upgrade to Pro for {feature}</span>
        <Link href="/pricing" className="text-blue-600 hover:underline font-medium">
          Upgrade
        </Link>
      </div>
    )
  }

  return (
    <div className={`bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-6 text-center ${className}`}>
      <h3 className="text-lg font-semibold text-gray-900 mb-1">Pro Feature</h3>
      <p className="text-gray-600 mb-4">Upgrade to unlock {feature}</p>
      <Link
        href="/pricing"
        className="inline-block bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition-colors font-medium"
      >
        Upgrade to Pro - $12/mo
      </Link>
    </div>
  )
}
