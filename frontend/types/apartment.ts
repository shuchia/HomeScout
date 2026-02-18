/**
 * TypeScript interfaces for HomeScout
 * These types mirror the backend Pydantic models for type safety
 */

/**
 * Search parameters for apartment search
 * Matches backend SearchRequest model
 */
export interface SearchParams {
  city: string;
  budget: number;
  bedrooms: number;
  bathrooms: number;
  property_type: string;
  move_in_date: string;
  other_preferences?: string;
}

/**
 * Base apartment listing data
 * Matches backend Apartment model
 */
export interface Apartment {
  id: string;
  address: string;
  rent: number;
  bedrooms: number;
  bathrooms: number;
  sqft: number;
  property_type: string;
  available_date: string;
  amenities: string[];
  neighborhood: string;
  description: string;
  images: string[];
}

/**
 * Apartment with AI-generated match score and reasoning
 * Matches backend ApartmentWithScore model
 */
export interface ApartmentWithScore extends Apartment {
  match_score: number;
  reasoning: string;
  highlights: string[];
}

/**
 * Response from the search API endpoint
 * Matches backend SearchResponse model
 */
export interface SearchResponse {
  apartments: ApartmentWithScore[];
  total_results: number;
}

/**
 * Health check response
 */
export interface HealthResponse {
  status: string;
  message: string;
}
