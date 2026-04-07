"""
Abstract base class for all scrapers.
Defines the common interface and data structures for scraping apartment listings.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class ScraperStatus(Enum):
    """Status of a scraper run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScrapedListing:
    """
    Normalized data structure for a scraped apartment listing.
    All scrapers must convert their source-specific data to this format.
    """
    # Required fields
    external_id: str  # ID from the source
    source: str  # Source identifier (zillow, apartments_com, craigslist)
    address: str  # Full address as scraped
    rent: int  # Monthly rent in dollars
    bedrooms: int  # Number of bedrooms
    bathrooms: float  # Number of bathrooms (can be 1.5, etc.)
    property_type: str  # Apartment, Condo, House, etc.

    # Optional location fields
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    neighborhood: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Optional listing details
    sqft: Optional[int] = None
    available_date: Optional[str] = None  # YYYY-MM-DD format
    description: Optional[str] = None
    amenities: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    source_url: Optional[str] = None

    # Fee fields (extracted from listing)
    pet_rent: Optional[int] = None
    parking_fee: Optional[int] = None
    amenity_fee: Optional[int] = None
    application_fee: Optional[int] = None
    admin_fee: Optional[int] = None
    security_deposit: Optional[int] = None
    other_monthly_fees: Optional[int] = None  # Catch-all for unmatched monthly fees

    # Contact info (extracted from listing)
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None

    # Raw data for debugging
    raw_data: Optional[Dict[str, Any]] = None

    # Timestamps
    scraped_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "external_id": self.external_id,
            "source": self.source,
            "source_url": self.source_url,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "zip_code": self.zip_code,
            "neighborhood": self.neighborhood,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "rent": self.rent,
            "bedrooms": self.bedrooms,
            "bathrooms": self.bathrooms,
            "sqft": self.sqft,
            "property_type": self.property_type,
            "available_date": self.available_date,
            "description": self.description,
            "amenities": self.amenities,
            "images": self.images,
            "pet_rent": self.pet_rent,
            "parking_fee": self.parking_fee,
            "amenity_fee": self.amenity_fee,
            "application_fee": self.application_fee,
            "admin_fee": self.admin_fee,
            "security_deposit": self.security_deposit,
            "other_monthly_fees": self.other_monthly_fees,
            "contact_phone": self.contact_phone,
            "contact_email": self.contact_email,
            "raw_data": self.raw_data,
        }


