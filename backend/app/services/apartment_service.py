import json
import os
from typing import List, Dict
from datetime import datetime
from pathlib import Path

from app.services.claude_service import ClaudeService


class ApartmentService:
    """Service for managing apartment search and matching"""

    def __init__(self):
        self.claude_service = ClaudeService()
        self.apartments_data = self._load_apartments()

    def _load_apartments(self) -> List[Dict]:
        """Load apartment data from JSON file"""
        # Get the path to the apartments.json file
        current_dir = Path(__file__).parent.parent
        data_file = current_dir / "data" / "apartments.json"

        with open(data_file, "r") as f:
            apartments = json.load(f)

        return apartments

    def search_apartments(
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

        Args:
            city: City to search in
            budget: Maximum monthly rent (we allow 20% flexibility)
            bedrooms: Number of bedrooms needed
            bathrooms: Number of bathrooms needed
            property_type: Comma-separated property types
            move_in_date: Desired move-in date (YYYY-MM-DD)

        Returns:
            List of filtered apartments
        """
        filtered = []

        # Parse property types into a list
        property_types = [pt.strip() for pt in property_type.split(",")]

        # Parse move-in date
        try:
            desired_move_in = datetime.strptime(move_in_date, "%Y-%m-%d")
        except ValueError:
            # If invalid date format, just use string comparison
            desired_move_in = None

        for apt in self.apartments_data:
            # Filter by city (case-insensitive, partial match)
            if city.lower() not in apt["address"].lower():
                continue

            # Filter by budget (allow up to 20% over budget for flexibility)
            if apt["rent"] > budget * 1.2:
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
                    # If invalid date in data, skip date filtering for this apartment
                    pass

            filtered.append(apt)

        return filtered

    def get_top_apartments(
        self,
        city: str,
        budget: int,
        bedrooms: int,
        bathrooms: int,
        property_type: str,
        move_in_date: str,
        other_preferences: str = None,
        top_n: int = 10
    ) -> tuple[List[Dict], int]:
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
        filtered_apartments = self.search_apartments(
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

        # Step 2: Score apartments using Claude AI
        scores = self.claude_service.score_apartments(
            city=city,
            budget=budget,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            property_type=property_type,
            move_in_date=move_in_date,
            other_preferences=other_preferences or "None specified",
            apartments=filtered_apartments
        )

        # Step 3: Merge apartment data with scores
        scored_apartments = []
        score_map = {score["apartment_id"]: score for score in scores}

        for apt in filtered_apartments:
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

    def get_apartment_count(self) -> int:
        """Get total number of apartments in database"""
        return len(self.apartments_data)
