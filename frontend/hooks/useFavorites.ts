'use client'
import { useEffect, useState, useCallback } from 'react'
import { supabase, Favorite } from '@/lib/supabase'
import { useAuth } from '@/contexts/AuthContext'
import { getApartmentsBatch } from '@/lib/api'
import { Apartment } from '@/types/apartment'

interface FavoriteWithApartment extends Favorite {
  apartment: Apartment | null
}

export function useFavorites() {
  const { user, isPro, profileLoading } = useAuth()
  const [favorites, setFavorites] = useState<FavoriteWithApartment[]>([])
  const [loading, setLoading] = useState(true)

  const loadFavorites = useCallback(async () => {
    if (!user) {
      // Don't clear favorites if we already have data — could be a token refresh
      setLoading(false)
      return
    }

    setLoading(true)

    try {
      const { data: favs, error: favsError } = await supabase
        .from('favorites')
        .select('*')
        .eq('user_id', user.id)
        .order('created_at', { ascending: false })

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

      // Fetch apartment details from FastAPI (retry once on failure)
      const apartmentIds = favs.map(f => f.apartment_id)
      let apartments: Apartment[] = []
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          apartments = await getApartmentsBatch(apartmentIds)
          break
        } catch (error) {
          if (attempt === 0) {
            // Wait briefly before retry
            await new Promise(r => setTimeout(r, 1000))
          } else {
            console.error('Failed to fetch apartment details after retry:', error)
          }
        }
      }

      const apartmentMap = new Map(apartments.map(a => [a.id, a]))

      // Use functional update to preserve existing apartment data for IDs the batch call missed
      setFavorites(prev => {
        const existingMap = new Map(prev.filter(f => f.apartment).map(f => [f.apartment_id, f.apartment]))
        return favs.map(fav => ({
          ...fav,
          apartment: apartmentMap.get(fav.apartment_id) || existingMap.get(fav.apartment_id) || null
        }))
      })
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

    // Check free tier limit (skip check while profile is still loading)
    if (!isPro && !profileLoading && favorites.length >= 5) {
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
    atLimit: !isPro && !profileLoading && favorites.length >= 5,
  }
}
