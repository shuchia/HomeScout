/**
 * API client for Snugd backend
 * Handles all communication with the FastAPI server
 */

import { SearchParams, SearchResponse, HealthResponse, Apartment, ApartmentWithScore, SearchContext, ComparisonAnalysis } from '@/types/apartment';
import { Tour, TourTag, TourNote } from '@/types/tour';
import { getAccessToken, isTokenExpiringSoon, refreshAccessToken } from './auth-store';

// Get API URL from environment variable, fallback to localhost
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Fetch with automatic token management:
 * 1. Proactively refreshes if token expires within 60 seconds
 * 2. Retries once on 401 after refreshing the token
 * 3. Detects permanent auth failure (expired refresh token) and stops retrying
 *
 * Use this for all endpoints that require or benefit from authentication.
 */
async function fetchWithAuth(url: string, init?: RequestInit): Promise<Response> {
  // Proactively refresh if we have a token that's about to expire
  if (getAccessToken() && isTokenExpiringSoon()) {
    const refreshed = await refreshAccessToken()
    if (!refreshed) {
      // Refresh failed permanently — session is dead.
      // Continue without auth; endpoint will return 401 if auth required.
    }
  }

  const addAuth = (headers?: HeadersInit): Record<string, string> => {
    const h: Record<string, string> = {}
    if (headers && typeof headers === 'object' && !Array.isArray(headers) && !(headers instanceof Headers)) {
      Object.assign(h, headers)
    }
    const token = getAccessToken()
    if (token) h['Authorization'] = `Bearer ${token}`
    return h
  }

  const response = await fetch(url, { ...init, headers: addAuth(init?.headers) })

  // Retry once on 401 — only if we can get a genuinely new token
  if (response.status === 401 && getAccessToken()) {
    const oldToken = getAccessToken()
    const newToken = await refreshAccessToken()
    // Only retry if we got a different, valid token
    if (newToken && newToken !== oldToken) {
      return fetch(url, { ...init, headers: addAuth(init?.headers) })
    }
    // Refresh returned null or same token — auth is permanently dead.
    // Return the 401 response so the caller can handle it.
  }

  return response
}

/**
 * Custom error class for API errors
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
    public details?: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Search for apartments based on user preferences
 * Calls POST /api/search endpoint
 *
 * @param params - Search parameters from the form
 * @returns Promise with apartment results and scores
 * @throws ApiError if request fails
 */
export async function searchApartments(params: SearchParams & { page?: number; page_size?: number }): Promise<SearchResponse> {
  try {
    const response = await fetchWithAuth(`${API_URL}/api/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      let message = errorData.detail || `Search failed with status ${response.status}`;
      if (response.status === 429 && !errorData.detail) {
        message = 'Too many requests. Please wait a moment before searching again.';
      }
      throw new ApiError(message, response.status, JSON.stringify(errorData));
    }

    const data: SearchResponse = await response.json();
    return data;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    // Network error or other issue
    throw new ApiError(
      'Unable to connect to the server. Please make sure the backend is running.',
      undefined,
      error instanceof Error ? error.message : 'Unknown error'
    );
  }
}

/**
 * Score a batch of apartments using Claude AI
 * Calls POST /api/search/score-batch endpoint
 *
 * @param apartmentIds - Array of apartment IDs to score
 * @param searchContext - Search context for scoring
 * @returns Promise with scores array
 */
export async function scoreBatch(
  apartmentIds: string[],
  searchContext: { city: string; budget: number; bedrooms: number; bathrooms: number; property_type: string; move_in_date: string; other_preferences?: string }
): Promise<{ scores: Array<{ apartment_id: string; match_score: number; reasoning: string; highlights: string[] }> }> {
  try {
    const response = await fetchWithAuth(`${API_URL}/api/search/score-batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        apartment_ids: apartmentIds,
        search_context: searchContext,
      }),
    })
    if (!response.ok) {
      return { scores: [] }
    }
    return response.json()
  } catch {
    return { scores: [] }
  }
}

/**
 * Check if the API server is healthy
 * Calls GET /health endpoint
 *
 * @returns Promise with health status
 * @throws ApiError if request fails
 */
