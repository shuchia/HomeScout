export interface GeocodeSuggestion {
  display_name: string
  lat: number
  lng: number
}

const NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'

let lastRequestTime = 0

export async function geocodeSearch(query: string): Promise<GeocodeSuggestion[]> {
  if (!query || query.length < 3) return []

  // Respect Nominatim 1 req/sec rate limit
  const now = Date.now()
  const elapsed = now - lastRequestTime
  if (elapsed < 1000) {
    await new Promise((resolve) => setTimeout(resolve, 1000 - elapsed))
  }
  lastRequestTime = Date.now()

  const params = new URLSearchParams({
    q: query,
    format: 'json',
    limit: '5',
    countrycodes: 'us',
  })

  const response = await fetch(`${NOMINATIM_URL}?${params}`, {
    headers: {
      'User-Agent': 'Snugd/1.0 (https://snugd.ai)',
    },
  })

  if (!response.ok) return []

  const data = await response.json()
  return data.map((item: { display_name: string; lat: string; lon: string }) => ({
    display_name: item.display_name,
    lat: parseFloat(item.lat),
    lng: parseFloat(item.lon),
  }))
}
