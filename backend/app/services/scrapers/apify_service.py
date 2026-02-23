"""
Apify SDK integration for scraping Zillow, Apartments.com, and Rentals.com.
Uses pre-built Apify actors for reliable data collection.
"""
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

import httpx

from app.services.scrapers.base_scraper import (
    BaseScraper,
    ScrapedListing,
    ScrapeResult,
    ScraperStatus,
)

logger = logging.getLogger(__name__)


class ApifyService(BaseScraper):
    """
    Scraper service using Apify for major rental platforms.

    Supported sources:
    - Zillow (maxcopell/zillow-scraper)
    - Apartments.com (epctex/apartments-scraper)
    """

    # Actor IDs for different platforms
    # Note: Use ~ instead of / for actors owned by other users
    ACTORS = {
        "zillow": os.getenv("APIFY_ZILLOW_ACTOR_ID", "maxcopell~zillow-scraper"),
        "apartments_com": os.getenv("APIFY_APARTMENTS_ACTOR_ID", "epctex~apartments-scraper-api"),
        "realtor": os.getenv("APIFY_REALTOR_ACTOR_ID", "epctex~realtor-scraper"),
        "rent_com": os.getenv("APIFY_RENT_ACTOR_ID", "jupri~rent-com-scraper"),
    }

    # Apify API configuration
    API_BASE_URL = "https://api.apify.com/v2"

    def __init__(self, source_id: str = "zillow"):
        """
        Initialize the Apify scraper.

        Args:
            source_id: Which platform to scrape (zillow, apartments_com)
        """
        super().__init__(source_id)
        self.api_token = os.getenv("APIFY_API_TOKEN")

        if not self.api_token:
            logger.warning("APIFY_API_TOKEN not set - Apify scraping will be disabled")

        self.actor_id = self.ACTORS.get(source_id, self.ACTORS["zillow"])
        self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-load HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(300.0),  # 5 minute timeout for long-running scrapes
                headers={"Authorization": f"Bearer {self.api_token}"}
            )
        return self._client

    async def scrape(
        self,
        city: str,
        state: str,
        max_listings: int = 100,
        **kwargs
    ) -> ScrapeResult:
        """
        Scrape rental listings using Apify.

        Args:
            city: City name (e.g., "San Francisco")
            state: State code (e.g., "CA")
            max_listings: Maximum listings to return
            **kwargs: Additional parameters (min_price, max_price, bedrooms, etc.)

        Returns:
            ScrapeResult with normalized listings
        """
        # Reset client to avoid event loop issues when called from Celery tasks
        # Each run_async() creates a new event loop, so we need a fresh client
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

        result = ScrapeResult(
            status=ScraperStatus.PENDING,
            started_at=datetime.utcnow()
        )

        if not self.api_token:
            result.status = ScraperStatus.FAILED
            result.errors.append("APIFY_API_TOKEN not configured")
            result.completed_at = datetime.utcnow()
            return result

        try:
            result.status = ScraperStatus.RUNNING

            # Build actor input based on source
            actor_input = self._build_actor_input(city, state, max_listings, **kwargs)

            # Run the actor
            run_result = await self._run_actor(actor_input)

            if not run_result:
                result.status = ScraperStatus.FAILED
                result.errors.append("Actor run failed or returned no data")
                result.completed_at = datetime.utcnow()
                return result

            result.external_job_id = run_result.get("id")
            result.external_job_url = f"https://console.apify.com/actors/runs/{run_result.get('id')}"
            result.api_calls_made = 1

            # Get dataset items
            dataset_id = run_result.get("defaultDatasetId")
            logger.info(f"Run {run_result.get('id')} completed. defaultDatasetId={dataset_id}, status={run_result.get('status')}")
            if dataset_id:
                items = await self._get_dataset_items(dataset_id, max_listings)
                result.total_found = len(items)
                logger.info(f"Fetched {len(items)} items from dataset {dataset_id}")

                # Normalize listings
                for item in items:
                    listing = self._normalize_listing(item)
                    if listing:
                        result.listings.append(listing)

                logger.info(f"Normalized {len(result.listings)}/{len(items)} listings")
            else:
                logger.warning(f"No defaultDatasetId in run result. Keys: {list(run_result.keys())}")

            result.status = ScraperStatus.COMPLETED
            result.estimated_cost_cents = self._estimate_cost(len(result.listings))

        except Exception as e:
            logger.exception(f"Error during Apify scrape: {e}")
            result.status = ScraperStatus.FAILED
            result.errors.append(str(e))

        result.completed_at = datetime.utcnow()
        return result

    def _build_actor_input(
        self,
        city: str,
        state: str,
        max_listings: int,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Build input parameters for the Apify actor.

        Args:
            city: City name
            state: State code
            max_listings: Max results
            **kwargs: Additional filters

        Returns:
            Dict of actor input parameters
        """
        if self.source_id == "zillow":
            return self._build_zillow_input(city, state, max_listings, **kwargs)
        elif self.source_id == "apartments_com":
            return self._build_apartments_com_input(city, state, max_listings, **kwargs)
        elif self.source_id == "realtor":
            return self._build_realtor_input(city, state, max_listings, **kwargs)
        elif self.source_id == "rent_com":
            return self._build_rent_com_input(city, state, max_listings, **kwargs)
        else:
            return self._build_apartments_com_input(city, state, max_listings, **kwargs)

    def _build_zillow_input(
        self,
        city: str,
        state: str,
        max_listings: int,
        **kwargs
    ) -> Dict[str, Any]:
        """Build Zillow actor input."""
        # Format city for Zillow URL (lowercase, hyphenated)
        city_slug = city.lower().replace(" ", "-")
        state_slug = state.lower()

        # Build Zillow rental search URL
        zillow_url = f"https://www.zillow.com/{city_slug}-{state_slug}/rentals/"

        actor_input = {
            "searchUrls": [{"url": zillow_url}],
            "maxItems": max_listings,
        }

        return actor_input

    def _build_apartments_com_input(
        self,
        city: str,
        state: str,
        max_listings: int,
        **kwargs
    ) -> Dict[str, Any]:
        """Build Apartments.com actor input for apartments-scraper-api."""
        return {
            "search": f"{city}, {state}",
            "maxItems": max_listings,
            "includeInteriorAmenities": kwargs.get("include_amenities", True),
            "includeReviews": kwargs.get("include_reviews", True),
            "includeVisuals": kwargs.get("include_visuals", True),
            "includeWalkScore": kwargs.get("include_walk_score", True),
        }

    def _build_realtor_input(
        self,
        city: str,
        state: str,
        max_listings: int,
        **kwargs
    ) -> Dict[str, Any]:
        """Build Realtor.com actor input for rentals."""
        return {
            "search": f"{city}, {state}",
            "mode": "RENT",  # Important: RENT mode for rentals
            "maxItems": max_listings,
            "proxy": {
                "useApifyProxy": True
            }
        }

    def _build_rent_com_input(
        self,
        city: str,
        state: str,
        max_listings: int,
        **kwargs
    ) -> Dict[str, Any]:
        """Build Rent.com actor input."""
        # Build Rent.com search URL
        city_slug = city.lower().replace(" ", "-")
        state_slug = state.lower()
        search_url = f"https://www.rent.com/pennsylvania/{city_slug}/apartments"

        return {
            "startUrls": [search_url],
            "maxResults": max_listings,
        }

    async def _run_actor(self, actor_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Run an Apify actor and wait for completion.

        Args:
            actor_input: Input parameters for the actor

        Returns:
            Run result dict or None if failed
        """
        try:
            # Start the actor run
            url = f"{self.API_BASE_URL}/acts/{self.actor_id}/runs"
            response = await self.client.post(url, json=actor_input)
            response.raise_for_status()

            run_data = response.json().get("data", {})
            run_id = run_data.get("id")

            if not run_id:
                logger.error("No run ID returned from Apify")
                return None

            # Wait for the run to complete
            return await self._wait_for_run(run_id)

        except Exception as e:
            logger.exception(f"Error running Apify actor: {e}")
            return None

    async def _wait_for_run(self, run_id: str, max_wait_seconds: int = 5400) -> Optional[Dict[str, Any]]:
        """
        Wait for an actor run to complete.

        Args:
            run_id: Apify run ID
            max_wait_seconds: Maximum time to wait (default 90 minutes —
                hot market scrapes can take 30-60 minutes on Apify)

        Returns:
            Run result or None
        """
        import asyncio

        url = f"{self.API_BASE_URL}/actor-runs/{run_id}"
        start_time = datetime.utcnow()
        poll_interval = 30  # 30s between polls — runs take 20-60 min

        while True:
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            if elapsed > max_wait_seconds:
                logger.warning(f"Apify run {run_id} timed out after {max_wait_seconds}s")
                return None

            try:
                response = await self.client.get(url)
                response.raise_for_status()
                data = response.json().get("data", {})
                status = data.get("status")

                if status == "SUCCEEDED":
                    logger.info(f"Run {run_id} SUCCEEDED after {int(elapsed)}s. defaultDatasetId={data.get('defaultDatasetId')}")
                    return data
                elif status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                    logger.error(f"Apify run {run_id} ended with status: {status}")
                    return None

                # Log progress
                stats = data.get("stats", {})
                dataset_items = stats.get("datasetItems", 0)
                run_time = stats.get("runTimeSecs", 0)
                logger.info(
                    f"Run {run_id}: status={status} | "
                    f"{dataset_items} items collected | "
                    f"{int(run_time)}s elapsed on Apify"
                )

                # Wait before polling again
                await asyncio.sleep(poll_interval)

            except Exception as e:
                logger.warning(f"Error checking Apify run status (will retry): {e}")
                await asyncio.sleep(poll_interval)

    async def _get_dataset_items(self, dataset_id: str, max_items: int) -> List[Dict[str, Any]]:
        """
        Get items from an Apify dataset.

        Args:
            dataset_id: Dataset ID
            max_items: Maximum items to retrieve

        Returns:
            List of dataset items
        """
        try:
            url = f"{self.API_BASE_URL}/datasets/{dataset_id}/items"
            params = {"limit": max_items}

            logger.info(f"Fetching dataset items: GET {url} params={params}")
            response = await self.client.get(url, params=params)
            logger.info(f"Dataset response: status={response.status_code}, content_length={len(response.content)}")
            response.raise_for_status()

            items = response.json()
            logger.info(f"Parsed {len(items)} items from dataset {dataset_id}")
            return items

        except Exception as e:
            logger.exception(f"Error getting Apify dataset {dataset_id}: {e}")
            return []

    def _normalize_listing(self, raw_data: Dict[str, Any]) -> Optional[ScrapedListing]:
        """
        Convert Apify actor output to normalized ScrapedListing.

        Args:
            raw_data: Raw data from Apify

        Returns:
            ScrapedListing or None if invalid
        """
        try:
            if self.source_id == "zillow":
                return self._normalize_zillow_listing(raw_data)
            elif self.source_id == "apartments_com":
                return self._normalize_apartments_com_listing(raw_data)
            elif self.source_id == "realtor":
                return self._normalize_realtor_listing(raw_data)
            elif self.source_id == "rent_com":
                return self._normalize_rent_com_listing(raw_data)
            else:
                return self._normalize_apartments_com_listing(raw_data)
        except Exception as e:
            logger.warning(f"Failed to normalize listing: {e}")
            return None

    def _normalize_zillow_listing(self, raw: Dict[str, Any]) -> Optional[ScrapedListing]:
        """Normalize Zillow listing data."""
        # Extract required fields
        address = raw.get("address") or raw.get("streetAddress", "")
        if not address:
            return None

        rent = self._parse_rent(raw.get("price") or raw.get("rentZestimate"))
        if not rent:
            return None

        # Build full address
        city = raw.get("city", "")
        state = raw.get("state", "")
        zip_code = raw.get("zipcode", "")

        if city and state and zip_code and city not in address:
            address = f"{address}, {city}, {state} {zip_code}"

        return ScrapedListing(
            external_id=str(raw.get("zpid") or raw.get("id", "")),
            source="zillow",
            address=address,
            rent=rent,
            bedrooms=self._parse_bedrooms(raw.get("bedrooms")),
            bathrooms=self._parse_bathrooms(raw.get("bathrooms")),
            property_type=self._normalize_property_type(raw.get("homeType", "")),
            city=city,
            state=state,
            zip_code=zip_code,
            neighborhood=raw.get("neighborhood", ""),
            latitude=raw.get("latitude"),
            longitude=raw.get("longitude"),
            sqft=raw.get("livingArea") or raw.get("sqft"),
            available_date=raw.get("dateAvailable"),
            description=raw.get("description", ""),
            amenities=self._normalize_amenities(raw.get("amenities", [])),
            images=raw.get("photos", []) or raw.get("images", []),
            source_url=raw.get("url") or raw.get("detailUrl"),
            raw_data=raw,
        )

    def _normalize_apartments_com_listing(self, raw: Dict[str, Any]) -> Optional[ScrapedListing]:
        """Normalize Apartments.com listing data from apartments-scraper-api."""
        # Handle nested location object
        location = raw.get("location", {})
        address = location.get("fullAddress") or location.get("streetAddress") or raw.get("address", "")
        if not address:
            return None

        # Handle rent object with min/max
        rent_data = raw.get("rent", {})
        if isinstance(rent_data, dict):
            # Use min rent as the primary rent value
            rent = rent_data.get("min") or rent_data.get("max")
        else:
            rent = self._parse_rent(rent_data)

        if not rent:
            return None

        # Extract location fields
        city = location.get("city", "") or raw.get("city", "")
        state = location.get("state", "") or raw.get("state", "")
        zip_code = location.get("postalCode", "") or raw.get("zipCode", "")
        neighborhood = location.get("neighborhood", "") or raw.get("neighborhood", "")

        # Handle coordinates
        coords = raw.get("coordinates", {})
        latitude = coords.get("latitude") or raw.get("latitude")
        longitude = coords.get("longitude") or raw.get("longitude")

        # Parse beds from string like "Studio - 2 bd" or "1 bd"
        beds_str = raw.get("beds", "")
        bedrooms = self._parse_bedrooms(beds_str)

        # Parse baths from string like "1 ba" or "1 - 2 ba"
        baths_str = raw.get("baths", "")
        bathrooms = self._parse_bathrooms(baths_str)

        # Parse sqft from string like "433 - 533 sq ft"
        sqft_str = raw.get("sqft", "")
        sqft = None
        if sqft_str:
            import re
            sqft_match = re.search(r"(\d+(?:,\d+)?)", sqft_str.replace(",", ""))
            if sqft_match:
                sqft = int(sqft_match.group(1))

        # Extract photo URLs
        photos = raw.get("photos", [])
        if photos and isinstance(photos[0], dict):
            photos = [p.get("url") or p.get("src") for p in photos if p.get("url") or p.get("src")]

        # Extract amenities from nested format: [{title: "Category", value: ["item1", "item2"]}]
        amenities_raw = raw.get("amenities", [])
        amenities = []
        if amenities_raw and isinstance(amenities_raw, list):
            for cat in amenities_raw:
                if isinstance(cat, dict):
                    # Handle {title: "Category", value: ["item1", "item2"]} format
                    values = cat.get("value", []) or cat.get("items", [])
                    if isinstance(values, list):
                        amenities.extend(values)
                elif isinstance(cat, str):
                    amenities.append(cat)

        return ScrapedListing(
            external_id=str(raw.get("id", "")),
            source="apartments_com",
            address=address,
            rent=rent,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            property_type="Apartment",
            city=city,
            state=state,
            zip_code=zip_code,
            neighborhood=neighborhood,
            latitude=latitude,
            longitude=longitude,
            sqft=sqft,
            available_date=None,
            description=raw.get("description", "") or raw.get("propertyName", ""),
            amenities=self._normalize_amenities(amenities),
            images=photos,
            source_url=raw.get("url"),
            raw_data=raw,
        )

    def _normalize_realtor_listing(self, raw: Dict[str, Any]) -> Optional[ScrapedListing]:
        """Normalize Realtor.com listing data."""
        address = raw.get("address") or raw.get("streetAddress") or raw.get("location", {}).get("address", "")
        if not address:
            return None

        # Realtor.com may have rent in various formats
        rent = self._parse_rent(
            raw.get("price") or raw.get("rent") or raw.get("listPrice")
        )
        if not rent:
            return None

        # Location info may be nested
        location = raw.get("location", {})
        city = raw.get("city") or location.get("city", "")
        state = raw.get("state") or location.get("state", "")
        zip_code = raw.get("zipCode") or raw.get("zip") or location.get("zipCode", "")

        return ScrapedListing(
            external_id=str(raw.get("propertyId") or raw.get("id", "")),
            source="realtor",
            address=address,
            rent=rent,
            bedrooms=self._parse_bedrooms(raw.get("beds") or raw.get("bedrooms")),
            bathrooms=self._parse_bathrooms(raw.get("baths") or raw.get("bathrooms")),
            property_type=self._normalize_property_type(raw.get("propertyType", "Apartment")),
            city=city,
            state=state,
            zip_code=zip_code,
            neighborhood=raw.get("neighborhood", ""),
            latitude=raw.get("latitude") or location.get("lat"),
            longitude=raw.get("longitude") or location.get("lon"),
            sqft=raw.get("sqft") or raw.get("livingArea"),
            available_date=raw.get("availableDate"),
            description=raw.get("description", ""),
            amenities=self._normalize_amenities(raw.get("amenities", [])),
            images=raw.get("photos", []) or raw.get("images", []),
            source_url=raw.get("url") or raw.get("detailUrl"),
            raw_data=raw,
        )

    def _normalize_rent_com_listing(self, raw: Dict[str, Any]) -> Optional[ScrapedListing]:
        """Normalize Rent.com listing data."""
        address = raw.get("address") or raw.get("streetAddress") or raw.get("name", "")
        if not address:
            return None

        rent = self._parse_rent(raw.get("rent") or raw.get("price") or raw.get("rentPrice"))
        if not rent:
            return None

        city = raw.get("city", "")
        state = raw.get("state", "")
        zip_code = raw.get("zipCode") or raw.get("zip", "")

        return ScrapedListing(
            external_id=str(raw.get("id") or raw.get("listingId", "")),
            source="rent_com",
            address=address,
            rent=rent,
            bedrooms=self._parse_bedrooms(raw.get("beds") or raw.get("bedrooms")),
            bathrooms=self._parse_bathrooms(raw.get("baths") or raw.get("bathrooms")),
            property_type=self._normalize_property_type(raw.get("propertyType", "Apartment")),
            city=city,
            state=state,
            zip_code=zip_code,
            neighborhood=raw.get("neighborhood", ""),
            latitude=raw.get("latitude"),
            longitude=raw.get("longitude"),
            sqft=raw.get("sqft"),
            available_date=raw.get("availableDate"),
            description=raw.get("description", ""),
            amenities=self._normalize_amenities(raw.get("amenities", [])),
            images=raw.get("photos", []) or raw.get("images", []),
            source_url=raw.get("url"),
            raw_data=raw,
        )

    def _estimate_cost(self, listing_count: int) -> int:
        """
        Estimate the cost of a scrape in cents.

        Apify pricing is roughly $0.25-0.50 per 1000 results for residential proxies.
        """
        # Estimate: ~$0.001 per listing
        return max(1, listing_count // 10)

    async def health_check(self) -> Dict[str, Any]:
        """Check if Apify API is accessible."""
        if not self.api_token:
            return {
                "source_id": self.source_id,
                "healthy": False,
                "message": "APIFY_API_TOKEN not configured",
            }

        try:
            url = f"{self.API_BASE_URL}/acts/{self.actor_id}"
            response = await self.client.get(url)

            if response.status_code == 200:
                return {
                    "source_id": self.source_id,
                    "healthy": True,
                    "message": "Apify API accessible",
                    "actor_id": self.actor_id,
                }
            else:
                return {
                    "source_id": self.source_id,
                    "healthy": False,
                    "message": f"Apify API returned status {response.status_code}",
                }

        except Exception as e:
            return {
                "source_id": self.source_id,
                "healthy": False,
                "message": str(e),
            }

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            try:
                await self._client.aclose()
            except RuntimeError:
                # Event loop may already be closed in sync context
                pass
            self._client = None