export async function checkHealth(): Promise<HealthResponse> {
  try {
    const response = await fetch(`${API_URL}/health`);

    if (!response.ok) {
      throw new ApiError(
        'Health check failed',
        response.status
      );
    }

    return response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      'Unable to connect to the server',
      undefined,
      error instanceof Error ? error.message : 'Unknown error'
    );
  }
}

/**
 * Get the count of available apartments
 * Calls GET /api/apartments/count endpoint
 *
 * @returns Promise with apartment count
 */
export async function getApartmentCount(): Promise<{ count: number }> {
  try {
    const response = await fetch(`${API_URL}/api/apartments/count`);

    if (!response.ok) {
      throw new ApiError(
        'Failed to get apartment count',
        response.status
      );
    }

    return response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      'Unable to connect to the server',
      undefined,
      error instanceof Error ? error.message : 'Unknown error'
    );
  }
}

/**
 * Get multiple apartments by their IDs
 * Calls POST /api/apartments/batch endpoint
 *
 * @param ids - Array of apartment IDs to fetch
 * @returns Promise with array of apartments
 * @throws ApiError if request fails
 */
export async function getApartmentsBatch(ids: string[]): Promise<Apartment[]> {
  if (ids.length === 0) return [];

  try {
    const response = await fetch(`${API_URL}/api/apartments/batch`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(ids),
    });

    if (!response.ok) {
      throw new ApiError(
        'Failed to fetch apartments',
        response.status
      );
    }

    return response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      'Unable to connect to the server',
      undefined,
      error instanceof Error ? error.message : 'Unknown error'
    );
  }
}

/**
 * Response from the compare API endpoint
 */
export interface CompareResponse {
  apartments: ApartmentWithScore[];
  comparison_fields: string[];
  comparison_analysis?: ComparisonAnalysis;
  tier?: string;
}

/**
 * Compare apartments side-by-side with optional AI scoring
 * Calls POST /api/apartments/compare endpoint
 *
 * @param apartmentIds - Array of apartment IDs to compare (2-3)
 * @param preferences - Optional user preferences for AI scoring
 * @returns Promise with comparison data
 * @throws ApiError if request fails
 */
export async function compareApartments(
  apartmentIds: string[],
  preferences?: string,
  searchContext?: SearchContext
): Promise<CompareResponse> {
  try {
    const response = await fetchWithAuth(`${API_URL}/api/apartments/compare`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        apartment_ids: apartmentIds,
        preferences: preferences || null,
        search_context: searchContext || null,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || 'Failed to compare apartments',
        response.status,
        JSON.stringify(errorData)
      );
    }

    return response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      'Unable to connect to the server',
      undefined,
      error instanceof Error ? error.message : 'Unknown error'
    );
  }
}

/**
 * List all tours for the current user
 * Calls GET /api/tours endpoint
 *
 * @returns Promise with array of tours
 * @throws ApiError if request fails
 */
export async function listTours(): Promise<{ tours: Tour[] }> {
  const response = await fetchWithAuth(`${API_URL}/api/tours`)
  if (!response.ok) throw new ApiError('Failed to load tours', response.status)
  return response.json()
}

/**
 * Create a new tour pipeline entry for an apartment
 * Calls POST /api/tours endpoint
 *
 * @param apartmentId - The apartment ID to create a tour for
 * @returns Promise with the created tour
 * @throws ApiError if request fails
 */
export async function createTour(apartmentId: string): Promise<{ tour: Tour }> {
  const response = await fetchWithAuth(`${API_URL}/api/tours`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ apartment_id: apartmentId }),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new ApiError(data.detail || 'Failed to create tour', response.status)
  }
  return response.json()
}

/**
 * Delete a tour pipeline entry
 * Calls DELETE /api/tours/:id endpoint
 *
 * @param tourId - The tour ID to delete
 * @throws ApiError if request fails
 */
