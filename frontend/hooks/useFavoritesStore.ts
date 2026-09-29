import { create } from 'zustand'
import { SavedListing } from '@/types/savedListing'
import {
  listSavedListings,
  createSavedListing,
  unfavoriteSavedListing,
  dismissListingChange,
} from '@/lib/api'

/**
 * Shared favourites state.
 *
 * This is a store rather than per-hook state because `FavoriteButton` renders
 * once per `ApartmentCard`, so a page of results mounts a dozen of them. When
 * each instance owned its own state and its own loading effect, every card
 * independently fetched the whole favourites list — QA logs showed up to
 * eleven identical `GET /api/saved-listings` in a single second, which both
 * burned the rate limit and turned one expired token into eleven visible
 * failures.
 *
 * The fan-out predates the move to `/api/saved-listings` (the Supabase version
 * did the same), but it only started costing anything once the traffic landed
 * on our own API.
 *
 * `inFlight` is the part that actually fixes it: concurrent callers share one
 * promise instead of each starting a request.
 */
interface FavoritesStore {
  favorites: SavedListing[]
  loading: boolean
  /** Which user the current list belongs to; null when nothing is loaded. */
  loadedForUser: string | null
  /** In-progress fetch, so simultaneous callers coalesce onto one request. */
  inFlight: Promise<void> | null

  load: (userId: string, opts?: { force?: boolean }) => Promise<void>
  add: (userId: string, apartmentId: string) => Promise<boolean>
  remove: (apartmentId: string) => Promise<boolean>
  dismissChange: (savedListingId: string) => Promise<void>
  reset: () => void
}

export const useFavoritesStore = create<FavoritesStore>((set, get) => ({
  favorites: [],
  loading: true,
  loadedForUser: null,
  inFlight: null,

  load: async (userId, opts) => {
    const state = get()

    // Already have this user's list and nobody asked for a refresh.
    if (!opts?.force && state.loadedForUser === userId && !state.loading) {
      return
    }
    // Someone else is already fetching it — wait on theirs.
    if (state.inFlight) {
      return state.inFlight
    }

    const request = (async () => {
      set({ loading: true })
      try {
        const { saved_listings } = await listSavedListings({ favoritesOnly: true })
        set({ favorites: saved_listings || [], loadedForUser: userId })
      } catch (error) {
        // Deliberately not clearing: a transient failure should not make the
        // user's favourites appear to vanish.
        console.error('Failed to load favorites:', error)
      } finally {
        set({ loading: false, inFlight: null })
      }
    })()

    set({ inFlight: request })
    return request
  },

  add: async (userId, apartmentId) => {
    try {
      const { saved_listing } = await createSavedListing({
        apartmentId,
        isFavorite: true,
      })
      set(state => ({
        favorites: state.favorites.some(f => f.id === saved_listing.id)
          ? state.favorites.map(f => (f.id === saved_listing.id ? saved_listing : f))
          : [saved_listing, ...state.favorites],
        loadedForUser: userId,
      }))
      return true
    } catch (error) {
      console.error('addFavorite failed:', error)
      return false
    }
  },

  remove: async (apartmentId) => {
    const target = get().favorites.find(f => f.apartment_id === apartmentId)
    if (!target) return false

    const previous = get().favorites
    set({ favorites: previous.filter(f => f.id !== target.id) })

    try {
      await unfavoriteSavedListing(target.id)
      return true
    } catch (error) {
      console.error('removeFavorite failed:', error)
      set({ favorites: previous })
      return false
    }
  },

  dismissChange: async (savedListingId) => {
    set(state => ({
      favorites: state.favorites.map(f =>
        f.id === savedListingId ? { ...f, last_change: null, last_change_at: null } : f,
      ),
    }))
    try {
      await dismissListingChange(savedListingId)
    } catch (error) {
      console.error('dismissChange failed:', error)
    }
  },

  reset: () => set({ favorites: [], loading: false, loadedForUser: null, inFlight: null }),
}))
