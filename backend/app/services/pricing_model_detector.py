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
    # Room-in-a-shared-house phrasing. Added 2026-10-09 after 5 Linden St,
    # Boston — "Room for rent: ... a private room in a shared apartment ...
    # Full bedroom in a 4 bedroom / 1 bathroom apartment" — scored 0.4 and was
    # published as a whole 4-bed house for $1,130. 90 listings across five
    # markets were mislabelled the same way. The existing vocabulary was built
    # for purpose-built student co-living and had no word for the far commoner
    # case of renting one room in a share.
    (r"room\s+for\s+rent", 0.9),
    (r"private\s+room\s+in\s+an?\s+shared", 0.9),
    (r"\broom\s+in\s+an?\s+shared\b", 0.9),
    (r"full\s+bedroom\s+in\s+an?\s+\d+\s*bed", 0.9),
    (r"\bjune\s+(homes?|representative)\b", 0.85),  # by-the-room operator
]

# Signals read from the listing URL. apartments.com builds its slug from the
# listing title, which is frequently more explicit than the description and
# costs nothing to read — the 5 Linden St slug was literally
# "room-in-shared-4-bed-1-bath-home-in-allston" while the detector was
# scoring the prose and getting it wrong.
_URL_SIGNALS = [
    (r"room-in-shared", 0.9),
    (r"shared-\d+-bed", 0.9),
    (r"room-for-rent", 0.9),
    (r"private-room", 0.85),
    (r"co-?living", 0.9),
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
    source_url: str = "",
) -> Dict[str, Any]:
    """Detect per-person vs per-unit pricing from listing data.

    Returns:
        {"pricing_model": ..., "confidence": float, "uncertain": bool}

    ``uncertain`` marks a listing with real evidence of by-the-room pricing
    that did not reach the threshold. It is not the same as a confident
    per_unit, and the distinction matters: getting this wrong publishes one
    room's rent as a whole house's, which always errs in the
    too-good-to-be-true direction and ranks the listing straight to the top.
    """
    # Studios are never per-person
    if bedrooms == 0:
        return {"pricing_model": "per_unit", "confidence": 0.95, "uncertain": False}

    desc_lower = (description or "").lower()
    url_lower = (source_url or "").lower()
    score = 0.0

    # High-confidence description signals
    for pattern, weight in _HIGH_SIGNALS:
        if re.search(pattern, desc_lower):
            score = max(score, weight)

    # URL slug signals, same confidence class as the description ones
    for pattern, weight in _URL_SIGNALS:
        if re.search(pattern, url_lower):
            score = max(score, weight)

    # Medium signals (accumulate)
    for pattern, weight in _MEDIUM_SIGNALS:
        if re.search(pattern, desc_lower):
            score += weight

    # Beds == baths pattern (2/2, 3/3, 4/4) — common in student housing
    if bedrooms >= 2 and bedrooms == int(bathrooms):
        score += 0.25

    # Beds far exceeding baths (4bd/1ba, 6bd/2ba, 7bd/2.5ba). The opposite
    # shape to the one above, and the one a room-in-a-share actually has:
    # purpose-built co-living gives every bed its own bath, a shared house
    # does not. Deliberately below the threshold on its own so an ordinary
    # family home does not flip on geometry alone — it needs a word as well.
    # Weighted 0.25, not 0.35, so it does not combine with the weak
    # "private bedroom" signal (0.3) to flip a luxury 3bd/1ba. The real cases
    # all carry an explicit word or URL slug anyway; this is the safety net,
    # not the primary signal.
    if bedrooms >= 3 and (bedrooms - float(bathrooms)) >= 2:
        score += 0.25

    # Clamp to 1.0
    score = min(score, 1.0)

    if score >= 0.6:
        return {
            "pricing_model": "per_person",
            "confidence": round(score, 2),
            "uncertain": False,
        }
    # Real evidence that fell short. Reporting this as a confident per_unit is
    # how 5 Linden St shipped: score 0.4, published as "confidence 0.6" in the
    # wrong answer.
    return {
        "pricing_model": "per_unit",
        "confidence": round(1.0 - score, 2),
        "uncertain": score >= 0.3,
    }
