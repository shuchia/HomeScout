"""
Service for managing apartment search and matching.
Supports both database (PostgreSQL) and JSON file fallback.
"""
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


class ApartmentService:
    """Service for managing apartment search and matching"""

    def __init__(self):
        self.claude_service = ClaudeService()
        self._apartments_data: Optional[List[Dict]] = None
        self._use_database = is_database_enabled()

        if not self._use_database:
            logger.info("Database not enabled, using JSON fallback")
            self._apartments_data = self._load_apartments_from_json()

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
        move_in_date: str
    ) -> List[Dict]:
        """Search apartments in PostgreSQL database."""
        from sqlalchemy import select, and_, or_
        from app.models.apartment import ApartmentModel

        # Parse property types
        property_types = [pt.strip() for pt in property_type.split(",")]

        # Parse city name from "City, ST" format for column matching
        city_name = city.split(",")[0].strip() if "," in city else city.strip()

        # Parse move-in date
        try:
            desired_move_in = datetime.strptime(move_in_date, "%Y-%m-%d")
        except ValueError:
            desired_move_in = None

        async with get_session_context() as session:
            # Build query with filters
            stmt = select(ApartmentModel).where(
                and_(
                    ApartmentModel.is_active == 1,
                    ApartmentModel.freshness_confidence >= 40,
                    ApartmentModel.rent <= budget,
                    ApartmentModel.bedrooms == bedrooms,
                    ApartmentModel.bathrooms >= bathrooms,
                    ApartmentModel.property_type.in_(property_types),
                    # City filter: match on indexed city column or fallback to address
                    or_(
                        ApartmentModel.city.ilike(city_name),
                        ApartmentModel.address.ilike(f"%{city}%"),
                    ),
                )
            )

            result = await session.execute(stmt)
            apartments = []

            for apt in result.scalars():
                # Additional filter for move-in date
                if desired_move_in and apt.available_date:
                    try:
                        apt_available = datetime.strptime(apt.available_date, "%Y-%m-%d")
                        if apt_available > desired_move_in:
                            continue
                    except ValueError:
                        pass

                apartments.append(apt.to_dict())

            logger.info(f"Database search returned {len(apartments)} apartments")
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

            # Filter by budget (strict maximum)
            if apt["rent"] > budget:
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

            # Filter by available date (must be available on or before move-in date)
            if desired_move_in:
                try:
                    apt_available = datetime.strptime(apt["available_date"], "%Y-%m-%d")
                    if apt_available > desired_move_in:
                        continue
                except ValueError:
                    pass

            filtered.append(apt)

        return filtered

    async def search_apartments(
        self,
        city: str,
        budget: int,
        bedrooms: int,
        bathrooms: int,
        property_type: str,
        move_in_date: str
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

        Returns:
            List of filtered apartments
        """
        if self._use_database:
            return await self._search_database(
                city, budget, bedrooms, bathrooms,
                property_type, move_in_date
            )
        else:
            return self._search_json(
                city, budget, bedrooms, bathrooms,
                property_type, move_in_date
            )

    async def get_top_apartments(
        self,
        city: str,
        budget: int,
        bedrooms: int,
        bathrooms: int,
        property_type: str,
        move_in_date: str,
        other_preferences: str = None,
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
        # Step 1: Filter apartments by basic criteria
        filtered_apartments = await self.search_apartments(
            city=city,
            budget=budget,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            property_type=property_type,
            move_in_date=move_in_date
        )

        # If no apartments match, return empty results
        if not filtered_apartments:
            return [], 0

        # Cap the number of apartments sent to Claude to keep API calls fast
        max_to_score = top_n * 2
        apartments_to_score = filtered_apartments[:max_to_score]

        # Step 2: Score apartments using Claude AI (run in thread to not block async loop)
        scores = await asyncio.to_thread(
            self.claude_service.score_apartments,
            city=city,
            budget=budget,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            property_type=property_type,
            move_in_date=move_in_date,
            other_preferences=other_preferences or "None specified",
            apartments=apartments_to_score,
        )

        # Step 3: Merge apartment data with scores
        scored_apartments = []
        score_map = {score["apartment_id"]: score for score in scores}

        for apt in apartments_to_score:
            apt_id = apt["id"]
            if apt_id in score_map:
                score_data = score_map[apt_id]
                # Combine apartment data with score
                scored_apt = {
                    **apt,
                    "match_score": score_data["match_score"],
                    "reasoning": score_data["reasoning"],
                    "highlights": score_data["highlights"]
                }
                scored_apartments.append(scored_apt)

        # Step 4: Sort by match score (highest first)
        scored_apartments.sort(key=lambda x: x["match_score"], reverse=True)

        # Step 5: Return top N results
        top_apartments = scored_apartments[:top_n]
        total_count = len(top_apartments)

        return top_apartments, total_count

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
