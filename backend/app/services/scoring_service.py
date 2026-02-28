"""Heuristic scoring engine for apartment search results.

Computes a 0-100 score for each apartment against search criteria
using weighted components: budget fit, freshness, data quality,
amenity match, and space fit. No AI calls — pure math.
"""

from datetime import datetime
from typing import List, Optional, Set


PREFERENCE_KEYWORDS: dict[str, list[str]] = {
    "pet": ["pet-friendly", "pet friendly", "dogs allowed", "cats allowed", "pet"],
    "parking": ["parking", "garage", "covered parking", "ev charging"],
    "laundry": ["washer", "dryer", "in-unit laundry", "laundry"],
    "gym": ["gym", "fitness center", "fitness"],
    "pool": ["pool", "swimming"],
    "transit": ["transit", "metro", "subway", "bus", "train station"],
    "outdoor": ["balcony", "patio", "rooftop", "terrace", "yard"],
    "security": ["doorman", "concierge", "gated", "security"],
    "storage": ["storage", "closet space"],
    "utilities": ["utilities included", "wifi included", "water included"],
}


class ScoringService:
    """Stateless heuristic scoring for apartments."""

    @staticmethod
    def budget_fit_score(rent: int, budget: int) -> int:
        """Score how well rent fits the budget (0-100).

        100 if rent <= budget. Linear decay from 100 to 0
        across the 0-10% overshoot range. 0 if >10% over.
        """
        if budget <= 0:
            return 0
        if rent <= budget:
            return 100
        overshoot = (rent - budget) / budget
        if overshoot >= 0.10:
            return 0
        return int(100 * (1 - overshoot / 0.10))

    @staticmethod
    def freshness_score(
        freshness_confidence: Optional[int],
        last_seen_at: Optional[str],
    ) -> int:
        """Score listing freshness (0-100).

        Blends the DB freshness_confidence (70% weight) with
        recency of last_seen_at (30% weight).
        """
        conf = freshness_confidence if freshness_confidence is not None else 50
        conf = max(0, min(100, conf))

        if last_seen_at:
            try:
                last_seen = datetime.fromisoformat(last_seen_at.replace("Z", "+00:00"))
                age_days = (datetime.utcnow() - last_seen.replace(tzinfo=None)).total_seconds() / 86400
                recency = max(0, int(100 * (1 - age_days / 30)))
            except (ValueError, TypeError):
                recency = 50
        else:
            recency = 50

        return int(conf * 0.7 + recency * 0.3)

    @staticmethod
    def data_quality_score(quality: Optional[int]) -> int:
        """Score based on DB data_quality_score (0-100). Returns 50 if missing."""
        if quality is None:
            return 50
        return max(0, min(100, quality))

    @staticmethod
    def extract_preference_categories(other_preferences: Optional[str]) -> Set[str]:
        """Extract amenity categories from free-text preferences."""
        if not other_preferences:
            return set()
        text = other_preferences.lower()
        matched = set()
        for category, keywords in PREFERENCE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                matched.add(category)
        return matched

    @staticmethod
    def amenity_match_score(
        other_preferences: Optional[str],
        amenities: List[str],
    ) -> int:
        """Score how well listing amenities match user preferences (0-100).

        Extracts categories from other_preferences, checks each against
        the listing's amenities list. Returns 100 if no preferences given.
        """
        requested = ScoringService.extract_preference_categories(other_preferences)
        if not requested:
            return 100

        amenities_lower = " ".join(a.lower() for a in amenities)
        matched = 0
        for category in requested:
            keywords = PREFERENCE_KEYWORDS[category]
            if any(kw in amenities_lower for kw in keywords):
                matched += 1

        return int(matched / len(requested) * 100)

    @staticmethod
    def space_fit_score(
        bedrooms: int,
        requested_bedrooms: int,
        bathrooms: float,
        requested_bathrooms: float,
        sqft: Optional[int],
    ) -> int:
        """Score space fit (0-100).

        Bedroom match (40%), bathroom overshoot bonus (30%),
        sqft bonus (30% — 50 baseline if unavailable).
        """
        if bedrooms == requested_bedrooms:
            bed_score = 100
        elif abs(bedrooms - requested_bedrooms) == 1:
            bed_score = 60
        else:
            bed_score = 20

        if bathrooms >= requested_bathrooms:
            extra = bathrooms - requested_bathrooms
            bath_score = min(100, 80 + int(extra * 10))
        else:
            bath_score = 40

        if sqft and sqft > 0:
            expected = 800 + max(0, requested_bedrooms - 1) * 400
            ratio = sqft / expected
            sqft_score = min(100, int(ratio * 80))
        else:
            sqft_score = 50

        return int(bed_score * 0.4 + bath_score * 0.3 + sqft_score * 0.3)

    @staticmethod
    def compute_heuristic_score(
        rent: int,
        budget: int,
        freshness_confidence: Optional[int],
        last_seen_at: Optional[str],
        data_quality: Optional[int],
        other_preferences: Optional[str],
        amenities: List[str],
        bedrooms: int,
        requested_bedrooms: int,
        bathrooms: float,
        requested_bathrooms: float,
        sqft: Optional[int],
    ) -> int:
        """Compute weighted overall heuristic score (0-100).

        Weights: budget 30%, freshness 20%, quality 15%,
        amenity 20%, space 15%.
        """
        budget_s = ScoringService.budget_fit_score(rent, budget)
        fresh_s = ScoringService.freshness_score(freshness_confidence, last_seen_at)
        quality_s = ScoringService.data_quality_score(data_quality)
        amenity_s = ScoringService.amenity_match_score(other_preferences, amenities)
        space_s = ScoringService.space_fit_score(
            bedrooms, requested_bedrooms, bathrooms, requested_bathrooms, sqft
        )

        total = (
            budget_s * 0.30
            + fresh_s * 0.20
            + quality_s * 0.15
            + amenity_s * 0.20
            + space_s * 0.15
        )
        return int(total)

    @staticmethod
    def score_to_label(score: int) -> Optional[str]:
        """Map heuristic score to qualitative label for free users."""
        if score >= 90:
            return "Excellent Match"
        if score >= 75:
            return "Great Match"
        if score >= 60:
            return "Good Match"
        if score >= 40:
            return "Fair Match"
        return None

    @staticmethod
    def score_apartments_list(
        apartments: List[dict],
        budget: int,
        bedrooms: int,
        bathrooms: float,
        other_preferences: Optional[str] = None,
    ) -> List[dict]:
        """Score a list of apartments and return sorted (highest first).

        Adds 'heuristic_score' and 'match_label' to each apartment dict.
        """
        scored = []
        for apt in apartments:
            h_score = ScoringService.compute_heuristic_score(
                rent=apt.get("rent", 0),
                budget=budget,
                freshness_confidence=apt.get("freshness_confidence"),
                last_seen_at=apt.get("last_seen_at"),
                data_quality=apt.get("data_quality_score"),
                other_preferences=other_preferences,
                amenities=apt.get("amenities", []),
                bedrooms=apt.get("bedrooms", 0),
                requested_bedrooms=bedrooms,
                bathrooms=apt.get("bathrooms", 0),
                requested_bathrooms=bathrooms,
                sqft=apt.get("sqft"),
            )
            apt_with_score = {
                **apt,
                "heuristic_score": h_score,
                "match_label": ScoringService.score_to_label(h_score),
            }
            scored.append(apt_with_score)

        scored.sort(key=lambda x: x["heuristic_score"], reverse=True)
        return scored
