"""
Service for estimating true monthly cost of apartment listings.

Combines scraped fee data with regional utility/insurance estimates
to compute a realistic total monthly cost.
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

import re

# Amenity strings that explicitly claim utility inclusion. These match
# AFTER lowercasing+stripping the amenity. The lists grew 2026-06-17
# (task #18 follow-up) — original sets only had a handful of exact
# phrasings and missed common variants we saw in real listings.
_HEAT_INCLUDED = {
    "heat included",
    "heating included",
    "gas included",
    "heat & hot water included",
    "heat and hot water included",
    "heat/hot water included",
    "hot water included",
}
_WATER_INCLUDED = {
    "water included",
    "water/sewer included",
    "water and sewer included",
    "water & sewer included",
    "sewer included",
    "water sewer trash included",
    "water/sewer/trash included",
}
_ELECTRIC_INCLUDED = {
    "electric included",
    "electricity included",
}
_INTERNET_INCLUDED = {
    "internet included",
    "wifi included",
    "wi-fi included",
    "high-speed internet included",
    "high speed internet included",
    "cable & internet included",
}
_ALL_UTILITIES = {
    "utilities included",
    "all utilities included",
    "all bills paid",
    "all utilities paid",
    "utilities paid by owner",
    "utilities paid by landlord",
    "inclusive of utilities",
}
_IN_UNIT_LAUNDRY = {
    "in-unit washer/dryer",
    "in-unit laundry",
    "washer/dryer in unit",
    "washer/dryer",
    "washer & dryer",
    "washer and dryer",
    "w/d in unit",
}
_INSURANCE_REQUIRED = {"renters insurance required", "renters insurance program", "insurance required"}

# Description patterns. The previous implementation only had patterns
# for the "all utilities included" case. Real listings often state
# utility coverage for individual utilities ("Heat is included in
# rent", "Water/sewer paid by owner"). Tuples are (utility_label,
# compiled_regex) — `utility_label` matches the keys in the
# returned breakdown.
_DESC_ALL_UTILITIES_PATTERNS = [
    re.compile(p) for p in [
        r"all\s+utilities\s+included",
        r"utilities\s+(?:are\s+)?included(?:\s+in\s+rent)?",
        r"includes?\s+(?:all\s+)?utilities",
        r"utilities?\s+paid\s+by\s+(?:owner|landlord)",
        r"all\s+bills\s+paid",
        r"inclusive\s+of\s+utilities",
    ]
]
_DESC_PER_UTILITY_PATTERNS = {
    "heat": [
        re.compile(r"\b(?:heat|heating|hot\s*water)(?:\s*[/&]\s*hot\s*water|\s+and\s+hot\s*water)?\s+(?:is\s+)?included"),
        re.compile(r"\b(?:heat|heating|gas)(?:\s*[/&]\s*\w+)?\s+paid\s+by\s+(?:owner|landlord)"),
    ],
    "water": [
        re.compile(r"\b(?:water|sewer)(?:\s*/\s*(?:sewer|trash|water))*\s+(?:is\s+)?included"),
        re.compile(r"\b(?:water|sewer)(?:\s*/\s*(?:sewer|trash|water))*\s+paid\s+by\s+(?:owner|landlord)"),
    ],
    "electric": [
        re.compile(r"\belectric(?:ity)?\s+(?:is\s+)?included"),
        re.compile(r"\belectric(?:ity)?\s+paid\s+by\s+(?:owner|landlord)"),
    ],
    "internet": [
        re.compile(r"\b(?:wi-?fi|internet|cable\s+(?:and|&)\s+internet)\s+(?:is\s+)?included"),
    ],
}

# Negation window: if any of these tokens appear within ~30 chars BEFORE
# the matched phrase, we treat the match as a false positive. Catches
# "Utilities NOT included" / "Does not include utilities" / etc.
_NEGATION_TOKENS = re.compile(r"\b(?:not|no|n't|never|exclude|excluding|excluded|without|tenant\s+pays|resident\s+pays|paid\s+by\s+resident|paid\s+by\s+tenant)\b")


def _has_negation_before(text: str, match_start: int, window: int = 30) -> bool:
    """True if a negation token appears within `window` chars before match_start."""
    start = max(0, match_start - window)
    return bool(_NEGATION_TOKENS.search(text[start:match_start]))


def _desc_has_all_utilities(desc_lower: str) -> bool:
    """Check if description claims all utilities included, with negation guard."""
    for pat in _DESC_ALL_UTILITIES_PATTERNS:
        m = pat.search(desc_lower)
        if m and not _has_negation_before(desc_lower, m.start()):
            return True
    return False


def _desc_utility_included(desc_lower: str, utility: str) -> bool:
    """Check if description claims a SPECIFIC utility is included.

    Lets us catch "Heat is included" / "Water paid by owner" even when the
    listing doesn't claim "all utilities included" overall. Same negation
    guard as the all-utilities matcher.
    """
    patterns = _DESC_PER_UTILITY_PATTERNS.get(utility, [])
    for pat in patterns:
        m = pat.search(desc_lower)
        if m and not _has_negation_before(desc_lower, m.start()):
            return True
    return False


class CostEstimator:
    """Estimates true monthly apartment cost using scraped fees + regional averages."""

    def __init__(self):
        data_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "cost_estimates.json"
        )
        with open(data_path) as f:
            self._data = json.load(f)
        self._default = self._data["default"]

    def get_estimates(
        self, zip_code: Optional[str], bedrooms: int
    ) -> Dict[str, int]:
        """Look up regional cost estimates by zip prefix and bedroom count.

        Fallback chain: 3-digit zip prefix -> default.
        Bedroom count capped at 4.
        """
        bed_key = str(min(bedrooms, 4))

        if zip_code and len(zip_code) >= 3:
            prefix = zip_code[:3]
            region = self._data.get(prefix)
            if region and bed_key in region:
                return dict(region[bed_key])

        return dict(self._default[bed_key])

    def compute_true_cost(
        self,
        rent: int,
        zip_code: Optional[str],
        bedrooms: int,
        amenities: List[str],
        scraped_fees: Dict[str, Any],
        description: str = "",
    ) -> Dict[str, Any]:
        """Compute full cost breakdown for a listing.

        Args:
            rent: Base monthly rent.
            zip_code: Listing zip code (for regional estimates).
            bedrooms: Bedroom count.
            amenities: List of amenity strings from the listing.
            scraped_fees: Dict of fees extracted from scraping. Keys:
                pet_rent, parking_fee, amenity_fee (monthly),
                application_fee, security_deposit (one-time).
            description: Listing description text (used for utility detection).

        Returns:
            Dict with all cost line items, totals, and source tracking.
        """
        estimates = self.get_estimates(zip_code, bedrooms)
        amenity_set = {a.lower().strip() for a in amenities}
        desc_lower = (description or "").lower()

        # Determine which utilities are included. Three signals, OR'd together:
        #   1. The "all utilities included" claim (amenity set match OR
        #      description regex with negation guard).
        #   2. Per-utility amenity match (e.g. "heat included").
        #   3. Per-utility description match (e.g. "heat is included in rent"),
        #      also negation-guarded.
        all_included = bool(amenity_set & _ALL_UTILITIES) or _desc_has_all_utilities(desc_lower)
        heat_included = (
            all_included
            or bool(amenity_set & _HEAT_INCLUDED)
            or _desc_utility_included(desc_lower, "heat")
        )
        water_included = (
            all_included
            or bool(amenity_set & _WATER_INCLUDED)
            or _desc_utility_included(desc_lower, "water")
        )
        electric_included = (
            all_included
            or bool(amenity_set & _ELECTRIC_INCLUDED)
            or _desc_utility_included(desc_lower, "electric")
        )
        internet_included = (
            all_included
            or bool(amenity_set & _INTERNET_INCLUDED)
            or _desc_utility_included(desc_lower, "internet")
        )
        has_in_unit_laundry = bool(amenity_set & _IN_UNIT_LAUNDRY)
        insurance_required = bool(amenity_set & _INSURANCE_REQUIRED)

        # Build estimates (zero out included utilities)
        est_electric = 0 if electric_included else estimates["electric"]
        est_gas = 0 if heat_included else estimates["gas"]
        est_water = 0 if water_included else estimates["water"]
        est_internet = 0 if internet_included else estimates["internet"]
        est_renters_insurance = 0 if insurance_required else estimates["renters_insurance"]
        est_laundry = 0 if has_in_unit_laundry else estimates["laundry"]

        # Scraped monthly fees (default to 0 if not scraped)
        pet_rent = scraped_fees.get("pet_rent") or 0
        parking_fee = scraped_fees.get("parking_fee") or 0
        amenity_fee = scraped_fees.get("amenity_fee") or 0
        other_monthly_fees = scraped_fees.get("other_monthly_fees") or 0

        # One-time fees
        application_fee = scraped_fees.get("application_fee") or 0
        admin_fee = scraped_fees.get("admin_fee") or 0
        security_deposit = scraped_fees.get("security_deposit") or 0

        # Compute totals
        monthly_extras = (
            pet_rent + parking_fee + amenity_fee + other_monthly_fees
            + est_electric + est_gas + est_water
            + est_internet + est_renters_insurance + est_laundry
        )
        true_cost_monthly = rent + monthly_extras
        true_cost_move_in = application_fee + admin_fee + security_deposit + true_cost_monthly

        # Track data sources for transparency
        scraped_sources = [
            k for k in ("pet_rent", "parking_fee", "amenity_fee", "other_monthly_fees",
                        "application_fee", "admin_fee", "security_deposit")
            if scraped_fees.get(k)
        ]
        estimated_sources = [
            name for name, val in [
                ("est_electric", est_electric),
                ("est_gas", est_gas),
                ("est_water", est_water),
                ("est_internet", est_internet),
                ("est_renters_insurance", est_renters_insurance),
                ("est_laundry", est_laundry),
            ]
            if val > 0
        ]
        included_sources = []
        if electric_included:
            included_sources.append("electric")
        if heat_included:
            included_sources.append("heat")
        if water_included:
            included_sources.append("water")
        if has_in_unit_laundry:
            included_sources.append("laundry")
        if insurance_required:
            included_sources.append("renters_insurance")
        if internet_included:
            included_sources.append("internet")

        return {
            "base_rent": rent,
            "pet_rent": pet_rent,
            "parking_fee": parking_fee,
            "amenity_fee": amenity_fee,
            "other_monthly_fees": other_monthly_fees,
            "est_electric": est_electric,
            "est_gas": est_gas,
            "est_water": est_water,
            "est_internet": est_internet,
            "est_renters_insurance": est_renters_insurance,
            "est_laundry": est_laundry,
            "application_fee": application_fee,
            "admin_fee": admin_fee,
            "security_deposit": security_deposit,
            "true_cost_monthly": true_cost_monthly,
            "true_cost_move_in": true_cost_move_in,
            "sources": {
                "scraped": scraped_sources,
                "estimated": estimated_sources,
                "included": included_sources,
            },
        }