export async function deleteTour(tourId: string): Promise<void> {
  const response = await fetchWithAuth(`${API_URL}/api/tours/${tourId}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new ApiError('Failed to delete tour', response.status)
}

/**
 * Get a single tour by ID
 * Calls GET /api/tours/:id endpoint
 */
export async function getTour(tourId: string): Promise<{ tour: Tour }> {
  const response = await fetchWithAuth(`${API_URL}/api/tours/${tourId}`)
  if (!response.ok) {
    if (response.status === 404) throw new ApiError('Tour not found', 404)
    throw new ApiError('Failed to load tour', response.status)
  }
  return response.json()
}

/**
 * Update a tour's fields
 * Calls PATCH /api/tours/:id endpoint
 */
export async function updateTour(tourId: string, updates: Partial<{
  stage: string
  scheduled_date: string
  scheduled_time: string
  tour_rating: number
  decision: string
  decision_reason: string
  contact_phone: string
  contact_email: string
}>): Promise<{ tour: Tour }> {
  const response = await fetchWithAuth(`${API_URL}/api/tours/${tourId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!response.ok) throw new ApiError('Failed to update tour', response.status)
  return response.json()
}

/**
 * Add a note to a tour
 * Calls POST /api/tours/:id/notes endpoint
 */
export async function addTourNote(tourId: string, content: string): Promise<{ note: TourNote }> {
  const response = await fetchWithAuth(`${API_URL}/api/tours/${tourId}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!response.ok) throw new ApiError('Failed to add note', response.status)
  return response.json()
}

/**
 * Delete a note from a tour
 * Calls DELETE /api/tours/:id/notes/:noteId endpoint
 */
export async function deleteTourNote(tourId: string, noteId: string): Promise<void> {
  const response = await fetchWithAuth(`${API_URL}/api/tours/${tourId}/notes/${noteId}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new ApiError('Failed to delete note', response.status)
}

/**
 * Tag suggestion from the API
 */
export interface TagSuggestion {
  tag: string
  sentiment: 'pro' | 'con'
  count: number
}

/**
 * Get tag suggestions for tours
 * Calls GET /api/tours/tags/suggestions endpoint
 */
export async function getTagSuggestions(): Promise<{ suggestions: TagSuggestion[] }> {
  const response = await fetchWithAuth(`${API_URL}/api/tours/tags/suggestions`)
  if (!response.ok) throw new ApiError('Failed to load tag suggestions', response.status)
  return response.json()
}

/**
 * Add a tag to a tour
 * Calls POST /api/tours/:id/tags endpoint
 */
export async function addTourTag(tourId: string, tag: string, sentiment: 'pro' | 'con'): Promise<{ tag: TourTag }> {
  const response = await fetchWithAuth(`${API_URL}/api/tours/${tourId}/tags`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tag, sentiment }),
  })
  if (!response.ok) throw new ApiError('Failed to add tag', response.status)
  return response.json()
}

/**
 * Remove a tag from a tour
 * Calls DELETE /api/tours/:id/tags/:tagId endpoint
 */
export async function removeTourTag(tourId: string, tagId: string): Promise<void> {
  const response = await fetchWithAuth(`${API_URL}/api/tours/${tourId}/tags/${tagId}`, {
    method: 'DELETE',
  })
  if (!response.ok) throw new ApiError('Failed to remove tag', response.status)
}

/**
 * Generate an AI inquiry email draft for a tour's apartment
 * Calls POST /api/tours/:id/inquiry-email endpoint
 *
 * @param tourId - The tour ID to generate an email for
 * @param context - Optional user context (name, move_in_date, budget, preferences)
 * @returns Promise with subject and body
 * @throws ApiError if request fails
 */
export async function generateInquiryEmail(
  tourId: string,
  context?: { name?: string; move_in_date?: string; budget?: number; preferences?: string }
): Promise<{ subject: string; body: string; inquiry_email_draft: string }> {
  const response = await fetchWithAuth(`${API_URL}/api/tours/${tourId}/inquiry-email`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: context ? JSON.stringify(context) : undefined,
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new ApiError(data.detail || 'Failed to generate email', response.status)
  }
  return response.json()
}

/**
 * Upload a voice note audio recording for a tour
 * Calls POST /api/tours/:id/notes/voice endpoint
 *
 * @param tourId - The tour ID to attach the voice note to
 * @param audioBlob - The recorded audio Blob
 * @returns Promise with the created note
 * @throws ApiError if request fails
 */
