"""Detect whether a listing uses per-person or per-unit pricing."""
import re
from typing import Dict, Any

# High confidence signals (any one is sufficient)
_HIGH_SIGNALS = [
    (r"per\s+person", 0.9),
    (r"per\s+bed\b", 0.9),
    (r"by\s+the\s+bed", 0.9),
    (r"individual\s+lease", 0.85),
    (r"per\s+room\b", 0.85),
]

# Medium signals (accumulated)
_MEDIUM_SIGNALS = [
    (r"\bstudent\b", 0.35),
    (r"off[- ]campus", 0.3),
    (r"prices\s+shown\s+are\s+base\s+rent", 0.5),
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
