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
  const { user } = useAuth()
  const [favorites, setFavorites] = useState<FavoriteWithApartment[]>([])
  const [loading, setLoading] = useState(true)

  const loadFavorites = useCallback(async () => {
    if (!user) {
      setFavorites([])
      setLoading(false)
      return
    }

    setLoading(true)

    // Get favorites from Supabase
    const { data: favs } = await supabase
      .from('favorites')
      .select('*')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false })

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

    const { error } = await supabase.from('favorites').insert({
      user_id: user.id,
      apartment_id: apartmentId,
    })

    return !error
  }

  async function removeFavorite(apartmentId: string): Promise<boolean> {
    if (!user) return false

    const { error } = await supabase
      .from('favorites')
      .delete()
      .eq('user_id', user.id)
      .eq('apartment_id', apartmentId)

    return !error
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
    refresh: loadFavorites
  }
}