@dataclass
class ScrapeResult:
    """Result of a scraping operation."""
    status: ScraperStatus
    listings: List[ScrapedListing] = field(default_factory=list)
    total_found: int = 0
    errors: List[str] = field(default_factory=list)
    external_job_id: Optional[str] = None
    external_job_url: Optional[str] = None
    api_calls_made: int = 0
    estimated_cost_cents: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def success_count(self) -> int:
        """Number of successfully scraped listings."""
        return len(self.listings)

    @property
    def error_count(self) -> int:
        """Number of errors encountered."""
        return len(self.errors)

    @property
    def duration_seconds(self) -> Optional[float]:
        """Duration of the scrape in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class BaseScraper(ABC):
    """
    Abstract base class for all apartment scrapers.

    Subclasses must implement:
    - scrape(): Main scraping method
    - _normalize_listing(): Convert source-specific data to ScrapedListing
    """

    def __init__(self, source_id: str):
        """
        Initialize the scraper.

        Args:
            source_id: Unique identifier for this data source
        """
        self.source_id = source_id

    @abstractmethod
    async def scrape(
        self,
        city: str,
        state: str,
        max_listings: int = 100,
        **kwargs
    ) -> ScrapeResult:
        """
        Scrape apartment listings for a given city.

        Args:
            city: City name
            state: State code (e.g., "CA")
            max_listings: Maximum number of listings to return
            **kwargs: Additional source-specific parameters

        Returns:
            ScrapeResult with listings and metadata
        """
        pass

    @abstractmethod
    def _normalize_listing(self, raw_data: Dict[str, Any]) -> Optional[ScrapedListing]:
        """
        Convert source-specific data to a normalized ScrapedListing.

        Args:
            raw_data: Raw data from the scraping source

        Returns:
            ScrapedListing or None if data is invalid
        """
        pass

    async def health_check(self) -> Dict[str, Any]:
        """
        Check if the scraper/API is healthy.

        Returns:
            Dict with health status and details
        """
        return {
            "source_id": self.source_id,
            "healthy": True,
            "message": "Health check not implemented",
        }

    def _parse_rent(self, rent_value: Any) -> Optional[int]:
        """
        Parse rent value from various formats.

        Args:
            rent_value: Rent as string, int, or None

        Returns:
            Rent as integer or None
        """
        if rent_value is None:
            return None
        if isinstance(rent_value, int):
            return rent_value
        if isinstance(rent_value, float):
            return int(rent_value)
        if isinstance(rent_value, str):
            # Remove currency symbols, commas, and whitespace
            cleaned = rent_value.replace("$", "").replace(",", "").strip()
            # Handle ranges like "$2,000 - $2,500" by taking the lower bound
            if "-" in cleaned:
                cleaned = cleaned.split("-")[0].strip()
            try:
                return int(float(cleaned))
            except ValueError:
                return None
        return None

    def _parse_bedrooms(self, bed_value: Any) -> int:
        """
        Parse bedroom count from various formats.

        Args:
            bed_value: Bedrooms as string, int, or None

        Returns:
            Bedroom count (default 0 for studio)
        """
        import re

        if bed_value is None:
            return 0
        if isinstance(bed_value, int):
            return bed_value
        if isinstance(bed_value, str):
            bed_lower = bed_value.lower().strip()
            if "studio" in bed_lower:
                return 0
            # Handle formats like "1 bd", "2 bed", "1 - 2 bd", "Studio - 2 bd"
            # Extract numbers and take the first one (minimum beds)
            matches = re.findall(r'(\d+)\s*(?:bd|bed|br|bedroom)', bed_lower)
            if matches:
                return int(matches[0])
            # Fallback: try to extract any number
            matches = re.findall(r'(\d+)', bed_lower)
            if matches:
                return int(matches[0])
            try:
                return int(float(bed_value.replace("+", "").strip()))
            except ValueError:
                return 0
        return 0

    def _parse_bathrooms(self, bath_value: Any) -> float:
        """
        Parse bathroom count from various formats.

        Args:
            bath_value: Bathrooms as string, int, float, or None

        Returns:
            Bathroom count (default 1.0)
        """
        import re

        if bath_value is None:
            return 1.0
        if isinstance(bath_value, (int, float)):
            return float(bath_value)
        if isinstance(bath_value, str):
            bath_lower = bath_value.lower().strip()
            # Handle formats like "1 ba", "1.5 bath", "1 - 2 ba"
            matches = re.findall(r'(\d+\.?\d*)\s*(?:ba|bath|bathroom)', bath_lower)
            if matches:
                return float(matches[0])
            # Fallback: try to extract any number
            matches = re.findall(r'(\d+\.?\d*)', bath_lower)
            if matches:
                return float(matches[0])
            try:
                return float(bath_value.replace("+", "").strip())
            except ValueError:
                return 1.0
        return 1.0

    def _normalize_property_type(self, prop_type: str) -> str:
        """
        Normalize property type to standard values.

        Args:
            prop_type: Raw property type string

        Returns:
            Normalized property type
        """
        if not prop_type:
            return "Apartment"

        prop_lower = prop_type.lower()

        if any(t in prop_lower for t in ["apartment", "apt", "flat"]):
            return "Apartment"
        if any(t in prop_lower for t in ["condo", "condominium"]):
            return "Condo"
        if any(t in prop_lower for t in ["house", "home", "single family"]):
            return "House"
        if any(t in prop_lower for t in ["townhouse", "townhome", "town home"]):
            return "Townhouse"
        if "studio" in prop_lower:
            return "Apartment"
        if "duplex" in prop_lower:
            return "Duplex"

        return "Apartment"  # Default

    def _normalize_amenities(self, amenities: Any) -> List[str]:
        """
        Normalize amenities list.

        Args:
            amenities: Raw amenities (string, list, or None)

        Returns:
            List of normalized amenity strings
        """
        if not amenities:
            return []

        if isinstance(amenities, str):
            # Split by common delimiters
            items = amenities.replace(";", ",").split(",")
            return [item.strip() for item in items if item.strip()]

        if isinstance(amenities, list):
            return [str(item).strip() for item in amenities if item]

        return []
