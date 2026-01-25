/**
 * API client for HomeScout backend
 * Handles all communication with the FastAPI server
 */

import { SearchParams, SearchResponse, HealthResponse } from '@/types/apartment';

// Get API URL from environment variable, fallback to localhost
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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
    const response = await fetch(`${API_URL}/api/search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
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
