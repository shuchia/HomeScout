"""
Main normalization pipeline for apartment listings.
Handles address standardization, field validation, and data quality scoring.
"""
import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass

from app.services.normalization.address_standardizer import AddressStandardizer
from app.services.scrapers.base_scraper import ScrapedListing
from app.services.cost_estimator import CostEstimator

logger = logging.getLogger(__name__)


@dataclass
class NormalizationResult:
    """Result of normalizing a listing."""
    success: bool
    listing: Optional[Dict[str, Any]]
    quality_score: int
    errors: List[str]
    warnings: List[str]


class NormalizationService:
    """
    Service for normalizing apartment listings.

    Pipeline:
    1. Validate required fields
    2. Standardize address
    3. Normalize property type
    4. Validate and convert data types
    5. Infer missing data where possible
    6. Calculate data quality score
    """

    # Property type mappings
    PROPERTY_TYPES = {
        "apartment": "Apartment",
        "apt": "Apartment",
        "flat": "Apartment",
        "studio": "Apartment",
        "condo": "Condo",
        "condominium": "Condo",
        "house": "House",
        "home": "House",
        "single family": "House",
        "single-family": "House",
        "townhouse": "Townhouse",
        "townhome": "Townhouse",
        "town home": "Townhouse",
        "town house": "Townhouse",
        "duplex": "Duplex",
        "triplex": "Triplex",
        "loft": "Loft",
    }

    # Average sqft per bedroom for inference
    SQFT_PER_BEDROOM = {
        0: 450,   # Studio
        1: 700,
        2: 1000,
        3: 1400,
        4: 1800,
        5: 2200,
    }

    def __init__(self):
        """Initialize the normalization service."""
        self.address_standardizer = AddressStandardizer()
        self.cost_estimator = CostEstimator()

    def normalize(self, listing: ScrapedListing) -> NormalizationResult:
        """
        Normalize a scraped listing.

        Args:
            listing: ScrapedListing to normalize

        Returns:
            NormalizationResult with normalized data and quality score
        """
        errors = []
        warnings = []

        # Start with basic conversion to dict
        data = listing.to_dict()

        # Step 1: Validate required fields
        if not data.get("address"):
            errors.append("Missing required field: address")
        if not data.get("rent") or data["rent"] <= 0:
            errors.append("Missing or invalid required field: rent")
        if data.get("bedrooms") is None:
            errors.append("Missing required field: bedrooms")
        if data.get("bathrooms") is None:
            errors.append("Missing required field: bathrooms")

        if errors:
            return NormalizationResult(
                success=False,
                listing=None,
                quality_score=0,
                errors=errors,
                warnings=warnings,
            )

        # Step 2: Standardize address
        parsed_address = self.address_standardizer.standardize(data["address"])
        data["address_normalized"] = parsed_address.normalized

        # Extract address components if not already present
        if not data.get("city") and parsed_address.city:
            data["city"] = parsed_address.city
        if not data.get("state") and parsed_address.state:
            data["state"] = parsed_address.state
        if not data.get("zip_code") and parsed_address.zip_code:
            data["zip_code"] = parsed_address.zip_code

        # Step 3: Normalize property type
        data["property_type"] = self._normalize_property_type(data.get("property_type", ""))

        # Step 4: Validate and normalize data types
        data["rent"] = self._validate_rent(data["rent"], warnings)
        data["bedrooms"] = self._validate_bedrooms(data["bedrooms"], warnings)
        data["bathrooms"] = self._validate_bathrooms(data["bathrooms"], warnings)
        data["sqft"] = self._validate_sqft(data.get("sqft"), warnings)

        # Step 5: Normalize available date (preserve sentinel values "Now" and "Unavailable")
        if data.get("available_date") and data["available_date"] not in ("Now", "Unavailable"):
            data["available_date"] = self._normalize_date(data["available_date"], warnings)

        # Step 6: Normalize amenities
        data["amenities"] = self._normalize_amenities(data.get("amenities", []))

        # Step 7: Validate and clean images
        data["images"] = self._validate_images(data.get("images", []), warnings)

        # Step 8: Infer missing data
        if not data.get("sqft") or data["sqft"] == 0:
            inferred_sqft = self._infer_sqft(data["bedrooms"])
            if inferred_sqft:
                data["sqft"] = inferred_sqft
                warnings.append(f"Inferred sqft from bedroom count: {inferred_sqft}")

        # Step 9: Clean description
        if data.get("description"):
            data["description"] = self._clean_description(data["description"])

        # Step 10: Compute true cost breakdown
        scraped_fees = {
            "pet_rent": data.get("pet_rent"),
            "parking_fee": data.get("parking_fee"),
            "amenity_fee": data.get("amenity_fee"),
            "application_fee": data.get("application_fee"),
            "security_deposit": data.get("security_deposit"),
        }
        try:
            cost_breakdown = self.cost_estimator.compute_true_cost(
                rent=data["rent"],
                zip_code=data.get("zip_code"),
                bedrooms=data["bedrooms"],
                amenities=data.get("amenities", []),
                scraped_fees=scraped_fees,
            )
            data["true_cost_monthly"] = cost_breakdown["true_cost_monthly"]
            data["true_cost_move_in"] = cost_breakdown["true_cost_move_in"]
            data["est_electric"] = cost_breakdown["est_electric"]
            data["est_gas"] = cost_breakdown["est_gas"]
            data["est_water"] = cost_breakdown["est_water"]
            data["est_internet"] = cost_breakdown["est_internet"]
            data["est_renters_insurance"] = cost_breakdown["est_renters_insurance"]
            data["est_laundry"] = cost_breakdown["est_laundry"]
            data["utilities_included"] = {
                "heat": cost_breakdown["est_gas"] == 0,
                "water": cost_breakdown["est_water"] == 0,
                "electric": cost_breakdown["est_electric"] == 0,
            }
        except Exception as e:
            logger.warning(f"Failed to compute true cost: {e}")

        # Step 11: Calculate quality score
        quality_score = self._calculate_quality_score(data)

        return NormalizationResult(
            success=True,
            listing=data,
            quality_score=quality_score,
            errors=errors,
            warnings=warnings,
        )

    def normalize_batch(self, listings: List[ScrapedListing]) -> List[NormalizationResult]:
        """
        Normalize a batch of listings.

        Args:
            listings: List of ScrapedListings

        Returns:
            List of NormalizationResults
        """
        return [self.normalize(listing) for listing in listings]

    def _normalize_property_type(self, prop_type: str) -> str:
        """Normalize property type to standard value."""
        if not prop_type:
            return "Apartment"

        lower = prop_type.lower().strip()
        return self.PROPERTY_TYPES.get(lower, "Apartment")

    def _validate_rent(self, rent: Any, warnings: List[str]) -> int:
        """Validate and normalize rent value."""
        if isinstance(rent, int):
            return max(0, rent)
        if isinstance(rent, float):
            return max(0, int(rent))
        if isinstance(rent, str):
            try:
                cleaned = rent.replace("$", "").replace(",", "").strip()
                return max(0, int(float(cleaned)))
            except ValueError:
                warnings.append(f"Could not parse rent value: {rent}")
                return 0
        return 0

    def _validate_bedrooms(self, bedrooms: Any, warnings: List[str]) -> int:
        """Validate and normalize bedroom count."""
        if isinstance(bedrooms, int):
            return max(0, bedrooms)
        if isinstance(bedrooms, float):
            return max(0, int(bedrooms))
        if isinstance(bedrooms, str):
            lower = bedrooms.lower()
            if "studio" in lower:
                return 0
            try:
                return max(0, int(float(bedrooms.replace("+", ""))))
            except ValueError:
                warnings.append(f"Could not parse bedrooms: {bedrooms}")
                return 0
        return 0

    def _validate_bathrooms(self, bathrooms: Any, warnings: List[str]) -> float:
        """Validate and normalize bathroom count."""
        if isinstance(bathrooms, (int, float)):
            return max(0.0, float(bathrooms))
        if isinstance(bathrooms, str):
            try:
                return max(0.0, float(bathrooms.replace("+", "")))
            except ValueError:
                warnings.append(f"Could not parse bathrooms: {bathrooms}")
                return 1.0
        return 1.0

    def _validate_sqft(self, sqft: Any, warnings: List[str]) -> Optional[int]:
        """Validate and normalize square footage."""
        if sqft is None:
            return None
        if isinstance(sqft, int):
            return sqft if sqft > 0 else None
        if isinstance(sqft, float):
            return int(sqft) if sqft > 0 else None
        if isinstance(sqft, str):
            try:
                cleaned = sqft.replace(",", "").replace("sq ft", "").replace("sqft", "").strip()
                value = int(float(cleaned))
                return value if value > 0 else None
            except ValueError:
                return None
        return None

    def _normalize_date(self, date_str: str, warnings: List[str]) -> str:
        """Normalize date to YYYY-MM-DD format."""
        if not date_str:
            return ""

        # Already in correct format
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return date_str

        # Try common formats
        formats = [
            "%m/%d/%Y",
            "%m/%d/%y",
            "%Y/%m/%d",
            "%d/%m/%Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%m-%d-%Y",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # Handle relative dates
        lower = date_str.lower()
        if "now" in lower or "immediate" in lower or "available" in lower:
            return datetime.now().strftime("%Y-%m-%d")

        warnings.append(f"Could not parse date: {date_str}")
        return ""

    def _normalize_amenities(self, amenities: Any) -> List[str]:
        """Normalize and deduplicate amenities list."""
        if not amenities:
            return []

        if isinstance(amenities, str):
            items = amenities.replace(";", ",").split(",")
        elif isinstance(amenities, list):
            items = [str(a) for a in amenities]
        else:
            return []

        # Clean and deduplicate
        normalized = []
        seen = set()

        for item in items:
            cleaned = item.strip()
            if cleaned and cleaned.lower() not in seen:
                # Title case for consistency
                normalized.append(cleaned.title())
                seen.add(cleaned.lower())

        return normalized

    def _validate_images(self, images: Any, warnings: List[str]) -> List[str]:
        """Validate and filter image URLs."""
        if not images:
            return []

        if isinstance(images, str):
            images = [images]

        valid_images = []
        for url in images:
            if isinstance(url, str):
                # Basic URL validation
                if url.startswith(("http://", "https://")):
                    valid_images.append(url)
                elif url.startswith("//"):
                    valid_images.append(f"https:{url}")

        return valid_images

    def _infer_sqft(self, bedrooms: int) -> Optional[int]:
        """Infer square footage from bedroom count."""
        return self.SQFT_PER_BEDROOM.get(bedrooms, self.SQFT_PER_BEDROOM.get(5))

    def _clean_description(self, description: str) -> str:
        """Clean and normalize description text."""
        if not description:
            return ""

        # Remove excessive whitespace
        cleaned = " ".join(description.split())

        # Remove common spam patterns
        spam_patterns = [
            r"call now[!]*",
            r"act fast[!]*",
            r"won't last[!]*",
            r"schedule.*tour",
            r"\d{3}[-.]?\d{3}[-.]?\d{4}",  # Phone numbers
        ]

        for pattern in spam_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # Trim to reasonable length
        if len(cleaned) > 2000:
            cleaned = cleaned[:2000] + "..."

        return cleaned.strip()

    def _calculate_quality_score(self, data: Dict[str, Any]) -> int:
        """
        Calculate data quality score (0-100).

        Scores based on:
        - Presence of required fields (base 40 points)
        - Presence of optional fields (up to 40 points)
        - Data completeness and validity (up to 20 points)
        """
        score = 0

        # Required fields (40 points)
        if data.get("address"):
            score += 10
        if data.get("rent") and data["rent"] > 0:
            score += 10
        if data.get("bedrooms") is not None:
            score += 10
        if data.get("bathrooms") is not None:
            score += 10

        # Optional fields (40 points)
        if data.get("address_normalized"):
            score += 5
        if data.get("city"):
            score += 5
        if data.get("state"):
            score += 3
        if data.get("zip_code"):
            score += 3
        if data.get("neighborhood"):
            score += 4
        if data.get("sqft") and data["sqft"] > 0:
            score += 5
        if data.get("available_date"):
            score += 3
        if data.get("description") and len(data["description"]) > 50:
            score += 4
        if data.get("amenities") and len(data["amenities"]) > 0:
            score += 4
        if data.get("images") and len(data["images"]) > 0:
            score += 4

        # Quality bonuses (20 points)
        # Multiple images
        if data.get("images") and len(data["images"]) >= 3:
            score += 5
        if data.get("images") and len(data["images"]) >= 5:
            score += 3
        """
        Main normalization pipeline for apartment listings.
        Handles address standardization, field validation, and data quality scoring.
        """
        import logging
        import re
        from typing import Dict, Any, List, Optional
        from datetime import datetime
        from dataclasses import dataclass

        from app.services.normalization.address_standardizer import AddressStandardizer
        from app.services.scrapers.base_scraper import ScrapedListing
        from app.services.cost_estimator import CostEstimator

        logger = logging.getLogger(__name__)

        @dataclass
        class NormalizationResult:
            """Result of normalizing a listing."""
            success: bool
            listing: Optional[Dict[str, Any]]
            quality_score: int
            errors: List[str]
            warnings: List[str]

        class NormalizationService:
            """
            Service for normalizing apartment listings.

            Pipeline:
            1. Validate required fields
            2. Standardize address
            3. Normalize property type
            4. Validate and convert data types
            5. Infer missing data where possible
            6. Calculate data quality score
            """

            # Property type mappings
            PROPERTY_TYPES = {
                "apartment": "Apartment",
                "apt": "Apartment",
                "flat": "Apartment",
                "studio": "Apartment",
                "condo": "Condo",
                "condominium": "Condo",
                "house": "House",
                "home": "House",
                "single family": "House",
                "single-family": "House",
                "townhouse": "Townhouse",
                "townhome": "Townhouse",
                "town home": "Townhouse",
                "town house": "Townhouse",
                "duplex": "Duplex",
                "triplex": "Triplex",
                "loft": "Loft",
            }

            # Average sqft per bedroom for inference
            SQFT_PER_BEDROOM = {
                0: 450,  # Studio
                1: 700,
                2: 1000,
                3: 1400,
                4: 1800,
                5: 2200,
            }

            def __init__(self):
                """Initialize the normalization service."""
                self.address_standardizer = AddressStandardizer()
                self.cost_estimator = CostEstimator()

            def normalize(self, listing: ScrapedListing) -> NormalizationResult:
                """
                Normalize a scraped listing.

                Args:
                    listing: ScrapedListing to normalize

                Returns:
                    NormalizationResult with normalized data and quality score
                """
                errors = []
                warnings = []

                # Start with basic conversion to dict
                data = listing.to_dict()

                # Step 1: Validate required fields
                if not data.get("address"):
                    errors.append("Missing required field: address")
                if not data.get("rent") or data["rent"] <= 0:
                    errors.append("Missing or invalid required field: rent")
                if data.get("bedrooms") is None:
                    errors.append("Missing required field: bedrooms")
                if data.get("bathrooms") is None:
                    errors.append("Missing required field: bathrooms")

                if errors:
                    return NormalizationResult(
                        success=False,
                        listing=None,
                        quality_score=0,
                        errors=errors,
                        warnings=warnings,
                    )

                # Step 2: Standardize address
                parsed_address = self.address_standardizer.standardize(data["address"])
                data["address_normalized"] = parsed_address.normalized

                # Extract address components if not already present
                if not data.get("city") and parsed_address.city:
                    data["city"] = parsed_address.city
                if not data.get("state") and parsed_address.state:
                    data["state"] = parsed_address.state
                if not data.get("zip_code") and parsed_address.zip_code:
                    data["zip_code"] = parsed_address.zip_code

                # Step 3: Normalize property type
                data["property_type"] = self._normalize_property_type(data.get("property_type", ""))

                # Step 4: Validate and normalize data types
                data["rent"] = self._validate_rent(data["rent"], warnings)
                data["bedrooms"] = self._validate_bedrooms(data["bedrooms"], warnings)
                data["bathrooms"] = self._validate_bathrooms(data["bathrooms"], warnings)
                data["sqft"] = self._validate_sqft(data.get("sqft"), warnings)

                # Step 5: Normalize available date (preserve sentinel values "Now" and "Unavailable")
                if data.get("available_date") and data["available_date"] not in ("Now", "Unavailable"):
                    data["available_date"] = self._normalize_date(data["available_date"], warnings)

                # Step 6: Normalize amenities
                data["amenities"] = self._normalize_amenities(data.get("amenities", []))

                # Step 7: Validate and clean images
                data["images"] = self._validate_images(data.get("images", []), warnings)

                # Step 8: Infer missing data
                if not data.get("sqft") or data["sqft"] == 0:
                    inferred_sqft = self._infer_sqft(data["bedrooms"])
                    if inferred_sqft:
                        data["sqft"] = inferred_sqft
                        warnings.append(f"Inferred sqft from bedroom count: {inferred_sqft}")

                # Step 9: Clean description
                if data.get("description"):
                    data["description"] = self._clean_description(data["description"])

                # Step 10: Compute true cost breakdown
                scraped_fees = {
                    "pet_rent": data.get("pet_rent"),
                    "parking_fee": data.get("parking_fee"),
                    "amenity_fee": data.get("amenity_fee"),
                    "application_fee": data.get("application_fee"),
                    "security_deposit": data.get("security_deposit"),
                }
                try:
                    cost_breakdown = self.cost_estimator.compute_true_cost(
                        rent=data["rent"],
                        zip_code=data.get("zip_code"),
                        bedrooms=data["bedrooms"],
                        amenities=data.get("amenities", []),
                        scraped_fees=scraped_fees,
                    )
                    data["true_cost_monthly"] = cost_breakdown["true_cost_monthly"]
                    data["true_cost_move_in"] = cost_breakdown["true_cost_move_in"]
                    data["est_electric"] = cost_breakdown["est_electric"]
                    data["est_gas"] = cost_breakdown["est_gas"]
                    data["est_water"] = cost_breakdown["est_water"]
                    data["est_internet"] = cost_breakdown["est_internet"]
                    data["est_renters_insurance"] = cost_breakdown["est_renters_insurance"]
                    data["est_laundry"] = cost_breakdown["est_laundry"]
                    data["utilities_included"] = {
                        "heat": cost_breakdown["est_gas"] == 0,
                        "water": cost_breakdown["est_water"] == 0,
                        "electric": cost_breakdown["est_electric"] == 0,
                    }
                except Exception as e:
                    logger.warning(f"Failed to compute true cost: {e}")

                # Step 11: Calculate quality score
                quality_score = self._calculate_quality_score(data)

                return NormalizationResult(
                    success=True,
                    listing=data,
                    quality_score=quality_score,
                    errors=errors,
                    warnings=warnings,
                )

            def normalize_batch(self, listings: List[ScrapedListing]) -> List[NormalizationResult]:
                """
                Normalize a batch of listings.

                Args:
                    listings: List of ScrapedListings

                Returns:
                    List of NormalizationResults
                """
                return [self.normalize(listing) for listing in listings]

            def _normalize_property_type(self, prop_type: str) -> str:
                """Normalize property type to standard value."""
                if not prop_type:
                    return "Apartment"

                lower = prop_type.lower().strip()
                return self.PROPERTY_TYPES.get(lower, "Apartment")

            def _validate_rent(self, rent: Any, warnings: List[str]) -> int:
                """Validate and normalize rent value."""
                if isinstance(rent, int):
                    return max(0, rent)
                if isinstance(rent, float):
                    return max(0, int(rent))
                if isinstance(rent, str):
                    try:
                        cleaned = rent.replace("$", "").replace(",", "").strip()
                        return max(0, int(float(cleaned)))
                    except ValueError:
                        warnings.append(f"Could not parse rent value: {rent}")
                        return 0
                return 0

            def _validate_bedrooms(self, bedrooms: Any, warnings: List[str]) -> int:
                """Validate and normalize bedroom count."""
                if isinstance(bedrooms, int):
                    return max(0, bedrooms)
                if isinstance(bedrooms, float):
                    return max(0, int(bedrooms))
                if isinstance(bedrooms, str):
                    lower = bedrooms.lower()
                    if "studio" in lower:
                        return 0
                    try:
                        return max(0, int(float(bedrooms.replace("+", ""))))
                    except ValueError:
                        warnings.append(f"Could not parse bedrooms: {bedrooms}")
                        return 0
                return 0

            def _validate_bathrooms(self, bathrooms: Any, warnings: List[str]) -> float:
                """Validate and normalize bathroom count."""
                if isinstance(bathrooms, (int, float)):
                    return max(0.0, float(bathrooms))
                if isinstance(bathrooms, str):
                    try:
                        return max(0.0, float(bathrooms.replace("+", "")))
                    except ValueError:
                        warnings.append(f"Could not parse bathrooms: {bathrooms}")
                        return 1.0
                return 1.0

            def _validate_sqft(self, sqft: Any, warnings: List[str]) -> Optional[int]:
                """Validate and normalize square footage."""
                if sqft is None:
                    return None
                if isinstance(sqft, int):
                    return sqft if sqft > 0 else None
                if isinstance(sqft, float):
                    return int(sqft) if sqft > 0 else None
                if isinstance(sqft, str):
                    try:
                        cleaned = sqft.replace(",", "").replace("sq ft", "").replace("sqft", "").strip()
                        value = int(float(cleaned))
                        return value if value > 0 else None
                    except ValueError:
                        return None
                return None

            def _normalize_date(self, date_str: str, warnings: List[str]) -> str:
                """Normalize date to YYYY-MM-DD format."""
                if not date_str:
                    return ""

                # Already in correct format
                if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
                    return date_str

                # Try common formats
                formats = [
                    "%m/%d/%Y",
                    "%m/%d/%y",
                    "%Y/%m/%d",
                    "%d/%m/%Y",
                    "%B %d, %Y",
                    "%b %d, %Y",
                    "%m-%d-%Y",
                ]

                for fmt in formats:
                    try:
                        dt = datetime.strptime(date_str.strip(), fmt)
                        return dt.strftime("%Y-%m-%d")
                    except ValueError:
                        continue

                # Handle relative dates
                lower = date_str.lower()
                if "now" in lower or "immediate" in lower or "available" in lower:
                    return datetime.now().strftime("%Y-%m-%d")

                warnings.append(f"Could not parse date: {date_str}")
                return ""

            def _normalize_amenities(self, amenities: Any) -> List[str]:
                """Normalize and deduplicate amenities list."""
                if not amenities:
                    return []

                if isinstance(amenities, str):
                    items = amenities.replace(";", ",").split(",")
                elif isinstance(amenities, list):
                    items = [str(a) for a in amenities]
                else:
                    return []

                # Clean and deduplicate
                normalized = []
                seen = set()

                for item in items:
                    cleaned = item.strip()
                    if cleaned and cleaned.lower() not in seen:
                        # Title case for consistency
                        normalized.append(cleaned.title())
                        seen.add(cleaned.lower())

                return normalized

            def _validate_images(self, images: Any, warnings: List[str]) -> List[str]:
                """Validate and filter image URLs."""
                if not images:
                    return []

                if isinstance(images, str):
                    images = [images]

                valid_images = []
                for url in images:
                    if isinstance(url, str):
                        # Basic URL validation
                        if url.startswith(("http://", "https://")):
                            valid_images.append(url)
                        elif url.startswith("//"):
                            valid_images.append(f"https:{url}")

                return valid_images

            def _infer_sqft(self, bedrooms: int) -> Optional[int]:
                """Infer square footage from bedroom count."""
                return self.SQFT_PER_BEDROOM.get(bedrooms, self.SQFT_PER_BEDROOM.get(5))

            def _clean_description(self, description: str) -> str:
                """Clean and normalize description text."""
                if not description:
                    return ""

                # Remove excessive whitespace
                cleaned = " ".join(description.split())

                # Remove common spam patterns
                spam_patterns = [
                    r"call now[!]*",
                    r"act fast[!]*",
                    r"won't last[!]*",
                    r"schedule.*tour",
                    r"\d{3}[-.]?\d{3}[-.]?\d{4}",  # Phone numbers
                ]

                for pattern in spam_patterns:
                    cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

                # Trim to reasonable length
                if len(cleaned) > 2000:
                    cleaned = cleaned[:2000] + "..."

                return cleaned.strip()

            def _calculate_quality_score(self, data: Dict[str, Any]) -> int:
                """
                Calculate data quality score (0-100).

                Scores based on:
                - Presence of required fields (base 40 points)
                - Presence of optional fields (up to 40 points)
                - Data completeness and validity (up to 20 points)
                """
                score = 0

                # Required fields (40 points)
                if data.get("address"):
                    score += 10
                if data.get("rent") and data["rent"] > 0:
                    score += 10
                if data.get("bedrooms") is not None:
                    score += 10
                if data.get("bathrooms") is not None:
                    score += 10

                # Optional fields (40 points)
                if data.get("address_normalized"):
                    score += 5
                if data.get("city"):
                    score += 5
                if data.get("state"):
                    score += 3
                if data.get("zip_code"):
                    score += 3
                if data.get("neighborhood"):
                    score += 4
                if data.get("sqft") and data["sqft"] > 0:
                    score += 5
                if data.get("available_date"):
                    score += 3
                if data.get("description") and len(data["description"]) > 50:
                    score += 4
                if data.get("amenities") and len(data["amenities"]) > 0:
                    score += 4
                if data.get("images") and len(data["images"]) > 0:
                    score += 4

                # Quality bonuses (20 points)
                # Multiple images
                if data.get("images") and len(data["images"]) >= 3:
                    score += 5
                if data.get("images") and len(data["images"]) >= 5:
                    score += 3

                # Detailed amenities
                if data.get("amenities") and len(data["amenities"]) >= 5:
                    score += 4

                # Source URL present
                if data.get("source_url"):
                    score += 3

                # Coordinates present
                if data.get("latitude") and data.get("longitude"):
                    score += 5

                return min(100, score)

        # Detailed amenities
        if data.get("amenities") and len(data["amenities"]) >= 5:
            score += 4

        # Source URL present
        if data.get("source_url"):
            score += 3

        # Coordinates present
        if data.get("latitude") and data.get("longitude"):
            score += 5

        return min(100, score)
