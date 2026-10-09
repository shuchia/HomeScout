"""Aggregate apartments.com floorplans into per-(bedrooms, bathrooms) buckets.

Each apartments.com property is one *building* with many floorplans (the
`models` array, persisted as `ApartmentModel.floor_plans`). Search needs
per-floorplan granularity — a 3-bedroom search must match a building that has a
3-bedroom floorplan, priced on *that* floorplan — but the UI shows one card per
building. So we collapse the raw floorplans into one bucket per
`(bedrooms, bathrooms)` among the *available* units, carrying the rent/sqft
range, summed available units, and the earliest availability date.

This module is pure (no DB, no network) so it can be unit-tested and reused by
both the backfill task and live ingestion. See
``docs/floorplan-search-design.md`` for the full design and decisions.

Parsing mirrors ``base_scraper._parse_*`` deliberately so buckets agree with the
building-level values the scraper already produces.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional


def parse_rent(value: Any) -> Optional[int]:
    """Parse a price like ``"$4,624 - 4,952"`` → 4624 (low bound).

    Returns ``None`` for missing prices or "Call for Rent" (→ price-on-request).
    Mirrors ``base_scraper._parse_rent``.
    """
    if value is None:
        return None
    if isinstance(value, bool):  # guard: bool is an int subclass
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").strip()
        if "-" in cleaned:
            cleaned = cleaned.split("-")[0].strip()
        try:
            return int(float(cleaned))
        except ValueError:
            return None
    return None


def parse_rent_high(value: Any) -> Optional[int]:
    """Parse the *high* bound of a price like ``"$4,624 - 4,952"`` → 4952.

    Single prices return themselves; "Call for Rent" → ``None``. Used for the
    bucket's ``max_rent`` (display range), while ``parse_rent`` gives the low
    bound used for budget filtering.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").strip()
        if "-" in cleaned:
            cleaned = cleaned.split("-")[-1].strip()
        try:
            return int(float(cleaned))
        except ValueError:
            return None
    return None


def parse_bedrooms(value: Any) -> Optional[int]:
    """Parse a floorplan bed label like ``"3 Beds"`` → 3, ``"Studio"`` → 0.

    Returns ``None`` when nothing parseable is found (caller decides fallback).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        low = value.lower().strip()
        if not low:
            return None
        if "studio" in low:
            return 0
        m = re.findall(r"(\d+)\s*(?:bd|bed|br|bedroom)", low)
        if m:
            return int(m[0])
        m = re.findall(r"(\d+)", low)
        if m:
            return int(m[0])
    return None


def parse_bathrooms(value: Any) -> Optional[float]:
    """Parse a floorplan bath label like ``"2 Baths"`` → 2.0. Mirrors base."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        low = value.lower().strip()
        m = re.findall(r"(\d+\.?\d*)\s*(?:ba|bath|bathroom)", low)
        if m:
            return float(m[0])
        m = re.findall(r"(\d+\.?\d*)", low)
        if m:
            return float(m[0])
    return None


def parse_sqft(value: Any) -> Optional[int]:
    """Parse a sqft label like ``"698 - 741"`` or ``"1,444"`` → low bound int."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        m = re.search(r"(\d[\d,]*)", value)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                return None
    return None


def parse_available_units(value: Any) -> int:
    """Parse ``"3 Available units"`` → 3, ``"0 Available units"`` → 0.

    Unknown / missing availability is treated as 0 (not available) so a
    floorplan only becomes searchable when the source explicitly says units are
    available.
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        m = re.match(r"\s*(\d+)", value)
        if m:
            return int(m.group(1))
    return 0


def _earliest_upcoming(dates: List[str], today: str) -> Optional[str]:
    """Earliest date >= today from a list of ``YYYY-MM-DD`` strings.

    Falls back to the earliest date overall when all are in the past (a listing
    that was "available from" a past date is available now).
    """
    if not dates:
        return None
    upcoming = sorted(d for d in dates if d >= today)
    if upcoming:
        return upcoming[0]
    return sorted(dates)[0]


