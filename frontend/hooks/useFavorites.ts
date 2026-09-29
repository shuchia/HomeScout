'use client'
import { useEffect } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { useFavoritesStore } from '@/hooks/useFavoritesStore'

/**
 * Favourites, backed by `saved_listings`.
 *
 * State lives in a shared store rather than in this hook. `FavoriteButton`
 * renders once per `ApartmentCard`, so a page of results mounts a dozen of
 * these — when each owned its own state and loading effect, every card fetched
 * the whole favourites list independently. See useFavoritesStore.
 *
 * Saving a listing queues a check of it against its source: search reads a
 * weekly-swept corpus, so a result can be days old, and the check is what
 * stops a stale rent becoming a true-cost figure the user acts on. It is
 * deliberately not awaited — the row is created from the corpus copy and the
 * corrected values arrive on the next load.
 *
 * The public interface is unchanged from the per-hook version, so callers did
 * not have to move.
 */
export function useFavorites() {
  const { user, isPro, profileLoading } = useAuth()

  const favorites = useFavoritesStore(s => s.favorites)
  const loading = useFavoritesStore(s => s.loading)
  const load = useFavoritesStore(s => s.load)
  const add = useFavoritesStore(s => s.add)
  const remove = useFavoritesStore(s => s.remove)
  const dismissChange = useFavoritesStore(s => s.dismissChange)
  const reset = useFavoritesStore(s => s.reset)

  useEffect(() => {
    if (!user) {
      reset()
      return
    }
    // Every mounted FavoriteButton runs this. The store coalesces them onto a
    // single request and skips entirely once the list is loaded.
    void load(user.id)
  }, [user, load, reset])

  async function addFavorite(apartmentId: string): Promise<boolean> {
    if (!user) return false

    // Free tier cap. Skipped while the profile is still loading, so a slow
    // tier lookup cannot wrongly block a Pro user.
    if (!isPro && !profileLoading && favorites.length >= 5) {
      return false // Caller handles the UI feedback
    }

    return add(user.id, apartmentId)
  }

  async function removeFavorite(apartmentId: string): Promise<boolean> {
    if (!user) return false
    return remove(apartmentId)
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
    refresh: () => (user ? load(user.id, { force: true }) : Promise.resolve()),
    atLimit: !isPro && !profileLoading && favorites.length >= 5,
  }
}
