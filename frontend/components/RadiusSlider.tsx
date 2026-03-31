'use client'

import Link from 'next/link'

interface RadiusSliderProps {
  value: number
  onChange: (value: number) => void
  isPro: boolean
}

export default function RadiusSlider({ value, onChange, isPro }: RadiusSliderProps) {
  return (
    <div className="relative">
      <div className="flex items-center justify-between mb-1">
        <label className="text-sm font-medium text-gray-700">
          Max Distance
        </label>
        <span className="text-sm text-gray-500">
          Within {value} mi
        </span>
      </div>
      <div className="relative">
        <input
          type="range"
          min={0.5}
          max={10}
          step={0.5}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          disabled={!isPro}
          className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-[var(--color-primary)] disabled:opacity-50 disabled:cursor-not-allowed"
        />
        {!isPro && (
          <Link
            href="/pricing"
            className="absolute -top-1 right-0 inline-flex items-center gap-1 bg-amber-100 text-amber-700 text-xs font-medium px-2 py-0.5 rounded-full hover:bg-amber-200 transition-colors"
          >
            Pro
          </Link>
        )}
      </div>
    </div>
  )
}