def _rental_dates_by_model(rentals: Optional[List[Any]]) -> Dict[str, List[str]]:
    """Group ``rentals[].availableDate`` (YYYY-MM-DD) by ``modelId``."""
    out: Dict[str, List[str]] = {}
    if not isinstance(rentals, list):
        return out
    for r in rentals:
        if not isinstance(r, dict):
            continue
        mid = r.get("modelId")
        raw = r.get("availableDate")
        if not mid or not isinstance(raw, str) or len(raw) < 10:
            continue
        out.setdefault(str(mid), []).append(raw[:10])
    return out


# Price fields on a floorplan model, in precedence order.
#
# apartments.com payloads come in two shapes and the actor emits whichever the
# property page uses. The older one carries ``totalPrice``/``basePrice``; newer
# captures carry ``rentLabel`` instead, with no price fields at all. Reading
# only the first pair silently turned every newly-captured priced floorplan
# into "price on request" — measured 2026-10-03 at 4.9% of models and rising
# with every sweep, with *zero* models genuinely lacking a price.
#
# A property uses one shape or the other, never both (80 listings sampled, 0
# mixed), so this is a fallback chain rather than a reconciliation.
_MODEL_PRICE_FIELDS = ("totalPrice", "basePrice", "rentLabel")


def model_price(model: Dict[str, Any]) -> tuple[Optional[int], Optional[int]]:
    """``(low, high)`` price for one floorplan model, across payload shapes.

    Returns ``(None, None)`` when the model is genuinely price-on-request —
    which must stay distinguishable from "we could not read the field".
    """
    for field in _MODEL_PRICE_FIELDS:
        raw = model.get(field)
        low = parse_rent(raw)
        if low is not None:
            return low, parse_rent_high(raw)
    return None, None


def rental_dates(rentals: Optional[List[Any]]) -> List[str]:
    """Every ``YYYY-MM-DD`` availability date on a building's rentals array.

    Unlike :func:`_rental_dates_by_model` this does not need a ``modelId``.
    Single-unit and by-the-room listings carry no ``models`` at all and their
    rental objects are keyed by ``key``, so the model join can never reach
    them — which is how ~56% of the corpus ended up with no availability date
    while holding one in ``available_units[].availableDate``.
    """
    out: List[str] = []
    if not isinstance(rentals, list):
        return out
    for r in rentals:
        if not isinstance(r, dict):
            continue
        raw = r.get("availableDate")
        if isinstance(raw, str) and len(raw) >= 10:
            out.append(raw[:10])
    return out


def earliest_rental_date(rentals: Optional[List[Any]], today: Optional[str] = None) -> Optional[str]:
    """Earliest upcoming availability date across a building's rentals."""
    return _earliest_upcoming(rental_dates(rentals), today or date.today().isoformat())


