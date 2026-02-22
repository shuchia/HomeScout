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
  freshness_confidence?: number;
  first_seen_at?: string;
  times_seen?: number;
}

/**
 * Apartment with AI-generated match score and reasoning
 * Matches backend ApartmentWithScore model
 */
export interface ApartmentWithScore extends Apartment {
  match_score: number | null;
  reasoning: string | null;
  highlights: string[];
}

/**
 * Response from the search API endpoint
 * Matches backend SearchResponse model
 */
export interface SearchResponse {
  apartments: ApartmentWithScore[];
  total_results: number;
  tier?: string;
  searches_remaining?: number;
}

/**
 * Health check response
 */
export interface HealthResponse {
  status: string;
  message: string;
}

/**
 * Search context passed from search page to compare page
 */
export interface SearchContext {
  city: string;
  budget: number;
  bedrooms: number;
  bathrooms: number;
  property_type: string;
  move_in_date: string;
}

/**
 * Score and note for a single comparison category
 */
export interface CategoryScore {
  score: number;
  note: string;
}

/**
 * Detailed comparison scoring for one apartment
 */
export interface ApartmentComparisonScore {
  apartment_id: string;
  overall_score: number;
  reasoning: string;
  highlights: string[];
  category_scores: Record<string, CategoryScore>;
}

/**
 * The winning apartment and why
 */
export interface ComparisonWinner {
  apartment_id: string;
  reason: string;
}

/**
 * Full comparison analysis returned by Claude
 */
export interface ComparisonAnalysis {
  winner: ComparisonWinner;
  categories: string[];
  apartment_scores: ApartmentComparisonScore[];
}
