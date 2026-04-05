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

# Amenity strings that indicate utilities are included
_HEAT_INCLUDED = {"heat included", "heating included", "gas included"}
_WATER_INCLUDED = {"water included", "water/sewer included"}
_ELECTRIC_INCLUDED = {"electric included", "electricity included"}
_ALL_UTILITIES = {"utilities included", "all utilities included"}
_IN_UNIT_LAUNDRY = {
    "in-unit washer/dryer",
    "in-unit laundry",
    "washer/dryer in unit",
    "washer/dryer",
    "washer & dryer",
    "washer and dryer",
    "w/d in unit",
}


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

        Returns:
            Dict with all cost line items, totals, and source tracking.
        """
        estimates = self.get_estimates(zip_code, bedrooms)
        amenity_set = {a.lower().strip() for a in amenities}

        # Determine which utilities are included
        all_included = bool(amenity_set & _ALL_UTILITIES)
        heat_included = all_included or bool(amenity_set & _HEAT_INCLUDED)
        water_included = all_included or bool(amenity_set & _WATER_INCLUDED)
        electric_included = all_included or bool(amenity_set & _ELECTRIC_INCLUDED)
        has_in_unit_laundry = bool(amenity_set & _IN_UNIT_LAUNDRY)

        # Build estimates (zero out included utilities)
        est_electric = 0 if electric_included else estimates["electric"]
        est_gas = 0 if heat_included else estimates["gas"]
        est_water = 0 if water_included else estimates["water"]
        est_internet = estimates["internet"]
        est_renters_insurance = estimates["renters_insurance"]
        est_laundry = 0 if has_in_unit_laundry else estimates["laundry"]

        # Scraped monthly fees (default to 0 if not scraped)
        pet_rent = scraped_fees.get("pet_rent") or 0
        parking_fee = scraped_fees.get("parking_fee") or 0
        amenity_fee = scraped_fees.get("amenity_fee") or 0
        other_monthly_fees = scraped_fees.get("other_monthly_fees") or 0

        # One-time fees
        application_fee = scraped_fees.get("application_fee") or 0
        security_deposit = scraped_fees.get("security_deposit") or 0

        # Compute totals
        monthly_extras = (
            pet_rent + parking_fee + amenity_fee + other_monthly_fees
            + est_electric + est_gas + est_water
            + est_internet + est_renters_insurance + est_laundry
        )
        true_cost_monthly = rent + monthly_extras
        true_cost_move_in = application_fee + security_deposit + true_cost_monthly

        # Track data sources for transparency
        scraped_sources = [
            k for k in ("pet_rent", "parking_fee", "amenity_fee", "other_monthly_fees")
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
            "security_deposit": security_deposit,
            "true_cost_monthly": true_cost_monthly,
            "true_cost_move_in": true_cost_move_in,
            "sources": {
                "scraped": scraped_sources,
                "estimated": estimated_sources,
                "included": included_sources,
            },
        }
