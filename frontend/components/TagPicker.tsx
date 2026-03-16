'use client'

import { useState } from 'react'
import { TourTag } from '@/types/tour'

export interface TagSuggestion {
  tag: string
  sentiment: 'pro' | 'con'
  count: number
}

interface TagPickerProps {
  tags: TourTag[]
  suggestions: TagSuggestion[]
  onAdd: (tag: string, sentiment: 'pro' | 'con') => void
  onRemove: (tagId: string) => void
  loading?: boolean
}

export default function TagPicker({
  tags,
  suggestions,
  onAdd,
  onRemove,
  loading = false,
}: TagPickerProps) {
  const [showCustom, setShowCustom] = useState(false)
  const [customText, setCustomText] = useState('')

  const usedTags = new Set(tags.map((t) => t.tag.toLowerCase()))
  const availableSuggestions = suggestions.filter(
    (s) => !usedTags.has(s.tag.toLowerCase())
  )

  function handleAddCustom(sentiment: 'pro' | 'con') {
    const trimmed = customText.trim()
    if (!trimmed) return
    onAdd(trimmed, sentiment)
    setCustomText('')
    setShowCustom(false)
  }

  return (
    <div className="space-y-3">
      {/* Current tags */}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {tags.map((tag) => (
            <span
              key={tag.id}
              className={`
                inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium border
                ${
                  tag.sentiment === 'pro'
                    ? 'bg-green-100 text-green-800 border-green-200'
                    : 'bg-red-100 text-red-800 border-red-200'
                }
              `}
            >
              {tag.tag}
              <button
                type="button"
                onClick={() => onRemove(tag.id)}
                disabled={loading}
                className="ml-0.5 hover:opacity-70 min-w-[1.25rem] min-h-[1.25rem] flex items-center justify-center"
                aria-label={`Remove ${tag.tag}`}
              >
                &times;
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Divider between current and suggestions */}
      {tags.length > 0 && availableSuggestions.length > 0 && (
        <hr className="border-gray-200" />
      )}

      {/* Suggested tags */}
      {availableSuggestions.length > 0 && (
        <div>
          <p className="text-xs text-gray-500 mb-1.5">Suggestions</p>
          <div className="flex flex-wrap gap-2">
            {availableSuggestions.map((s) => (
              <button
                key={`${s.tag}-${s.sentiment}`}
                type="button"
                onClick={() => onAdd(s.tag, s.sentiment)}
                disabled={loading}
                className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm
                  border border-gray-300 text-gray-600 hover:bg-gray-50
                  transition-colors min-h-[2rem] disabled:opacity-50"
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    s.sentiment === 'pro' ? 'bg-green-400' : 'bg-red-400'
                  }`}
                />
                {s.tag}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Custom tag input */}
      {showCustom ? (
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={customText}
            onChange={(e) => setCustomText(e.target.value)}
            placeholder="Custom tag..."
            className="flex-1 border border-gray-300 rounded-md px-3 py-1.5 text-sm
              focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                setShowCustom(false)
                setCustomText('')
              }
            }}
            autoFocus
          />
          <button
            type="button"
            onClick={() => handleAddCustom('pro')}
            disabled={!customText.trim() || loading}
            className="px-3 py-1.5 text-sm font-medium rounded-md
              bg-green-100 text-green-700 hover:bg-green-200
              disabled:opacity-40 disabled:cursor-not-allowed
              min-h-[2rem] transition-colors"
          >
            Pro
          </button>
          <button
            type="button"
            onClick={() => handleAddCustom('con')}
            disabled={!customText.trim() || loading}
            className="px-3 py-1.5 text-sm font-medium rounded-md
              bg-red-100 text-red-700 hover:bg-red-200
              disabled:opacity-40 disabled:cursor-not-allowed
              min-h-[2rem] transition-colors"
          >
            Con
          </button>
          <button
            type="button"
            onClick={() => {
              setShowCustom(false)
              setCustomText('')
            }}
            className="text-gray-400 hover:text-gray-600 text-sm"
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setShowCustom(true)}
          className="text-sm text-blue-600 hover:text-blue-700 font-medium"
        >
          + Custom
        </button>
      )}
    </div>
  )
}
