'use client'

interface RadiusSliderProps {
  value: number
  onChange: (value: number) => void
}

export default function RadiusSlider({ value, onChange }: RadiusSliderProps) {
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
      <input
        type="range"
        min={0.5}
        max={10}
        step={0.5}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-[var(--color-primary)]"
      />
    </div>
  )
}
