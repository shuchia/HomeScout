"""
ScrapingBee API integration for scraping Craigslist and local rental sites.
Uses JavaScript rendering for dynamic content and built-in anti-blocking.
"""
import os
import logging
import re
from typing import Dict, Any, Optional, List
from datetime import datetime
from urllib.parse import urlencode, quote

import httpx
from bs4 import BeautifulSoup

from app.services.scrapers.base_scraper import (
    BaseScraper,
    ScrapedListing,
    ScrapeResult,
    ScraperStatus,
)

logger = logging.getLogger(__name__)


class ScrapingBeeService(BaseScraper):
    """
    Scraper service using ScrapingBee for Craigslist and local rental sites.

    ScrapingBee provides:
    - JavaScript rendering
    - Rotating proxies
    - CAPTCHA solving
    - Anti-bot bypass
    """

    API_BASE_URL = "https://app.scrapingbee.com/api/v1/"

    # Craigslist city subdomain mapping
    CRAIGSLIST_CITIES = {
        "San Francisco": "sfbay",
        "New York": "newyork",
        "Los Angeles": "losangeles",
        "Austin": "austin",
        "Denver": "denver",
        "Seattle": "seattle",
        "Portland": "portland",
        "Chicago": "chicago",
        "Boston": "boston",
        "Miami": "miami",
        # Pennsylvania - Bryn Mawr area uses Philadelphia subdomain
        "Bryn Mawr": "philadelphia",
        "Ardmore": "philadelphia",
        "Haverford": "philadelphia",
        "Wayne": "philadelphia",
        "Philadelphia": "philadelphia",
    }

    def __init__(self, source_id: str = "craigslist"):
        """
        Initialize the ScrapingBee scraper.

        Args:
            source_id: Which platform to scrape (craigslist, etc.)
        """
        super().__init__(source_id)
        self.api_key = os.getenv("SCRAPINGBEE_API_KEY")

        if not self.api_key:
            logger.warning("SCRAPINGBEE_API_KEY not set - ScrapingBee scraping will be disabled")

        self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-load HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0)
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
        Scrape rental listings using ScrapingBee.

        Args:
            city: City name (e.g., "San Francisco")
            state: State code (e.g., "CA")
            max_listings: Maximum listings to return
            **kwargs: Additional parameters

        Returns:
            ScrapeResult with normalized listings
        """
        result = ScrapeResult(
            status=ScraperStatus.PENDING,
            started_at=datetime.utcnow()
        )

        if not self.api_key:
            result.status = ScraperStatus.FAILED
            result.errors.append("SCRAPINGBEE_API_KEY not configured")
            result.completed_at = datetime.utcnow()
            return result

        try:
            result.status = ScraperStatus.RUNNING

            if self.source_id == "craigslist":
                listings = await self._scrape_craigslist(city, state, max_listings, **kwargs)
            else:
                listings = await self._scrape_generic(city, state, max_listings, **kwargs)

            result.listings = listings
            result.total_found = len(listings)
            result.status = ScraperStatus.COMPLETED

            # ScrapingBee costs ~$0.001-0.005 per request depending on plan
            result.estimated_cost_cents = result.api_calls_made * 1

        except Exception as e:
            logger.exception(f"Error during ScrapingBee scrape: {e}")
            result.status = ScraperStatus.FAILED
            result.errors.append(str(e))

        result.completed_at = datetime.utcnow()
        return result

    async def _scrape_craigslist(
        self,
        city: str,
        state: str,
        max_listings: int,
        **kwargs
    ) -> List[ScrapedListing]:
        """
        Scrape Craigslist apartment listings.

        Args:
            city: City name
            state: State code
            max_listings: Max results

        Returns:
            List of ScrapedListing objects
        """
        listings = []

        # Get Craigslist subdomain for city
        subdomain = self.CRAIGSLIST_CITIES.get(city, city.lower().replace(" ", ""))

        # Build search URL
        min_price = kwargs.get("min_price", 500)
        max_price = kwargs.get("max_price", 10000)
        bedrooms = kwargs.get("bedrooms")

        search_url = f"https://{subdomain}.craigslist.org/search/apa"
        params = {
            "min_price": min_price,
            "max_price": max_price,
            "availabilityMode": 0,  # All dates
        }

        if bedrooms:
            params["min_bedrooms"] = bedrooms
            params["max_bedrooms"] = bedrooms

        full_url = f"{search_url}?{urlencode(params)}"

        # Fetch search results page
        html = await self._fetch_page(full_url)
        if not html:
            return listings

        # Parse search results
        soup = BeautifulSoup(html, "html.parser")
        result_rows = soup.select(".cl-search-result, .result-row, li.cl-static-search-result")

        logger.info(f"Found {len(result_rows)} Craigslist results")

        # Process each listing (up to max)
        for row in result_rows[:max_listings]:
            try:
                listing = self._parse_craigslist_row(row, subdomain, city, state)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.warning(f"Failed to parse Craigslist row: {e}")
                continue

        return listings

    def _parse_craigslist_row(
        self,
        row: BeautifulSoup,
        subdomain: str,
        city: str,
        state: str
    ) -> Optional[ScrapedListing]:
        """Parse a Craigslist search result row."""
        # Get listing URL - new layout uses direct <a> tag
        link = row.select_one("a")
        if not link:
            return None

        listing_url = link.get("href", "")
        if not listing_url.startswith("http"):
            listing_url = f"https://{subdomain}.craigslist.org{listing_url}"

        # Get title - new layout uses div.title
        title_elem = row.select_one("div.title, .titlestring, a.result-title")
        title = title_elem.get_text(strip=True) if title_elem else row.get("title", "")

        if not title:
            return None

        # Get price - new layout uses div.price
        price_elem = row.select_one("div.price, .priceinfo, .result-price")
        rent = self._parse_rent(price_elem.get_text() if price_elem else "0")
        if not rent or rent < 100:  # Filter out likely invalid prices
            return None

        # Get location
        location_elem = row.select_one("div.location, .result-hood")
        neighborhood = location_elem.get_text(strip=True) if location_elem else ""

        # Get housing info from title (beds/baths/sqft often in title)
        bedrooms = 1
        bathrooms = 1.0
        sqft = None

        # Parse from title: "2br - 800ft²" or "2BR/1BA"
        title_lower = title.lower()
        br_match = re.search(r"(\d+)\s*br", title_lower)
        if br_match:
            bedrooms = int(br_match.group(1))

        ba_match = re.search(r"(\d+\.?\d*)\s*ba", title_lower)
        if ba_match:
            bathrooms = float(ba_match.group(1))

        sqft_match = re.search(r"(\d+)\s*(?:ft|sq)", title_lower)
        if sqft_match:
            sqft = int(sqft_match.group(1))

        # Get post ID from URL
        post_id = ""
        id_match = re.search(r"/(\d+)\.html", listing_url)
        if id_match:
            post_id = id_match.group(1)

        return ScrapedListing(
            external_id=post_id or listing_url,
            source="craigslist",
            address=f"{title}, {city}, {state}" if city.lower() not in title.lower() else title,
            rent=rent,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            property_type="Apartment",
            city=city,
            state=state,
            neighborhood=neighborhood,
            sqft=sqft,
            source_url=listing_url,
            description=title,
            raw_data={"title": title, "url": listing_url},
        )

    async def _scrape_generic(
        self,
        city: str,
        state: str,
        max_listings: int,
        **kwargs
    ) -> List[ScrapedListing]:
        """Placeholder for generic site scraping."""
        logger.warning(f"Generic scraping not implemented for source: {self.source_id}")
        return []

    async def _fetch_page(self, url: str, render_js: bool = True) -> Optional[str]:
        """
        Fetch a page using ScrapingBee API.

        Args:
            url: URL to fetch
            render_js: Whether to render JavaScript

        Returns:
            HTML content or None
        """
        try:
            params = {
                "api_key": self.api_key,
                "url": url,
                "render_js": str(render_js).lower(),
                "premium_proxy": "true",  # Better for Craigslist
                "country_code": "us",
            }

            response = await self.client.get(
                self.API_BASE_URL,
                params=params
            )

            if response.status_code == 200:
                return response.text
            else:
                logger.error(f"ScrapingBee returned status {response.status_code}: {response.text[:200]}")
                return None

        except Exception as e:
            logger.exception(f"Error fetching page via ScrapingBee: {e}")
            return None

    def _normalize_listing(self, raw_data: Dict[str, Any]) -> Optional[ScrapedListing]:
        """
        Convert raw scraped data to ScrapedListing.
        This is used when processing already-fetched data.
        """
        try:
            return ScrapedListing(
                external_id=str(raw_data.get("id", "")),
                source=self.source_id,
                address=raw_data.get("address", ""),
                rent=self._parse_rent(raw_data.get("rent")),
                bedrooms=self._parse_bedrooms(raw_data.get("bedrooms")),
                bathrooms=self._parse_bathrooms(raw_data.get("bathrooms")),
                property_type=self._normalize_property_type(raw_data.get("property_type", "")),
                city=raw_data.get("city"),
                state=raw_data.get("state"),
                zip_code=raw_data.get("zip_code"),
                neighborhood=raw_data.get("neighborhood"),
                sqft=raw_data.get("sqft"),
                available_date=raw_data.get("available_date"),
                description=raw_data.get("description"),
                amenities=self._normalize_amenities(raw_data.get("amenities", [])),
                images=raw_data.get("images", []),
                source_url=raw_data.get("url"),
                raw_data=raw_data,
            )
        except Exception as e:
            logger.warning(f"Failed to normalize listing: {e}")
            return None

    async def health_check(self) -> Dict[str, Any]:
        """Check if ScrapingBee API is accessible."""
        if not self.api_key:
            return {
                "source_id": self.source_id,
                "healthy": False,
                "message": "SCRAPINGBEE_API_KEY not configured",
            }

        try:
            # Use a simple test URL
            params = {
                "api_key": self.api_key,
                "url": "https://httpbin.org/ip",
            }

            response = await self.client.get(self.API_BASE_URL, params=params)

            if response.status_code == 200:
                return {
                    "source_id": self.source_id,
                    "healthy": True,
                    "message": "ScrapingBee API accessible",
                }
            else:
                return {
                    "source_id": self.source_id,
                    "healthy": False,
                    "message": f"ScrapingBee API returned status {response.status_code}",
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
