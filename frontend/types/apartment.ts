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
  // Proximity search
  near_lat?: number;
  near_lng?: number;
  near_label?: string;
  max_distance_miles?: number;
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
  other_monthly_fees: number;
  est_electric: number;
  est_gas: number;
  est_water: number;
  est_internet: number;
  est_renters_insurance: number;
  est_laundry: number;
  application_fee: number;
  admin_fee: number;
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
  /** Human-friendly range label like "Studio–1 BR" when the listing covers
   * multiple floor plans; null when the listing has a single value (use bedrooms). */
  beds_label?: string | null;
  /** Same for bathrooms, e.g. "1–2 BA". Null = use bathrooms field. */
  baths_label?: string | null;
  sqft: number;
  property_type: string;
  available_date: string;
  amenities: string[];
  neighborhood: string;
  description: string;
  images: string[];
  source_url?: string | null;
  contact_phone?: string | null;
  contact_email?: string | null;
  contact_name?: string | null;
  property_website?: string | null;
  walk_score?: number | null;
  transit_score?: number | null;
  apartments_com_rating?: number | null;
  specials?: ApartmentSpecial | null;
  available_units?: ApartmentUnit[];
  transit_options?: ApartmentTransitOption[];
  virtual_tour_urls?: string[];
  true_cost_monthly?: number | null;
  true_cost_move_in?: number | null;
  cost_breakdown?: CostBreakdown | null;
  pricing_model?: 'per_unit' | 'per_person' | null;
  freshness_confidence?: number;
  first_seen_at?: string;
  times_seen?: number;
  distance_miles?: number | null;
}

/**
 * Promotion / special offer attached to a listing (e.g. "Lease today, get one month free").
 * Shape mirrors what apartments.com surfaces — `description` is the long-form
 * detail, `label` or `title` is the short pill text.
 */
export interface ApartmentSpecial {
  title?: string | null;
  label?: string | null;
  description?: string | null;
}

/**
 * A single available unit within a property (when the listing represents a
 * building with multiple floor plans).
 */
export interface ApartmentUnit {
  unitNumber?: string | null;
  beds?: number | string | null;
  baths?: number | string | null;
  sqft?: number | null;
  price?: number | string | null;
  availableDate?: string | null;
}

/**
 * Nearby transit option scraped from apartments.com.
 */
export interface ApartmentTransitOption {
  name?: string | null;
  walk?: string | null;
  drive?: string | null;
  distance?: string | null;
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
  page: number;
  has_more: boolean;
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
  near_lat?: number;
  near_lng?: number;
  near_label?: string;
  max_distance_miles?: number;
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
