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
        rent = parse_rent(model.get("totalPrice"))
        rent_high = parse_rent_high(model.get("totalPrice"))
        if rent is None:
            rent = parse_rent(model.get("basePrice"))
            rent_high = parse_rent_high(model.get("basePrice"))
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

    # No available floorplans. If the building carried NO floorplan array at all
    # (zillow / craigslist / manual — the listing itself is one unit), emit one
    # implicit bucket from building-level values so the search join is uniform.
    # If it DID carry floorplans but none are available, emit nothing — the
    # building genuinely has no current inventory and must not match a search.
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
                    "earliest_available_date": fallback_available_date,
                    "model_ids": [],
                    "pricing_model": _detect_bucket_pricing(
                        description, city, beds, baths, fallback_rent
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
                    description, city, g["bedrooms"], g["bathrooms"], min_rent
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

    ``rent`` is always left numeric (scoring does ``rent <= budget``): the
    bucket's ``min_rent`` when priced, else ``max_rent``, else the building's
    original rent. The real bucket (including ``price_on_request``) is attached
    as ``matched_floorplan`` for the display layer. See decision D1.

    For ``per_person`` (by-the-bed) floorplans, ``min_rent`` is the per-bedroom
    share; matching/scoring stays on that per-bed price (students pay per bed),
    but ``matched_floorplan`` also carries ``per_bed_rent`` and an estimated
    ``whole_unit_rent`` (= per-bed × bedrooms) so the card can label it clearly.
    """
    rent = min_rent
    if rent is None:
        rent = max_rent
    if rent is None:
        rent = apt.get("rent")

    per_person = pricing_model == "per_person"
    per_bed_rent = min_rent if per_person else None
    whole_unit_rent = (
        min_rent * max(int(bedrooms), 1) if (per_person and min_rent is not None) else None
    )

    out = {**apt}
    out["rent"] = rent
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