def _buckets_ignoring_availability(
    floor_plans: Optional[List[Any]],
    dates_by_model: Dict[str, List[str]],
    today: str,
    fallback_bathrooms: Optional[float],
    fallback_available_date: Optional[str],
    description: Optional[str],
    city: Optional[str],
    source_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Group a fully-leased building's floorplans, with ``available_units = 0``.

    Same shape as a normal bucket so the search join stays uniform; the zero
    unit count is what marks it unrentable. Only called when the ordinary pass
    found nothing available, so it never competes with real inventory.
    """
    groups: Dict[tuple, Dict[str, Any]] = {}
    for model in floor_plans or []:
        if not isinstance(model, dict):
            continue
        details = model.get("details")
        if not isinstance(details, list) or not details:
            continue
        beds = parse_bedrooms(details[0])
        if beds is None:
            continue
        baths = parse_bathrooms(details[1] if len(details) > 1 else None)
        if baths is None:
            baths = fallback_bathrooms if fallback_bathrooms is not None else 1.0
        rent, rent_high = model_price(model)
        sqft = parse_sqft(model.get("squareFeet"))
        model_id = model.get("modelId")

        key = (beds, float(baths))
        g = groups.setdefault(key, {
            "bedrooms": beds, "bathrooms": float(baths),
            "rents": [], "rents_high": [], "sqfts": [], "dates": [], "model_ids": [],
        })
        if rent is not None:
            g["rents"].append(rent)
        if rent_high is not None:
            g["rents_high"].append(rent_high)
        if sqft is not None:
            g["sqfts"].append(sqft)
        if model_id:
            g["model_ids"].append(str(model_id))
            g["dates"].extend(dates_by_model.get(str(model_id), []))

    out: List[Dict[str, Any]] = []
    for g in groups.values():
        min_rent = min(g["rents"]) if g["rents"] else None
        out.append({
            "bedrooms": g["bedrooms"],
            "bathrooms": g["bathrooms"],
            "min_rent": min_rent,
            "max_rent": max(g["rents_high"]) if g["rents_high"] else None,
            "min_sqft": min(g["sqfts"]) if g["sqfts"] else None,
            "max_sqft": max(g["sqfts"]) if g["sqfts"] else None,
            "available_units": 0,
            "earliest_available_date": _earliest_upcoming(g["dates"], today) or fallback_available_date,
            "model_ids": g["model_ids"],
            "pricing_model": _detect_bucket_pricing(
                description, city, g["bedrooms"], g["bathrooms"], min_rent, source_url
),
        })
    return out


def build_floorplan_buckets(
    floor_plans: Optional[List[Any]],
    rentals: Optional[List[Any]] = None,
    *,
    fallback_bedrooms: Optional[int] = None,
    fallback_bathrooms: Optional[float] = None,
    fallback_rent: Optional[int] = None,
    fallback_sqft: Optional[int] = None,
    fallback_available_date: Optional[str] = None,
    description: Optional[str] = None,
    city: Optional[str] = None,
    today: Optional[str] = None,
    source_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Collapse a building's floorplans into ``(bedrooms, bathrooms)`` buckets.

    Args:
        floor_plans: the building's ``models`` array (``ApartmentModel.floor_plans``).
        rentals: the building's ``rentals`` array, for per-model availability dates.
        fallback_*: building-level values used when there are no usable models —
            non-apartments.com sources (zillow/craigslist/manual) and single-unit
            listings get exactly one implicit bucket so every building has >=1
            bucket and the search join is uniform.
        description, city: building-level context for per-bucket pricing-model
            detection (per_unit vs per_person / by-the-bed). Detected per bucket
            using the bucket's real beds/baths — the building's own pricing_model
            is unreliable because it's computed on the collapsed bedroom count.
        today: ``YYYY-MM-DD`` reference for "earliest upcoming"; defaults to
            ``date.today()``. Injectable for tests.

    Returns:
        A list of bucket dicts, one per available ``(bedrooms, bathrooms)``:
        ``{bedrooms, bathrooms, min_rent, max_rent, min_sqft, max_sqft,
        available_units, earliest_available_date, model_ids}``. ``min_rent`` is
        ``None`` when every unit in the bucket is price-on-request. Buckets with
        no available units are omitted. May be empty (building has nothing
        currently available).
    """
    today = today or date.today().isoformat()
    dates_by_model = _rental_dates_by_model(rentals)

    # Group available models by (bedrooms, bathrooms).
    groups: Dict[tuple, Dict[str, Any]] = {}
    had_any_model = False  # did this building carry a floorplan array at all?

    for model in floor_plans or []:
        if not isinstance(model, dict):
            continue
        had_any_model = True
        avail = parse_available_units(model.get("availability"))
        if avail <= 0:
            continue  # 0-available floorplans are not searchable
        details = model.get("details")
        if not isinstance(details, list) or not details:
            continue
        beds = parse_bedrooms(details[0])
        if beds is None:
            continue  # unparseable size → skip; building fallback still applies
        baths = parse_bathrooms(details[1] if len(details) > 1 else None)
        if baths is None:
            baths = fallback_bathrooms if fallback_bathrooms is not None else 1.0
        rent, rent_high = model_price(model)
        sqft = parse_sqft(model.get("squareFeet"))
        model_id = model.get("modelId")

        dates: List[str] = []
        if model_id and str(model_id) in dates_by_model:
            dates = dates_by_model[str(model_id)]

        key = (beds, float(baths))
        g = groups.get(key)
        if g is None:
            g = {
                "bedrooms": beds,
                "bathrooms": float(baths),
                "rents": [],
                "rents_high": [],
                "sqfts": [],
                "available_units": 0,
                "dates": [],
                "model_ids": [],
            }
            groups[key] = g
        if rent is not None:
            g["rents"].append(rent)
        if rent_high is not None:
            g["rents_high"].append(rent_high)
        if sqft is not None:
            g["sqfts"].append(sqft)
        g["available_units"] += avail
        g["dates"].extend(dates)
        if model_id:
            g["model_ids"].append(str(model_id))

    # No available floorplans. Two different situations.
    if not groups and had_any_model:
        # The building carried floorplans but none have units right now. It used
        # to produce no buckets at all, which made it invisible to search — 124
        # active QA listings, 8% of the corpus, silently absent.
        #
        # They are emitted now with available_units = 0 so they can match a
        # search and be shown with a "nothing available" caveat. A building that
        # fits someone's criteria is worth knowing about even when it is fully
        # leased: you can call, join a waitlist, or check back. What must not
        # happen is one of these outranking somewhere you can actually rent, so
        # the search orders zero-unit buckets last and the card labels them.
        #
        # Measured 2026-10-01: none of those 124 had a single future-dated unit,
        # so this is not rescuing "free in August" inventory — apartments.com
        # reports that as available with a future date, which already works.
        # These are genuinely full today.
        unavailable = _buckets_ignoring_availability(
            floor_plans, dates_by_model, today, fallback_bathrooms,
            fallback_available_date, description, city, source_url,
        )
        if unavailable:
            return unavailable

    if not groups:
        if not had_any_model and fallback_bedrooms is not None:
            beds = int(fallback_bedrooms)
            baths = float(fallback_bathrooms) if fallback_bathrooms is not None else 1.0
            return [
                {
                    "bedrooms": beds,
                    "bathrooms": baths,
                    "min_rent": fallback_rent,
                    "max_rent": fallback_rent,
                    "min_sqft": fallback_sqft,
                    "max_sqft": fallback_sqft,
                    "available_units": 1,
                    # A listing with no models still carries its date in
                    # `rentals`; without this the single fallback bucket has no
                    # date and the card reads "availability unknown".
                    "earliest_available_date": (
                        fallback_available_date or earliest_rental_date(rentals, today)
                    ),
                    "model_ids": [],
                    "pricing_model": _detect_bucket_pricing(
                        description, city, beds, baths, fallback_rent, source_url
),
                }
            ]
        return []

    buckets: List[Dict[str, Any]] = []
    for g in groups.values():
        rents = g["rents"]
        rents_high = g["rents_high"]
        sqfts = g["sqfts"]
        earliest = _earliest_upcoming(g["dates"], today) or fallback_available_date
        min_rent = min(rents) if rents else None
        buckets.append(
            {
                "bedrooms": g["bedrooms"],
                "bathrooms": g["bathrooms"],
                "min_rent": min_rent,
                "max_rent": max(rents_high) if rents_high else None,
                "min_sqft": min(sqfts) if sqfts else None,
                "max_sqft": max(sqfts) if sqfts else None,
                "available_units": g["available_units"],
                "earliest_available_date": earliest,
                "model_ids": g["model_ids"],
                # Per-bucket pricing model (per_unit vs per_person / by-the-bed),
                # detected on the bucket's real beds/baths — not the building's
                # collapsed pricing_model (which is computed on bedrooms=0).
                "pricing_model": _detect_bucket_pricing(
                    description, city, g["bedrooms"], g["bathrooms"], min_rent, source_url
),
            }
        )

    # Stable order: by bedrooms then bathrooms.
    buckets.sort(key=lambda b: (b["bedrooms"], b["bathrooms"]))
    return buckets


def _detect_bucket_pricing(
    description: Optional[str],
    city: Optional[str],
    bedrooms: int,
    bathrooms: float,
    rent: Optional[int],
    source_url: Optional[str] = None,
) -> Optional[str]:
    """Detect per_unit vs per_person for one bucket. Returns None when there's no
    signal to run on (no description and studio), leaving it unlabeled."""
    # Studios are never per-person; skip the detector's building-level call when
    # we have nothing to go on.
    if not description and bedrooms == 0:
        return None
    try:
        from app.services.pricing_model_detector import detect_pricing_model

        return detect_pricing_model(
            description=description or "",
            bedrooms=int(bedrooms),
            bathrooms=float(bathrooms),
            rent=int(rent) if rent else 0,
            city=city or "",
            source_url=source_url or "",
        )["pricing_model"]
    except Exception:
        return None


def project_matched_floorplan(
    apt: Dict[str, Any],
    *,
    bedrooms: int,
    bathrooms: float,
    min_rent: Optional[int],
    max_rent: Optional[int],
    min_sqft: Optional[int],
    max_sqft: Optional[int],
    available_units: Optional[int] = None,
    earliest_available_date: Optional[str] = None,
    pricing_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Overlay a matched floorplan bucket onto a building's summary dict.

    A floorplan search matches a *building* on one of its buckets, but
    ``to_summary_dict`` describes the collapsed building (studio rent/beds). This
    projects the matched bucket's values onto a copy of that dict so scoring, the
    card, and everything downstream reflect the unit the user actually searched
    for — not the studio.

    ``rent`` carries the bucket's own price — ``min_rent``, else ``max_rent`` —
    and is **None when the bucket has no price at all**. It is never the
    building's collapsed studio rent.

    ``rent_for_scoring`` is the always-numeric value the heuristic needs, and
    falls back to the building's rent when the bucket is unpriced.

    The split exists because one field cannot honestly serve both. It used to:
    ``rent`` fell back to the building's figure so scoring could do
    ``rent <= budget``, and every consumer that treated it as a price published
    a number the property never quoted. That shipped twice in one week — a card
    reading "Price on request" above "Est. True Cost $2,700/mo", and AI
    reasoning asserting "$3,390 advertised rent" on a listing with no published
    price. Both read ``rent`` in good faith. Now a consumer that wants
    something displayable gets None and has to decide what to do about it.

    See decision D1.

    For ``per_person`` (by-the-bed) floorplans, ``min_rent`` is the per-bedroom
    share; matching/scoring stays on that per-bed price (students pay per bed),
    but ``matched_floorplan`` also carries ``per_bed_rent`` and an estimated
    ``whole_unit_rent`` (= per-bed × bedrooms) so the card can label it clearly.
    """
    # The bucket's own price, or nothing. max_rent is a real price for this
    # bucket (an upper bound), so it counts; the building's rent does not.
    rent = min_rent if min_rent is not None else max_rent

    # What the heuristic scores against. Falls back to the building's rent so
    # `rent <= budget` always has a number, which is the whole reason the two
    # are now separate fields.
    rent_for_scoring = rent if rent is not None else apt.get("rent")

    per_person = pricing_model == "per_person"
    per_bed_rent = min_rent if per_person else None
    whole_unit_rent = (
        min_rent * max(int(bedrooms), 1) if (per_person and min_rent is not None) else None
    )

    out = {**apt}
    out["rent"] = rent
    out["rent_for_scoring"] = rent_for_scoring
    out["bedrooms"] = bedrooms
    out["bathrooms"] = int(bathrooms) if float(bathrooms).is_integer() else bathrooms
    if min_sqft or max_sqft:
        out["sqft"] = min_sqft or max_sqft or apt.get("sqft") or 0
    out["price_on_request"] = min_rent is None
    # Surface the per-bucket pricing model (overrides the building-level value,
    # which is unreliable for buckets) so Claude scoring and the card use it.
    out["pricing_model"] = pricing_model or apt.get("pricing_model")
    out["matched_floorplan"] = {
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "min_rent": min_rent,
        "max_rent": max_rent,
        "min_sqft": min_sqft,
        "max_sqft": max_sqft,
        "available_units": available_units,
        "earliest_available_date": earliest_available_date,
        "price_on_request": min_rent is None,
        "pricing_model": pricing_model,
        "per_bed_rent": per_bed_rent,
        "whole_unit_rent": whole_unit_rent,
    }
    return out
