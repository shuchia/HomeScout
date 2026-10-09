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


# Degrees of latitude per mile is near-constant; longitude narrows with
# latitude, so the longitude span has to be divided by cos(lat).
_MILES_PER_DEGREE_LAT = 69.0


def bounding_box(lat: float, lng: float, miles: float):
    """A lat/lng box guaranteed to contain every point within ``miles``.

    A cheap SQL prefilter so the radius can be applied *before* pagination
    rather than after. It is deliberately a superset — the corners of a box
    sit further out than the circle it encloses — so the exact haversine
    filter still has to run on what comes back. Getting those the wrong way
    round silently drops listings near the edge.

    Returns ``(min_lat, max_lat, min_lng, max_lng)``.
    """
    lat_delta = miles / _MILES_PER_DEGREE_LAT

    # cos() collapses toward the poles, which would make the longitude span
    # explode or divide by zero. Clamp so the box stays finite; at these
    # latitudes it never binds, and a too-wide box is merely slower, not wrong.
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    lng_delta = miles / (_MILES_PER_DEGREE_LAT * cos_lat)

    return (
        lat - lat_delta,
        lat + lat_delta,
        lng - lng_delta,
        lng + lng_delta,
    )


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
        elif max_distance_miles is None:
            without_coords.append({**apt, "distance_miles": None})
        # When a radius is set, a listing with no coordinates is dropped. It
        # cannot be shown as satisfying "within N miles of here" — and leaving
        # it in was a quiet way to defeat the filter entirely, since these were
        # appended after the distance check rather than going through it.
        # The DB query already excludes them; this keeps the function honest
        # on its own, which matters for JSON mode and for any caller that
        # filters without a query behind it.

    with_dist.sort(key=lambda x: x["distance_miles"])
    return with_dist + without_coords