"""
Address standardization service.
Normalizes addresses to a consistent format for deduplication.
"""
import re
import logging
from typing import Optional, Dict, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ParsedAddress:
    """Parsed and standardized address components."""
    street_number: Optional[str] = None
    street_name: Optional[str] = None
    street_type: Optional[str] = None
    unit: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    full_address: Optional[str] = None
    normalized: Optional[str] = None


class AddressStandardizer:
    """
    Address standardization using pattern matching.

    Normalizes addresses for consistent comparison and deduplication.
    Uses regex-based parsing when usaddress library is not available.
    """

    # Street type abbreviations mapping
    STREET_TYPES = {
        "avenue": "Ave",
        "ave": "Ave",
        "av": "Ave",
        "boulevard": "Blvd",
        "blvd": "Blvd",
        "circle": "Cir",
        "cir": "Cir",
        "court": "Ct",
        "ct": "Ct",
        "drive": "Dr",
        "dr": "Dr",
        "expressway": "Expy",
        "expy": "Expy",
        "freeway": "Fwy",
        "fwy": "Fwy",
        "highway": "Hwy",
        "hwy": "Hwy",
        "lane": "Ln",
        "ln": "Ln",
        "parkway": "Pkwy",
        "pkwy": "Pkwy",
        "place": "Pl",
        "pl": "Pl",
        "road": "Rd",
        "rd": "Rd",
        "square": "Sq",
        "sq": "Sq",
        "street": "St",
        "st": "St",
        "terrace": "Ter",
        "ter": "Ter",
        "trail": "Trl",
        "trl": "Trl",
        "way": "Way",
    }

    # Direction abbreviations
    DIRECTIONS = {
        "north": "N",
        "south": "S",
        "east": "E",
        "west": "W",
        "northeast": "NE",
        "northwest": "NW",
        "southeast": "SE",
        "southwest": "SW",
        "n": "N",
        "s": "S",
        "e": "E",
        "w": "W",
        "ne": "NE",
        "nw": "NW",
        "se": "SE",
        "sw": "SW",
    }

    # State abbreviations
    STATE_ABBREVS = {
        "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
        "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
        "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
        "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
        "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
        "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
        "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
        "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
        "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
        "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
        "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
        "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
        "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
    }

    # Unit type patterns
    UNIT_PATTERNS = [
        r"(?:apt|apartment|unit|suite|ste|#)\s*[#]?\s*([a-z0-9-]+)",
        r"(?:floor|fl)\s*(\d+)",
    ]

    def __init__(self):
        """Initialize the address standardizer."""
        self._usaddress = None
        self._postal = None
        self._load_optional_libraries()

    def _load_optional_libraries(self):
        """Try to load optional address parsing libraries."""
        try:
            import usaddress
            self._usaddress = usaddress
            logger.info("usaddress library loaded for enhanced address parsing")
        except ImportError:
            logger.info("usaddress library not available, using regex-based parsing")

    def standardize(self, address: str) -> ParsedAddress:
        """
        Standardize an address to a consistent format.

        Args:
            address: Raw address string

        Returns:
            ParsedAddress with normalized components
        """
        if not address:
            return ParsedAddress()

        # Clean the address
        cleaned = self._clean_address(address)

        # Try usaddress first if available
        if self._usaddress:
            parsed = self._parse_with_usaddress(cleaned)
            if parsed.normalized:
                return parsed

        # Fall back to regex parsing
        return self._parse_with_regex(cleaned)

    def _clean_address(self, address: str) -> str:
        """Clean and normalize an address string."""
        # Remove extra whitespace
        cleaned = " ".join(address.split())

        # Remove common prefixes
        cleaned = re.sub(r"^(address|addr|at|located at)[:\s]+", "", cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

    def _parse_with_usaddress(self, address: str) -> ParsedAddress:
        """Parse address using usaddress library."""
        try:
            parsed, addr_type = self._usaddress.tag(address)

            result = ParsedAddress(full_address=address)

            # Extract components
            result.street_number = parsed.get("AddressNumber", "")
            result.street_name = self._build_street_name(parsed)
            result.street_type = self._normalize_street_type(
                parsed.get("StreetNamePostType", "")
            )
            result.unit = parsed.get("OccupancyIdentifier", "")
            result.city = parsed.get("PlaceName", "")
            result.state = self._normalize_state(parsed.get("StateName", ""))
            result.zip_code = parsed.get("ZipCode", "")

            # Build normalized address
            result.normalized = self._build_normalized_address(result)

            return result

        except Exception as e:
            logger.warning(f"usaddress parsing failed: {e}")
            return ParsedAddress(full_address=address)

    def _build_street_name(self, parsed: Dict) -> str:
        """Build complete street name from parsed components."""
        parts = []

        # Pre-direction
        pre_dir = parsed.get("StreetNamePreDirectional", "")
        if pre_dir:
            parts.append(self._normalize_direction(pre_dir))

        # Street name
        street = parsed.get("StreetName", "")
        if street:
            parts.append(street.title())

        return " ".join(parts)

    def _parse_with_regex(self, address: str) -> ParsedAddress:
        """Parse address using regex patterns."""
        result = ParsedAddress(full_address=address)

        # Split by comma to get parts
        parts = [p.strip() for p in address.split(",")]

        if not parts:
            return result

        # First part is usually street address
        street_part = parts[0]

        # Extract street number
        num_match = re.match(r"^(\d+[-/]?\d*)\s+", street_part)
        if num_match:
            result.street_number = num_match.group(1)
            street_part = street_part[num_match.end():]

        # Extract unit number
        for pattern in self.UNIT_PATTERNS:
            unit_match = re.search(pattern, street_part, re.IGNORECASE)
            if unit_match:
                result.unit = unit_match.group(1).upper()
                street_part = re.sub(pattern, "", street_part, flags=re.IGNORECASE)
                break

        # Extract and normalize street type
        for street_type, abbrev in self.STREET_TYPES.items():
            pattern = rf"\b{street_type}\b\.?"
            if re.search(pattern, street_part, re.IGNORECASE):
                result.street_type = abbrev
                street_part = re.sub(pattern, "", street_part, flags=re.IGNORECASE)
                break

        # Remaining is street name
        result.street_name = " ".join(street_part.split()).title()

        # Process remaining parts for city, state, zip
        if len(parts) >= 2:
            city_state_zip = parts[1].strip()

            # Try to extract state and zip from end
            state_zip_match = re.search(
                r"([A-Za-z\s]+)[,\s]+([A-Z]{2})\s*(\d{5}(?:-\d{4})?)?$",
                city_state_zip
            )
            if state_zip_match:
                result.city = state_zip_match.group(1).strip().title()
                result.state = state_zip_match.group(2).upper()
                result.zip_code = state_zip_match.group(3) or ""
            else:
                # Try simpler patterns
                result.city = city_state_zip.title()

        if len(parts) >= 3:
            state_zip = parts[2].strip()
            state_zip_match = re.match(r"([A-Z]{2})\s*(\d{5}(?:-\d{4})?)?", state_zip, re.IGNORECASE)
            if state_zip_match:
                result.state = state_zip_match.group(1).upper()
                result.zip_code = state_zip_match.group(2) or ""

        # Build normalized address
        result.normalized = self._build_normalized_address(result)

        return result

    def _build_normalized_address(self, parsed: ParsedAddress) -> str:
        """Build a normalized address string from components."""
        parts = []

        # Street address
        street_parts = []
        if parsed.street_number:
            street_parts.append(parsed.street_number)
        if parsed.street_name:
            street_parts.append(parsed.street_name)
        if parsed.street_type:
            street_parts.append(parsed.street_type)

        if street_parts:
            parts.append(" ".join(street_parts))

        # Unit
        if parsed.unit:
            parts.append(f"#{parsed.unit}")

        # City, State, Zip
        location_parts = []
        if parsed.city:
            location_parts.append(parsed.city)
        if parsed.state:
            location_parts.append(parsed.state)
        if parsed.zip_code:
            location_parts.append(parsed.zip_code)

        if location_parts:
            parts.append(", ".join([" ".join(location_parts[:2])] + location_parts[2:]))

        return ", ".join(parts) if parts else parsed.full_address or ""

    def _normalize_street_type(self, street_type: str) -> str:
        """Normalize street type to standard abbreviation."""
        if not street_type:
            return ""
        lower = street_type.lower().rstrip(".")
        return self.STREET_TYPES.get(lower, street_type.title())

    def _normalize_direction(self, direction: str) -> str:
        """Normalize direction to standard abbreviation."""
        if not direction:
            return ""
        lower = direction.lower().rstrip(".")
        return self.DIRECTIONS.get(lower, direction.upper())

    def _normalize_state(self, state: str) -> str:
        """Normalize state name to abbreviation."""
        if not state:
            return ""
        # Already an abbreviation
        if len(state) == 2:
            return state.upper()
        # Full name
        lower = state.lower()
        return self.STATE_ABBREVS.get(lower, state.upper()[:2])

    def get_address_key(self, address: str) -> str:
        """
        Generate a key for address comparison/deduplication.

        Returns a lowercase, punctuation-stripped version for matching.
        """
        parsed = self.standardize(address)
        if not parsed.normalized:
            return address.lower()

        # Create key by removing punctuation and lowercasing
        key = re.sub(r"[^\w\s]", "", parsed.normalized.lower())
        key = " ".join(key.split())  # Normalize whitespace

        return key

    def addresses_match(self, addr1: str, addr2: str, threshold: float = 0.9) -> bool:
        """
        Check if two addresses likely refer to the same location.

        Args:
            addr1: First address
            addr2: Second address
            threshold: Similarity threshold (0.0 to 1.0)

        Returns:
            True if addresses likely match
        """
        key1 = self.get_address_key(addr1)
        key2 = self.get_address_key(addr2)

        # Exact match
        if key1 == key2:
            return True

        # Try fuzzy matching
        similarity = self._calculate_similarity(key1, key2)
        return similarity >= threshold

    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate similarity ratio between two strings.
        Uses Levenshtein distance if available, else simple ratio.
        """
        try:
            from fuzzywuzzy import fuzz
            return fuzz.ratio(s1, s2) / 100.0
        except ImportError:
            # Simple character-based similarity
            if not s1 or not s2:
                return 0.0
            common = set(s1.split()) & set(s2.split())
            total = set(s1.split()) | set(s2.split())
            return len(common) / len(total) if total else 0.0
