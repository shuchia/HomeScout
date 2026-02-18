import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

interface SearchContext {
  city: string
  budget: number
  bedrooms: number
  bathrooms: number
  property_type: string
  move_in_date: string
  other_preferences: string
}

interface ComparisonStore {
  apartmentIds: string[]
  searchContext: SearchContext | null
  addToCompare: (id: string) => void
  removeFromCompare: (id: string) => void
  clearComparison: () => void
  isInComparison: (id: string) => boolean
  setSearchContext: (ctx: SearchContext) => void
}

const useComparisonStore = create(
  persist<ComparisonStore>(
    (set, get) => ({
      apartmentIds: [],
      searchContext: null,

      addToCompare: (id) => {
        const current = get().apartmentIds
        if (current.length < 3 && !current.includes(id)) {
          set({ apartmentIds: [...current, id] })
        }
      },

      removeFromCompare: (id) => {
        set({ apartmentIds: get().apartmentIds.filter(i => i !== id) })
      },

      clearComparison: () => set({ apartmentIds: [], searchContext: null }),

      isInComparison: (id) => get().apartmentIds.includes(id),

      setSearchContext: (ctx) => set({ searchContext: ctx }),
    }),
    {
      name: 'homescout-comparison',
      storage: createJSONStorage(() => localStorage),
    }
  )
)

export { useComparisonStore as useComparison }
