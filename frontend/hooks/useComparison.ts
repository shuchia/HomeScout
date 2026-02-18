import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface ComparisonStore {
  apartmentIds: string[]
  addToCompare: (id: string) => void
  removeFromCompare: (id: string) => void
  clearComparison: () => void
  isInComparison: (id: string) => boolean
}

export const useComparison = create<ComparisonStore>()(
  persist(
    (set, get) => ({
      apartmentIds: [],

      addToCompare: (id) => {
        const current = get().apartmentIds
        if (current.length < 3 && !current.includes(id)) {
          set({ apartmentIds: [...current, id] })
        }
      },

      removeFromCompare: (id) => {
        set({ apartmentIds: get().apartmentIds.filter(i => i !== id) })
      },

      clearComparison: () => set({ apartmentIds: [] }),

      isInComparison: (id) => get().apartmentIds.includes(id),
    }),
    { name: 'homescout-comparison' }
  )
)
