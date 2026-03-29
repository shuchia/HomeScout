/**
 * TypeScript interfaces for Snugd
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
 * Source tracking for cost estimates
 */
export interface CostSources {
  scraped: string[];
  estimated: string[];
  included: string[];
}

/**
 * Full cost breakdown (Pro users only)
 */
export interface CostBreakdown {
  base_rent: number;
  pet_rent: number;
  parking_fee: number;
  amenity_fee: number;
  est_electric: number;
  est_gas: number;
  est_water: number;
  est_internet: number;
  est_renters_insurance: number;
  est_laundry: number;
  application_fee: number;
  security_deposit: number;
  sources: CostSources;
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
  contact_phone?: string | null;
  contact_email?: string | null;
  true_cost_monthly?: number | null;
  true_cost_move_in?: number | null;
  cost_breakdown?: CostBreakdown | null;
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
  heuristic_score?: number;
  match_label?: string | null;
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
