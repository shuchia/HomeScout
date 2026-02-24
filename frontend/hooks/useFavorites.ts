'use client'
import { useEffect, useState, useCallback } from 'react'
import { supabase, Favorite } from '@/lib/supabase'
import { useAuth } from '@/contexts/AuthContext'
import { getApartmentsBatch } from '@/lib/api'
import { Apartment } from '@/types/apartment'

interface FavoriteWithApartment extends Favorite {
  apartment: Apartment | null
}

/**
 * Race a promise against a timeout. Returns null if the timeout fires first.
 */
function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T | null> {
  return Promise.race([
    promise,
    new Promise<null>((resolve) => setTimeout(() => resolve(null), ms)),
  ])
}

export function useFavorites() {
  const { user, isPro } = useAuth()
  const [favorites, setFavorites] = useState<FavoriteWithApartment[]>([])
  const [loading, setLoading] = useState(true)

  const loadFavorites = useCallback(async () => {
    if (!user) {
      setFavorites([])
      setLoading(false)
      return
    }

    setLoading(true)

    try {
      // Get favorites from Supabase (with timeout to prevent hanging)
      const query = supabase
        .from('favorites')
        .select('*')
        .eq('user_id', user.id)
        .order('created_at', { ascending: false })
      const result = await withTimeout(
        Promise.resolve(query),
        5000,
      )

      if (!result) {
        console.warn('Supabase favorites query timed out')
        setFavorites([])
        setLoading(false)
        return
      }

      const { data: favs, error: favsError } = result

      if (favsError) {
        console.error('Error loading favorites:', favsError)
        setLoading(false)
        return
      }

      if (!favs?.length) {
        setFavorites([])
        setLoading(false)
        return
      }

      // Fetch apartment details from FastAPI
      const apartmentIds = favs.map(f => f.apartment_id)
      try {
        const apartments = await getApartmentsBatch(apartmentIds)
        const apartmentMap = new Map(apartments.map(a => [a.id, a]))

        const merged = favs.map(fav => ({
          ...fav,
          apartment: apartmentMap.get(fav.apartment_id) || null
        }))

        setFavorites(merged)
      } catch (error) {
        console.error('Failed to fetch apartment details:', error)
        setFavorites(favs.map(fav => ({ ...fav, apartment: null })))
      }
    } catch (error) {
      console.error('Failed to load favorites:', error)
      setFavorites([])
    }

    setLoading(false)
  }, [user])

  useEffect(() => {
    loadFavorites()

    if (!user) return

    // Realtime subscription
    const subscription = supabase
      .channel('favorites-changes')
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'favorites',
          filter: `user_id=eq.${user.id}`
        },
        () => loadFavorites()
      )
      .subscribe()

    return () => {
      subscription.unsubscribe()
    }
  }, [user, loadFavorites])

  async function addFavorite(apartmentId: string): Promise<boolean> {
    if (!user) return false

    // Check free tier limit
    if (!isPro && favorites.length >= 5) {
      return false  // Caller handles the UI feedback
    }

    // Optimistic update - immediately show as favorited
    setFavorites(prev => [...prev, {
      id: `temp-${apartmentId}`,
      user_id: user.id,
      apartment_id: apartmentId,
      notes: null,
      is_available: true,
      created_at: new Date().toISOString(),
      apartment: null
    }])

    const { error } = await supabase.from('favorites').insert({
      user_id: user.id,
      apartment_id: apartmentId,
    })

    if (error) {
      console.error('Supabase addFavorite error:', error)
      // Rollback optimistic update on error
      setFavorites(prev => prev.filter(f => f.apartment_id !== apartmentId))
      return false
    }

    // Refresh to get full data including apartment details
    await loadFavorites()
    return true
  }

  async function removeFavorite(apartmentId: string): Promise<boolean> {
    if (!user) return false

    // Store for rollback
    const previousFavorites = [...favorites]

    // Optimistic update - immediately remove
    setFavorites(prev => prev.filter(f => f.apartment_id !== apartmentId))

    const { error } = await supabase
      .from('favorites')
      .delete()
      .eq('user_id', user.id)
      .eq('apartment_id', apartmentId)

    if (error) {
      console.error('Supabase removeFavorite error:', error)
      // Rollback on error
      setFavorites(previousFavorites)
      return false
    }

    return true
  }

  function isFavorite(apartmentId: string): boolean {
    return favorites.some(f => f.apartment_id === apartmentId)
  }

  return {
    favorites,
    loading,
    addFavorite,
    removeFavorite,
    isFavorite,
    refresh: loadFavorites,
    atLimit: !isPro && favorites.length >= 5,
  }
}
