"""
Service for managing apartment search and matching.
Supports both database (PostgreSQL) and JSON file fallback.
"""
import hashlib
import json
import os
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from pathlib import Path

from app.services.claude_service import ClaudeService
from app.database import is_database_enabled, get_session_context

logger = logging.getLogger(__name__)

# Limit concurrent Claude API calls to prevent runaway costs
_claude_semaphore = asyncio.Semaphore(5)

# Phase 2 of docs/floorplan-search-design.md. When enabled, DB search joins
# apartment_floorplans and matches per-floorplan bucket (so larger units in
# mixed buildings become searchable), projecting the matched floorplan onto each
# result. Default off — the building-level query is unchanged until buckets are
# backfilled and this is flipped per-env.
USE_FLOORPLAN_SEARCH = os.getenv("USE_FLOORPLAN_SEARCH", "false").lower() == "true"


class ApartmentService:
    """Service for managing apartment search and matching"""

    def __init__(self):
        self.claude_service = ClaudeService()
        self._apartments_data: Optional[List[Dict]] = None
        self._use_database = is_database_enabled()

        # Async Redis client for Claude score caching
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(redis_url)
        except Exception:
            self._redis = None

        if not self._use_database:
            logger.info("Database not enabled, using JSON fallback")
            self._apartments_data = self._load_apartments_from_json()

    @staticmethod
    def build_score_cache_key(
        city: str, budget: int, bedrooms: int, bathrooms: float,
        property_type: str, move_in_date: str,
        other_preferences: str, apartment_ids: list[str],
        near_label: str = None,
    ) -> str:
        """Build deterministic Redis key for Claude score cache."""
        raw = f"{city}|{budget}|{bedrooms}|{bathrooms}|{property_type}|{move_in_date}|{other_preferences}|{','.join(sorted(apartment_ids))}|{near_label or ''}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"claude_score:{digest}"

    def _load_apartments_from_json(self) -> List[Dict]:
        """Load apartment data from JSON file (fallback mode)"""
        current_dir = Path(__file__).parent.parent
        data_file = current_dir / "data" / "apartments.json"

        try:
            with open(data_file, "r") as f:
                apartments = json.load(f)
            logger.info(f"Loaded {len(apartments)} apartments from JSON")
            return apartments
        except FileNotFoundError:
            logger.warning(f"Apartments JSON file not found: {data_file}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in apartments file: {e}")
            return []

    async def _search_database(
        self,
        city: str,
        budget: int,
        bedrooms: int,
        bathrooms: int,
        property_type: str,
        move_in_date: str,
        bedroom_mode: str = "exact",
    ) -> List[Dict]:
        """Search apartments in PostgreSQL database.

        Routes to the floorplan-aware join (per-floorplan matching, one card per
        building) when ``USE_FLOORPLAN_SEARCH`` is enabled, else the legacy
        building-level query. ``bedroom_mode`` is ``"exact"`` (default) or
        ``"plus"`` (>= N); it only affects the floorplan path.
        """
        if USE_FLOORPLAN_SEARCH:
            return await self._search_database_floorplan(
                city, budget, bedrooms, bathrooms, property_type, bedroom_mode
            )
        return await self._search_database_building(
            city, budget, bedrooms, bathrooms, property_type
        )

    async def _search_database_building(
        self,
        city: str,
        budget: int,
        bedrooms: int,
        bathrooms: int,
        property_type: str,
    ) -> List[Dict]:
        """Legacy building-level search: one row per building, bedroom matched on
        the building's collapsed ``bedrooms`` value."""
        from sqlalchemy import select, and_, or_
        from app.models.apartment import ApartmentModel

        property_types = [pt.strip() for pt in property_type.split(",")]
        city_name = city.split(",")[0].strip() if "," in city else city.strip()

        async with get_session_context() as session:
            stmt = select(ApartmentModel).where(
                and_(
                    ApartmentModel.is_active == 1,
                    ApartmentModel.freshness_confidence >= 40,
                    ApartmentModel.rent <= int(budget * 1.10),
                    ApartmentModel.bedrooms == bedrooms,
                    ApartmentModel.bathrooms >= bathrooms,
                    ApartmentModel.property_type.in_(property_types),
                    or_(
                        ApartmentModel.city.ilike(city_name),
                        ApartmentModel.address.ilike(f"%{city}%"),
                    ),
                )
            )

            result = await session.execute(stmt)
            apartments = [apt.to_summary_dict() for apt in result.scalars()]
            logger.info(f"Database search (building) returned {len(apartments)} apartments")
            return apartments

    async def _search_database_floorplan(
        self,
        city: str,
        budget: int,
        bedrooms: int,
        bathrooms: int,
        property_type: str,
        bedroom_mode: str = "exact",
    ) -> List[Dict]:
        """Floorplan-aware search (docs/floorplan-search-design.md).

        Joins ``apartment_floorplans`` and matches per-floorplan bucket, so a 3BR
        floorplan inside an otherwise-studio building is found. Returns one row
        per building (DISTINCT ON), keeping the cheapest matching bucket, with the
        matched floorplan projected onto the result dict.
        """
        from sqlalchemy import select, and_, or_
        from app.models.apartment import ApartmentModel
        from app.models.apartment_floorplan import ApartmentFloorplanModel as FP
        from app.services.floorplans import project_matched_floorplan

        property_types = [pt.strip() for pt in property_type.split(",")]
        city_name = city.split(",")[0].strip() if "," in city else city.strip()

        # Bedroom match mode (D3): exact N, or N+ for "3+" searches.
        bed_cond = (
            FP.bedrooms >= bedrooms if bedroom_mode == "plus" else FP.bedrooms == bedrooms
        )

        async with get_session_context() as session:
            stmt = (
                select(ApartmentModel, FP)
                .join(FP, FP.apartment_id == ApartmentModel.id)
                .where(
                    and_(
                        ApartmentModel.is_active == 1,
                        ApartmentModel.freshness_confidence >= 40,
                        ApartmentModel.property_type.in_(property_types),
                        or_(
                            ApartmentModel.city.ilike(city_name),
                            ApartmentModel.address.ilike(f"%{city}%"),
                        ),
                        bed_cond,
                        FP.bathrooms >= bathrooms,
                        FP.available_units > 0,
                        # Budget against the matched floorplan; keep
                        # price-on-request (null min_rent) — decision D1.
                        or_(
                            FP.min_rent <= int(budget * 1.10),
                            FP.min_rent.is_(None),
                        ),
                    )
                )
                # One card per building: keep the priced-before-unpriced,
                # smallest-qualifying, cheapest matching bucket.
                .distinct(ApartmentModel.id)
                .order_by(
                    ApartmentModel.id,
                    FP.min_rent.is_(None),
                    FP.bedrooms,
                    FP.min_rent.asc().nullslast(),
                )
            )

            result = await session.execute(stmt)
            apartments = []
            for apt, fp in result.all():
                projected = project_matched_floorplan(
                    apt.to_summary_dict(),
                    bedrooms=fp.bedrooms,
                    bathrooms=fp.bathrooms,
                    min_rent=fp.min_rent,
                    max_rent=fp.max_rent,
                    min_sqft=fp.min_sqft,
                    max_sqft=fp.max_sqft,
                    available_units=fp.available_units,
                    earliest_available_date=fp.earliest_available_date,
                )
                apartments.append(projected)

            logger.info(f"Database search (floorplan) returned {len(apartments)} apartments")
            return apartments

    def _search_json(
        self,
        city: str,
        budget: int,
        bedrooms: int,
        bathrooms: int,
        property_type: str,
        move_in_date: str
    ) -> List[Dict]:
        """Search apartments in JSON data (fallback mode)."""
        filtered = []

        # Parse property types into a list
        property_types = [pt.strip() for pt in property_type.split(",")]

        # Parse move-in date
        try:
            desired_move_in = datetime.strptime(move_in_date, "%Y-%m-%d")
        except ValueError:
            desired_move_in = None

        for apt in self._apartments_data:
            # Filter by city (case-insensitive, partial match)
            if city.lower() not in apt["address"].lower():
                continue

            # Filter by budget (with 10% buffer)
            if apt["rent"] > int(budget * 1.10):
                continue

            # Filter by bedrooms (exact match)
            if apt["bedrooms"] != bedrooms:
                continue

            # Filter by bathrooms (at least the requested number)
            if apt["bathrooms"] < bathrooms:
                continue

            # Filter by property type
            if apt["property_type"] not in property_types:
                continue

            filtered.append(apt)

        return filtered

    async def search_apartments(
        self,
        city: str,
        budget: int,
        bedrooms: int,
        bathrooms: int,
        property_type: str,
        move_in_date: str,
        bedroom_mode: str = "exact",
    ) -> List[Dict]:
        """
        Filter apartments based on basic search criteria.
        Uses database if enabled, otherwise falls back to JSON.

        Args:
            city: City to search in
            budget: Maximum monthly rent
            bedrooms: Number of bedrooms needed
            bathrooms: Number of bathrooms needed
            property_type: Comma-separated property types
            move_in_date: Desired move-in date (YYYY-MM-DD)
            bedroom_mode: "exact" (default) or "plus" (>= N); only affects the
                floorplan-aware DB path.

        Returns:
            List of filtered apartments
        """
        if self._use_database:
            return await self._search_database(
                city, budget, bedrooms, bathrooms,
                property_type, move_in_date, bedroom_mode=bedroom_mode,
            )
        else:
            return self._search_json(
                city, budget, bedrooms, bathrooms,
                property_type, move_in_date
            )

    async def get_apartments_paginated(
        self,
        city: str,
        budget: int,
        bedrooms: int,
        bathrooms: int,
        property_type: str,
        move_in_date: str,
        other_preferences: str = None,
        page: int = 1,
        page_size: int = 10,
    ) -> Tuple[List[Dict], int, bool]:
        """
        Get paginated heuristic-scored apartments.

        Page 1: filters from DB, scores, caches full list in Redis.
        Page 2+: reads from Redis cache, falls back to re-query on miss.

        Returns:
            Tuple of (page_results, total_count, has_more)
        """
        from app.services.scoring_service import ScoringService

        # Build cache key from search params (excluding page)
        raw = f"{city}:{budget}:{bedrooms}:{bathrooms}:{property_type}:{move_in_date}:{other_preferences or ''}"
        cache_key = f"search_pages:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

        # Try cache first (for page 2+ or even page 1 re-hits)
        cached = None
        if self._redis:
            try:
                cached = await self._redis.get(cache_key)
            except Exception:
                pass

        if cached:
            all_scored = json.loads(cached)
            # Reset TTL on access (keep alive while user is browsing)
            if self._redis:
                try:
                    await self._redis.expire(cache_key, 600)
                except Exception:
                    pass
        else:
            # Filter and score
            filtered = await self.search_apartments(
                city=city, budget=budget, bedrooms=bedrooms,
                bathrooms=bathrooms, property_type=property_type,
                move_in_date=move_in_date,
            )

            if not filtered:
                return [], 0, False

            all_scored = ScoringService.score_apartments_list(
                apartments=filtered, budget=budget,
                bedrooms=bedrooms, bathrooms=bathrooms,
                other_preferences=other_preferences,
            )

            # Cache the full list (10 min TTL)
            if self._redis:
                try:
                    await self._redis.setex(cache_key, 600, json.dumps(all_scored))
                except Exception:
                    pass

        total_count = len(all_scored)
        start = (page - 1) * page_size
        end = start + page_size
        page_results = all_scored[start:end]
        has_more = end < total_count

        return page_results, total_count, has_more

    async def get_apartments_by_ids(self, apartment_ids: List[str]) -> List[Dict]:
        """Fetch apartments by their IDs."""
        if self._use_database:
            from sqlalchemy import select
            from app.models.apartment import ApartmentModel
            async with get_session_context() as session:
                stmt = select(ApartmentModel).where(
                    ApartmentModel.id.in_(apartment_ids),
                    ApartmentModel.is_active == 1,
                )
                result = await session.execute(stmt)
                return [apt.to_summary_dict() for apt in result.scalars()]
        else:
            if not self._apartments_data:
                self._apartments_data = self._load_apartments_from_json()
            id_set = set(apartment_ids)
            return [apt for apt in self._apartments_data if apt["id"] in id_set]

    async def get_top_apartments(
        self,
        city: str,
        budget: int,
        bedrooms: int,
        bathrooms: int,
        property_type: str,
        move_in_date: str,
        other_preferences: str = None,
        near_label: str = None,
        top_n: int = 10
    ) -> Tuple[List[Dict], int]:
        """
        Get top N apartment recommendations based on user preferences.

        Args:
            city: City to search in
            budget: Maximum monthly rent
            bedrooms: Number of bedrooms needed
            bathrooms: Number of bathrooms needed
            property_type: Desired property types
            move_in_date: Desired move-in date
            other_preferences: Additional preferences
            top_n: Number of top results to return (default 10)

        Returns:
            Tuple of (list of apartments with scores, total count)
        """
        from app.services.scoring_service import ScoringService

        # Step 1: Filter (with soft budget)
        filtered_apartments = await self.search_apartments(
            city=city,
            budget=budget,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            property_type=property_type,
            move_in_date=move_in_date,
        )

        if not filtered_apartments:
            return [], 0

        # Step 2: Heuristic score and sort ALL filtered results
        scored = ScoringService.score_apartments_list(
            apartments=filtered_apartments,
            budget=budget,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            other_preferences=other_preferences,
        )

        total_count = len(scored)

        # Step 3: Send top 20 (by heuristic) to Claude for AI re-scoring
        max_to_score = top_n * 2
        apartments_to_score = scored[:max_to_score]

        # Check Claude score cache
        apt_ids = [a["id"] for a in apartments_to_score]
        cache_key = self.build_score_cache_key(
            city, budget, bedrooms, bathrooms, property_type,
            move_in_date, other_preferences or "", apt_ids,
            near_label=near_label,
        )

        cached = None
        if self._redis:
            try:
                cached = await self._redis.get(cache_key)
            except Exception:
                pass

        if cached:
            scores = json.loads(cached)
            logger.info(f"Claude score cache HIT for {cache_key}")
        else:
            BATCH_THRESHOLD = 12

            async def _score_batch(batch):
                async with _claude_semaphore:
                    return await asyncio.to_thread(
                        self.claude_service.score_apartments,
                        city=city,
                        budget=budget,
                        bedrooms=bedrooms,
                        bathrooms=bathrooms,
                        property_type=property_type,
                        move_in_date=move_in_date,
                        other_preferences=other_preferences or "None specified",
                        apartments=batch,
                        near_label=near_label,
                    )

            try:
                if len(apartments_to_score) > BATCH_THRESHOLD:
                    mid = len(apartments_to_score) // 2
                    batch_a = apartments_to_score[:mid]
                    batch_b = apartments_to_score[mid:]
                    scores_a, scores_b = await asyncio.wait_for(
                        asyncio.gather(_score_batch(batch_a), _score_batch(batch_b)),
                        timeout=15.0,
                    )
                    scores = scores_a + scores_b
                else:
                    scores = await asyncio.wait_for(
                        _score_batch(apartments_to_score),
                        timeout=15.0,
                    )

                # Cache the result (1 hour TTL)
                if self._redis:
                    try:
                        await self._redis.setex(cache_key, 3600, json.dumps(scores))
                        logger.info(f"Claude score cache MISS, stored {cache_key}")
                    except Exception:
                        pass

            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"Claude scoring failed, falling back to heuristic: {e}")
                scores = [
                    {
                        "apartment_id": apt["id"],
                        "match_score": apt.get("heuristic_score") or 50,
                        "reasoning": "AI scoring temporarily unavailable. Score based on heuristic matching.",
                        "highlights": [],
                    }
                    for apt in apartments_to_score
                ]

        # Step 4: Merge Claude scores
        scored_apartments = []
        score_map = {score["apartment_id"]: score for score in scores}
        for apt in apartments_to_score:
            apt_id = apt["id"]
            if apt_id in score_map:
                score_data = score_map[apt_id]
                scored_apt = {
                    **apt,
                    "match_score": score_data["match_score"],
                    "reasoning": score_data["reasoning"],
                    "highlights": score_data["highlights"],
                }
                scored_apartments.append(scored_apt)

        scored_apartments.sort(key=lambda x: x["match_score"], reverse=True)
        return scored_apartments[:top_n], total_count

    async def get_apartment_count_async(self) -> int:
        """Get total number of apartments (async version for database)."""
        if self._use_database:
            from sqlalchemy import select, func
            from app.models.apartment import ApartmentModel

            async with get_session_context() as session:
                stmt = select(func.count(ApartmentModel.id)).where(
                    ApartmentModel.is_active == 1
                )
                result = await session.execute(stmt)
                return result.scalar() or 0
        else:
            return len(self._apartments_data) if self._apartments_data else 0

    def get_apartment_count(self) -> int:
        """Get total number of apartments in database"""
        if self._use_database:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.get_apartment_count_async())
            finally:
                loop.close()
        else:
            return len(self._apartments_data) if self._apartments_data else 0

    async def get_apartments_by_city_async(self, city: str, limit: int = 100) -> List[Dict]:
        """Get apartments for a specific city (async)."""
        if self._use_database:
            from sqlalchemy import select, and_
            from app.models.apartment import ApartmentModel

            async with get_session_context() as session:
                stmt = select(ApartmentModel).where(
                    and_(
                        ApartmentModel.is_active == 1,
                        ApartmentModel.address.ilike(f"%{city}%")
                    )
                ).limit(limit)

                result = await session.execute(stmt)
                return [apt.to_dict() for apt in result.scalars()]
        else:
            return [
                apt for apt in self._apartments_data
                if city.lower() in apt.get("address", "").lower()
            ][:limit]

    async def get_listing_stats_async(self) -> Dict:
        """Get listing statistics (async)."""
        if self._use_database:
            from sqlalchemy import select, func
            from app.models.apartment import ApartmentModel

            async with get_session_context() as session:
                # Total active
                total_stmt = select(func.count(ApartmentModel.id)).where(
                    ApartmentModel.is_active == 1
                )
                total = (await session.execute(total_stmt)).scalar() or 0

                # By source
                source_stmt = select(
                    ApartmentModel.source,
                    func.count(ApartmentModel.id)
                ).where(
                    ApartmentModel.is_active == 1
                ).group_by(ApartmentModel.source)
                source_result = await session.execute(source_stmt)
                by_source = {row[0]: row[1] for row in source_result}

                # By city (top 10)
                city_stmt = select(
                    ApartmentModel.city,
                    func.count(ApartmentModel.id)
                ).where(
                    ApartmentModel.is_active == 1,
                    ApartmentModel.city.isnot(None)
                ).group_by(ApartmentModel.city).order_by(
                    func.count(ApartmentModel.id).desc()
                ).limit(10)
                city_result = await session.execute(city_stmt)
                by_city = {row[0]: row[1] for row in city_result}

                # Average quality
                quality_stmt = select(func.avg(ApartmentModel.data_quality_score))
                quality = (await session.execute(quality_stmt)).scalar() or 0

                return {
                    "total_active": total,
                    "by_source": by_source,
                    "by_city": by_city,
                    "avg_quality_score": round(quality, 2),
                }
        else:
            # JSON fallback stats
            total = len(self._apartments_data) if self._apartments_data else 0
            cities = {}
            for apt in (self._apartments_data or []):
                # Extract city from address
                address = apt.get("address", "")
                parts = address.split(",")
                if len(parts) >= 2:
                    city = parts[-2].strip()
                    cities[city] = cities.get(city, 0) + 1

            return {
                "total_active": total,
                "by_source": {"json": total},
                "by_city": dict(sorted(cities.items(), key=lambda x: -x[1])[:10]),
                "avg_quality_score": 50.0,
            }
