/**
 * API client for HomeScout backend
 * Handles all communication with the FastAPI server
 */

import { SearchParams, SearchResponse, HealthResponse, Apartment, ApartmentWithScore, SearchContext, ComparisonAnalysis } from '@/types/apartment';
import { Tour } from '@/types/tour';
import { getAccessToken } from './auth-store';

// Get API URL from environment variable, fallback to localhost
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Get authorization headers using the current access token.
 * Reads synchronously from the auth-store (updated by AuthContext on every
 * session change / token refresh). Never calls getSession() — no hanging.
 */
function getAuthHeaders(): Record<string, string> {
  const token = getAccessToken()
  if (token) {
    return { Authorization: `Bearer ${token}` }
  }
  return {}
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
export async function searchApartments(params: SearchParams): Promise<SearchResponse> {
  try {
    const authHeaders = getAuthHeaders()
    const response = await fetch(`${API_URL}/api/search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders,
      },
      body: JSON.stringify(params),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || `Search failed with status ${response.status}`,
        response.status,
        JSON.stringify(errorData)
      );
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
    const authHeaders = getAuthHeaders()
    const response = await fetch(`${API_URL}/api/apartments/compare`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders,
      },
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
  const authHeaders = getAuthHeaders()
  const response = await fetch(`${API_URL}/api/tours`, {
    headers: authHeaders,
  })
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
  const authHeaders = getAuthHeaders()
  const response = await fetch(`${API_URL}/api/tours`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders },
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
  const authHeaders = getAuthHeaders()
  const response = await fetch(`${API_URL}/api/tours/${tourId}`, {
    method: 'DELETE',
    headers: authHeaders,
  })
  if (!response.ok) throw new ApiError('Failed to delete tour', response.status)
}
