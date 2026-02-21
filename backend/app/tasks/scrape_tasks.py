"""
Celery tasks for apartment listing scraping.
"""
import asyncio
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from app.celery_app import celery_app
from app.database import get_session_context, is_database_enabled
from app.services.scrapers.apify_service import ApifyService
from app.services.scrapers.scrapingbee_service import ScrapingBeeService
from app.services.normalization.normalizer import NormalizationService
from app.services.deduplication.deduplicator import DeduplicationService

logger = logging.getLogger(__name__)

# Default cities to scrape (MVP - 3 cities)
DEFAULT_CITIES = [
    ("Philadelphia", "PA"),
    ("Bryn Mawr", "PA"),
    ("Pittsburgh", "PA"),
]


def run_async(coro):
    """Run an async coroutine in a sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3)
def scrape_source(
    self,
    source: str,
    cities: Optional[List[str]] = None,
    state: Optional[str] = None,
    max_listings_per_city: int = 100,
    **kwargs
) -> Dict[str, Any]:
    """
    Scrape a data source for apartment listings.

    Args:
        source: Source identifier (zillow, apartments_com, craigslist, realtor, rent_com)
        cities: List of city names to scrape
        state: State code (e.g., "PA") - used for all cities if provided
        max_listings_per_city: Maximum listings per city

    Returns:
        Dict with scrape results summary
    """
    job_id = str(uuid.uuid4())
    logger.info(f"Starting scrape job {job_id} for source: {source}")

    # Default cities if not specified
    if not cities:
        cities = [city for city, _ in DEFAULT_CITIES]

    # Initialize services
    normalizer = NormalizationService()
    deduplicator = DeduplicationService()

    # Select scraper based on source
    if source in ["zillow", "apartments_com", "realtor", "rent_com"]:
        scraper = ApifyService(source)
    elif source == "craigslist":
        scraper = ScrapingBeeService(source)
    else:
        logger.error(f"Unknown source: {source}")
        return {"status": "failed", "error": f"Unknown source: {source}"}

    results = {
        "job_id": job_id,
        "source": source,
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
        "cities": [],
        "total_found": 0,
        "total_new": 0,
        "total_duplicates": 0,
        "total_errors": 0,
    }

    try:
        for city in cities:
            # Use provided state, or look up from DEFAULT_CITIES, or default to PA
            city_state = state
            if not city_state:
                for c, s in DEFAULT_CITIES:
                    if c == city:
                        city_state = s
                        break
                if not city_state:
                    city_state = "PA"  # Default for Bryn Mawr area

            city_result = run_async(_scrape_city(
                scraper=scraper,
                source=source,
                city=city,
                state=city_state,
                max_listings=max_listings_per_city,
                normalizer=normalizer,
                deduplicator=deduplicator,
                job_id=job_id,
            ))

            results["cities"].append(city_result)
            results["total_found"] += city_result.get("found", 0)
            results["total_new"] += city_result.get("new", 0)
            results["total_duplicates"] += city_result.get("duplicates", 0)
            results["total_errors"] += city_result.get("errors", 0)

        results["status"] = "completed"

    except Exception as e:
        logger.exception(f"Scrape job {job_id} failed: {e}")
        results["status"] = "failed"
        results["error"] = str(e)

        # Retry on transient errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))

    finally:
        results["completed_at"] = datetime.utcnow().isoformat()
        # Clean up scraper
        run_async(scraper.close())

    logger.info(
        f"Scrape job {job_id} completed: "
        f"{results['total_found']} found, {results['total_new']} new, "
        f"{results['total_duplicates']} duplicates"
    )

    return results


async def _scrape_city(
    scraper,
    source: str,
    city: str,
    state: str,
    max_listings: int,
    normalizer: NormalizationService,
    deduplicator: DeduplicationService,
    job_id: str,
) -> Dict[str, Any]:
    """
    Scrape listings for a single city.

    Args:
        scraper: Scraper service instance
        source: Source identifier
        city: City name
        state: State code
        max_listings: Maximum listings to scrape
        normalizer: Normalization service
        deduplicator: Deduplication service
        job_id: Parent job ID

    Returns:
        Dict with city scrape results
    """
    logger.info(f"Scraping {city}, {state} from {source}")

    result = {
        "city": city,
        "state": state,
        "found": 0,
        "new": 0,
        "duplicates": 0,
        "errors": 0,
    }

    try:
        # Scrape listings
        scrape_result = await scraper.scrape(
            city=city,
            state=state,
            max_listings=max_listings,
        )

        result["found"] = len(scrape_result.listings)

        # Normalize listings
        normalized = []
        for listing in scrape_result.listings:
            norm_result = normalizer.normalize(listing)
            if norm_result.success:
                norm_result.listing["id"] = str(uuid.uuid4())
                norm_result.listing["data_quality_score"] = norm_result.quality_score
                normalized.append(norm_result.listing)
            else:
                result["errors"] += 1
                logger.warning(f"Normalization failed: {norm_result.errors}")

        # Deduplicate
        if normalized:
            # Get existing hashes from database if enabled
            existing_hashes = {}
            existing_listings = []

            if is_database_enabled():
                existing_hashes, existing_listings = await _get_existing_data(city)

            unique, duplicates, _ = deduplicator.deduplicate_batch(
                normalized, existing_hashes, existing_listings
            )

            result["new"] = len(unique)
            result["duplicates"] = len(duplicates)

            # Save to database
            if is_database_enabled() and unique:
                await _save_listings(unique, job_id)

    except Exception as e:
        logger.exception(f"Error scraping {city}: {e}")
        result["errors"] += 1

    return result


async def _get_existing_data(city: str):
    """Get existing hashes and listings for deduplication."""
    from sqlalchemy import select
    from app.models.apartment import ApartmentModel

    existing_hashes = {}
    existing_listings = []

    try:
        async with get_session_context() as session:
            # Get content hashes
            stmt = select(ApartmentModel.content_hash, ApartmentModel.id).where(
                ApartmentModel.city.ilike(f"%{city}%"),
                ApartmentModel.is_active == 1,
            )
            result = await session.execute(stmt)
            for row in result:
                if row.content_hash:
                    existing_hashes[row.content_hash] = row.id

            # Get recent listings for fuzzy matching (limit to recent)
            stmt = select(ApartmentModel).where(
                ApartmentModel.city.ilike(f"%{city}%"),
                ApartmentModel.is_active == 1,
            ).limit(1000)
            result = await session.execute(stmt)
            for row in result.scalars():
                existing_listings.append(row.to_dict())

    except Exception as e:
        logger.warning(f"Could not get existing data: {e}")

    return existing_hashes, existing_listings


async def _save_listings(listings: List[Dict[str, Any]], job_id: str):
    """Save listings to database."""
    from app.models.apartment import ApartmentModel

    try:
        async with get_session_context() as session:
            for listing_data in listings:
                apartment = ApartmentModel(
                    id=listing_data["id"],
                    external_id=listing_data.get("external_id"),
                    source=listing_data.get("source", "manual"),
                    source_url=listing_data.get("source_url"),
                    address=listing_data["address"],
                    address_normalized=listing_data.get("address_normalized"),
                    city=listing_data.get("city"),
                    state=listing_data.get("state"),
                    zip_code=listing_data.get("zip_code"),
                    neighborhood=listing_data.get("neighborhood"),
                    latitude=listing_data.get("latitude"),
                    longitude=listing_data.get("longitude"),
                    rent=listing_data["rent"],
                    bedrooms=listing_data["bedrooms"],
                    bathrooms=listing_data["bathrooms"],
                    sqft=listing_data.get("sqft"),
                    property_type=listing_data["property_type"],
                    available_date=listing_data.get("available_date"),
                    description=listing_data.get("description"),
                    amenities=listing_data.get("amenities", []),
                    images=listing_data.get("images", []),
                    content_hash=listing_data.get("content_hash"),
                    data_quality_score=listing_data.get("data_quality_score", 50),
                    raw_data=listing_data.get("raw_data"),
                )
                session.add(apartment)

            await session.commit()
            logger.info(f"Saved {len(listings)} listings to database")

    except Exception as e:
        logger.exception(f"Error saving listings: {e}")
        raise


@celery_app.task(bind=True, max_retries=3)
def scrape_city_task(self, market_id: str) -> Dict[str, Any]:
    """
    Scrape a single market. Called by the dispatcher.
    """
    logger.info(f"Starting scrape for market: {market_id}")
    return run_async(_scrape_market(self, market_id))


async def _scrape_market(task, market_id: str) -> Dict[str, Any]:
    """Async implementation of market scraping."""
    from sqlalchemy import select, update
    from app.models.market_config import MarketConfigModel
    from app.models.scrape_job import ScrapeJobModel

    # Load market config
    async with get_session_context() as session:
        result = await session.execute(
            select(MarketConfigModel).where(MarketConfigModel.id == market_id)
        )
        market = result.scalar_one_or_none()
        if not market:
            return {"status": "failed", "error": f"Market {market_id} not found"}

        city = market.city
        state = market.state
        max_listings = market.max_listings_per_scrape

    # Create scrape job record
    job_id = str(uuid.uuid4())
    async with get_session_context() as session:
        job = ScrapeJobModel(
            id=job_id,
            source="apartments_com",
            job_type="scheduled",
            status="running",
            city=city,
            state=state,
            started_at=datetime.utcnow(),
        )
        session.add(job)
        await session.commit()

    # Check rate limits
    from app.models.data_source import DataSourceModel
    async with get_session_context() as session:
        ds_result = await session.execute(
            select(DataSourceModel).where(DataSourceModel.name == "apartments_com")
        )
        data_source = ds_result.scalar_one_or_none()
        if data_source and not data_source.can_make_request():
            logger.warning(f"Rate limit exceeded for apartments_com, skipping {market_id}")
            await _update_job(job_id, "failed", error="Rate limit exceeded")
            return {"status": "skipped", "reason": "rate_limit"}

    # Run the scrape
    normalizer = NormalizationService()
    deduplicator = DeduplicationService()
    scraper = ApifyService("apartments_com")

    try:
        scrape_result = await scraper.scrape(
            city=city, state=state, max_listings=max_listings
        )

        found = len(scrape_result.listings)

        # Normalize
        normalized = []
        errors = 0
        for listing in scrape_result.listings:
            norm_result = normalizer.normalize(listing)
            if norm_result.success:
                norm_result.listing["id"] = str(uuid.uuid4())
                norm_result.listing["data_quality_score"] = norm_result.quality_score
                norm_result.listing["market_id"] = market_id
                normalized.append(norm_result.listing)
            else:
                errors += 1
                logger.warning(f"Normalization failed: {norm_result.errors}")

        # Deduplicate with re-see updates
        new_count = 0
        updated_count = 0
        dup_count = 0

        if normalized:
            existing_hashes, existing_listings = await _get_existing_data(city)

            new_listings, updates, dups = deduplicator.deduplicate_batch_with_updates(
                normalized, existing_hashes, existing_listings
            )

            new_count = len(new_listings)
            updated_count = len(updates)
            dup_count = len(dups)

            # Save new listings
            if new_listings:
                await _save_listings(new_listings, job_id)

            # Update re-seen listings (confidence reset)
            if updates:
                await _update_reseen_listings(updates)

        # Update job and market
        await _update_job(job_id, "completed",
            listings_found=found, listings_new=new_count,
            listings_updated=updated_count, listings_duplicates=dup_count,
            listings_errors=errors)

        await _update_market_after_scrape(market_id, "completed")

        result = {
            "status": "completed",
            "market_id": market_id,
            "city": city,
            "found": found,
            "new": new_count,
            "updated": updated_count,
            "duplicates": dup_count,
            "errors": errors,
        }
        logger.info(f"Scrape {market_id}: {result}")
        return result

    except Exception as e:
        logger.exception(f"Scrape failed for {market_id}: {e}")
        await _update_job(job_id, "failed", error=str(e))
        await _update_market_after_scrape(market_id, "failed")

        if task.request.retries < task.max_retries:
            raise task.retry(exc=e, countdown=60 * (task.request.retries + 1))

        return {"status": "failed", "market_id": market_id, "error": str(e)}

    finally:
        await scraper.close()


async def _update_job(job_id: str, status: str, **metrics):
    """Update a scrape job record."""
    from sqlalchemy import update
    from app.models.scrape_job import ScrapeJobModel

    values = {"status": status, "completed_at": datetime.utcnow()}
    values.update(metrics)

    async with get_session_context() as session:
        await session.execute(
            update(ScrapeJobModel).where(ScrapeJobModel.id == job_id).values(**values)
        )
        await session.commit()


async def _update_market_after_scrape(market_id: str, status: str):
    """Update market config after a scrape completes or fails."""
    from sqlalchemy import update
    from app.models.market_config import MarketConfigModel

    values = {
        "last_scrape_at": datetime.now(timezone.utc) if hasattr(datetime, 'now') else datetime.utcnow(),
        "last_scrape_status": status,
    }

    if status == "completed":
        values["consecutive_failures"] = 0
    else:
        from sqlalchemy import text
        async with get_session_context() as session:
            await session.execute(
                update(MarketConfigModel)
                .where(MarketConfigModel.id == market_id)
                .values(
                    last_scrape_at=datetime.utcnow(),
                    last_scrape_status=status,
                    consecutive_failures=MarketConfigModel.consecutive_failures + 1,
                )
            )
            await session.commit()
            return

    async with get_session_context() as session:
        await session.execute(
            update(MarketConfigModel).where(MarketConfigModel.id == market_id).values(**values)
        )
        await session.commit()


async def _update_reseen_listings(updates: List[Dict[str, Any]]):
    """Update existing listings that were re-seen in a scrape."""
    from sqlalchemy import update
    from app.models.apartment import ApartmentModel

    async with get_session_context() as session:
        for upd in updates:
            values = {
                "last_seen_at": datetime.utcnow(),
                "freshness_confidence": 100,
                "times_seen": ApartmentModel.times_seen + 1,
            }
            # Merge richer data if available
            if upd.get("images"):
                values["images"] = upd["images"]
            if upd.get("description") and len(upd.get("description", "")) > 100:
                values["description"] = upd["description"]

            await session.execute(
                update(ApartmentModel)
                .where(ApartmentModel.id == upd["matched_id"])
                .values(**values)
            )
        await session.commit()
        logger.info(f"Updated {len(updates)} re-seen listings")