export async function uploadVoiceNote(tourId: string, audioBlob: Blob): Promise<{ note: TourNote }> {
  const formData = new FormData()
  formData.append('file', audioBlob, 'voice-note.webm')
  const response = await fetchWithAuth(`${API_URL}/api/tours/${tourId}/notes/voice`, {
    method: 'POST',
    // No Content-Type header — browser sets multipart boundary automatically
    body: formData,
  })
  if (!response.ok) throw new ApiError('Failed to upload voice note', response.status)
  return response.json()
}

/**
 * Generate an AI-optimized day plan for multiple tours
 * Calls POST /api/tours/day-plan endpoint
 *
 * @param date - The date for the tour day (YYYY-MM-DD)
 * @param tourIds - Array of tour IDs to include in the plan
 * @returns Promise with ordered tours, travel notes, and tips
 * @throws ApiError if request fails
 */
export async function generateDayPlan(
  date: string,
  tourIds: string[]
): Promise<{ tours_ordered: Array<Record<string, unknown>>; travel_notes: string[]; tips: string[] }> {
  const response = await fetchWithAuth(`${API_URL}/api/tours/day-plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date, tour_ids: tourIds }),
  })
  if (!response.ok) throw new ApiError('Failed to generate day plan', response.status)
  return response.json()
}

/**
 * Enhance a tour note with AI — clean up text and suggest tags
 * Calls POST /api/tours/:id/enhance-note endpoint
 *
 * @param tourId - The tour ID the note belongs to
 * @param noteId - The note ID to enhance
 * @returns Promise with enhanced text and suggested tags
 * @throws ApiError if request fails
 */
export async function enhanceNote(
  tourId: string,
  noteId: string
): Promise<{ enhanced_text: string; suggested_tags: Array<{ tag: string; sentiment: string }> }> {
  const response = await fetchWithAuth(`${API_URL}/api/tours/${tourId}/enhance-note`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note_id: noteId }),
  })
  if (!response.ok) throw new ApiError('Failed to enhance note', response.status)
  return response.json()
}

/**
 * Generate an AI decision brief for all toured apartments
 * Calls POST /api/tours/decision-brief endpoint
 *
 * @returns Promise with apartment analyses and recommendation
 * @throws ApiError if request fails
 */
export async function generateDecisionBrief(): Promise<{
  apartments: Array<{ apartment_id: string; ai_take: string; strengths: string[]; concerns: string[] }>
  recommendation: { apartment_id: string; reasoning: string }
}> {
  const response = await fetchWithAuth(`${API_URL}/api/tours/decision-brief`, {
    method: 'POST',
  })
  if (!response.ok) throw new ApiError('Failed to generate decision brief', response.status)
  return response.json()
}

// Invite code endpoints
export async function redeemInviteCode(code: string): Promise<{ success: boolean; message: string; expires_at?: string }> {
  const res = await fetchWithAuth(`${API_URL}/api/invite/redeem`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to redeem code' }));
    throw new ApiError(err.detail || 'Failed to redeem code', res.status);
  }
  return res.json();
}

export async function getInviteStatus(): Promise<{ has_invite: boolean; expires_at?: string }> {
  const res = await fetchWithAuth(`${API_URL}/api/invite/status`);
  if (!res.ok) throw new ApiError('Failed to check invite status', res.status);
  return res.json();
}

// Billing endpoints
export async function createCheckoutSession(): Promise<{ url: string }> {
  const res = await fetchWithAuth(`${API_URL}/api/billing/checkout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to start checkout' }));
    throw new ApiError(err.detail || 'Failed to start checkout. Please try again.', res.status);
  }
  return res.json();
}

export async function createBillingPortalSession(): Promise<{ url: string }> {
  const res = await fetchWithAuth(`${API_URL}/api/billing/portal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to open billing portal' }));
    throw new ApiError(err.detail || 'Failed to open billing portal.', res.status);
  }
  return res.json();
}

// Feedback endpoint
export async function submitFeedback(data: {
  type: 'bug' | 'suggestion' | 'general';
  message: string;
  screenshot_url?: string;
  page_url?: string;
}): Promise<{ success: boolean; message: string }> {
  const res = await fetchWithAuth(`${API_URL}/api/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to submit feedback' }));
    throw new ApiError(err.detail || 'Failed to submit feedback', res.status);
  }
  return res.json();
}
