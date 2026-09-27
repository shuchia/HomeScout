'use client'
import { useEffect, useState, useCallback } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import {
  listSavedListings,
  createSavedListing,
  unfavoriteSavedListing,
  dismissListingChange,
} from '@/lib/api'
import { SavedListing } from '@/types/savedListing'

/**
 * Favourites, backed by `saved_listings`.
 *
 * This used to query the `favorites` table directly through the anon key and
 * then hydrate each row from /api/apartments/batch. It now goes through the
 * backend, for two reasons:
 *
 *  - A saved listing carries its own copy of the listing, so there is no
 *    second fetch and nothing to reconcile. The old version had to keep a map
 *    of previously-loaded apartments to paper over ids the batch call missed.
 *  - Saving queues a check of the listing against its source. Search reads a
 *    weekly-swept corpus, so a result can be days old; the check is what stops
 *    a stale rent becoming a true-cost figure the user acts on.
 *
 * The check is deliberately not awaited — it takes 10-20 seconds. The row is
 * created from the corpus copy, this returns immediately, and `refresh()`
 * picks up the corrected values plus any `last_change` marker.
 *
 * The public interface is unchanged from the previous version so callers such
 * as FavoriteButton did not need to move.
 */
export function useFavorites() {
  const { user, isPro, profileLoading } = useAuth()
  const [favorites, setFavorites] = useState<SavedListing[]>([])
  const [loading, setLoading] = useState(true)

  const loadFavorites = useCallback(async () => {
    if (!user) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const { saved_listings } = await listSavedListings({ favoritesOnly: true })
      setFavorites(saved_listings || [])
    } catch (error) {
      console.error('Failed to load favorites:', error)
      // Deliberately not clearing: a transient failure should not make the
      // user's favourites appear to vanish.
    }
    setLoading(false)
  }, [user])

  useEffect(() => {
    // Intentional: load on mount; loadFavorites sets state (react-hooks v6).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadFavorites()
  }, [user, loadFavorites])

  async function addFavorite(apartmentId: string): Promise<boolean> {
    if (!user) return false

    // Free tier cap. Skipped while the profile is still loading, so a slow
    // tier lookup cannot wrongly block a Pro user.
    if (!isPro && !profileLoading && favorites.length >= 5) {
      return false // Caller handles the UI feedback
    }

    try {
      const { saved_listing } = await createSavedListing({
        apartmentId,
        isFavorite: true,
      })
      setFavorites(prev =>
        prev.some(f => f.id === saved_listing.id)
          ? prev.map(f => (f.id === saved_listing.id ? saved_listing : f))
          : [saved_listing, ...prev],
      )
      return true
    } catch (error) {
      console.error('addFavorite failed:', error)
      return false
    }
  }

  async function removeFavorite(apartmentId: string): Promise<boolean> {
    if (!user) return false

    const target = favorites.find(f => f.apartment_id === apartmentId)
    if (!target) return false

    const previous = [...favorites]
    setFavorites(prev => prev.filter(f => f.id !== target.id))

    try {
      await unfavoriteSavedListing(target.id)
      return true
    } catch (error) {
      console.error('removeFavorite failed:', error)
      setFavorites(previous)
      return false
    }
  }

  /** Acknowledge the "changed since you saved this" marker on one listing. */
  async function dismissChange(savedListingId: string): Promise<void> {
    setFavorites(prev =>
      prev.map(f =>
        f.id === savedListingId ? { ...f, last_change: null, last_change_at: null } : f,
      ),
    )
    try {
      await dismissListingChange(savedListingId)
    } catch (error) {
      console.error('dismissChange failed:', error)
      await loadFavorites()
    }
  }

  function isFavorite(apartmentId: string): boolean {
    return favorites.some(f => f.apartment_id === apartmentId && f.is_favorite)
  }

  return {
    favorites,
    loading,
    addFavorite,
    removeFavorite,
    dismissChange,
    isFavorite,
    refresh: loadFavorites,
    atLimit: !isPro && !profileLoading && favorites.length >= 5,
  }
}
