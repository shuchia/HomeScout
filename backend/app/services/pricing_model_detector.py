"""Detect whether a listing uses per-person or per-unit pricing."""
import re
from typing import Dict, Any

# High confidence signals (any one is sufficient). These are unambiguous
# by-the-bed / by-the-room phrases — luxury whole-unit listings don't use them,
# so each is enough on its own. The recall additions (co-living, rent-by-the-room,
# per-bedroom lease, the RoostUp operator) came from a coverage investigation that
# found real co-living listings tagged per_unit — see
# docs/floorplan-search-architecture.md "Detection coverage".
_HIGH_SIGNALS = [
    (r"per\s+person", 0.9),
    (r"per\s+bed\b", 0.9),
    (r"by\s+the\s+bed", 0.9),
    (r"individual\s+lease", 0.85),
    (r"per\s+room\b", 0.85),
    (r"co-?living", 0.9),
    (r"rent\s+by\s+the\s+room", 0.9),
    (r"\bby[- ]the[- ]room\b", 0.9),
    (r"\broostup\b", 0.9),  # known by-the-room operator
    (r"per[- ]bedroom\s+(lease|pricing|rate|rent)", 0.85),
]

# Medium signals (accumulated). Each is deliberately below the 0.6 threshold so
# it can't flag on its own — a whole-unit luxury listing that happens to say
# "private bedroom" (0.3) or "student" (0.35), even in a beds==baths unit (+0.25),
# stays per_unit. Only a genuine by-the-room combination crosses.
_MEDIUM_SIGNALS = [
    (r"\bstudent\b", 0.35),
    (r"off[- ]campus", 0.3),
    (r"prices\s+shown\s+are\s+base\s+rent", 0.5),
    (r"private\s+bedroom", 0.3),
    # "shared apartment/suite" = renting a room in a shared unit. Deliberately
    # excludes "shared living/spaces" — that's a luxury common-area amenity term,
    # not a by-the-room signal, and would false-positive on beds==baths luxury.
    (r"shared\s+(apartment|suite)", 0.4),
]


def detect_pricing_model(
    description: str,
    bedrooms: int,
    bathrooms: float,
    rent: int,
    city: str,
) -> Dict[str, Any]:
    """Detect per-person vs per-unit pricing from listing data.

    Returns:
        {"pricing_model": "per_unit"|"per_person", "confidence": float}
    """
    # Studios are never per-person
    if bedrooms == 0:
        return {"pricing_model": "per_unit", "confidence": 0.95}

    desc_lower = (description or "").lower()
    score = 0.0

    # High-confidence description signals
    for pattern, weight in _HIGH_SIGNALS:
        if re.search(pattern, desc_lower):
            score = max(score, weight)

    # Medium signals (accumulate)
    for pattern, weight in _MEDIUM_SIGNALS:
        if re.search(pattern, desc_lower):
            score += weight

    # Beds == baths pattern (2/2, 3/3, 4/4) — common in student housing
    if bedrooms >= 2 and bedrooms == int(bathrooms):
        score += 0.25

    # Clamp to 1.0
    score = min(score, 1.0)

    if score >= 0.6:
        return {"pricing_model": "per_person", "confidence": round(score, 2)}
    else:
        return {"pricing_model": "per_unit", "confidence": round(1.0 - score, 2)}
