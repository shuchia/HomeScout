"""Haversine distance calculation for proximity search."""
import math
from typing import List, Dict, Optional


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate crow-flies distance in miles between two lat/lng points."""
    R = 3958.8  # Earth's radius in miles
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def add_distances(
    apartments: List[Dict],
    near_lat: float,
    near_lng: float,
    max_distance_miles: Optional[float] = None,
) -> List[Dict]:
    """Add distance_miles to each apartment, sort by distance, optionally filter."""
    with_dist = []
    without_coords = []

    for apt in apartments:
        lat = apt.get("latitude")
        lng = apt.get("longitude")
        if lat is not None and lng is not None:
            dist = round(haversine_miles(near_lat, near_lng, lat, lng), 1)
            if max_distance_miles is not None and dist > max_distance_miles:
                continue
            with_dist.append({**apt, "distance_miles": dist})
        else:
            without_coords.append({**apt, "distance_miles": None})

    with_dist.sort(key=lambda x: x["distance_miles"])
    return with_dist + without_coords