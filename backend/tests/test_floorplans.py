"""Unit tests for floorplan bucket aggregation (app/services/floorplans.py).

Pure/synchronous — no DB, no network. The fixture mirrors the real Apify
`models` payload for Peninsula Apartments (Boston run zvpMrxcRyJrcJPbmm), the
building our search stored as a single studio while it actually offers a
3-bedroom under budget.

Runnable via pytest, or standalone (no pytest needed):
    python3 -m pytest tests/test_floorplans.py
    python3 -m tests.test_floorplans      # standalone runner, from backend/
"""

from app.services.floorplans import (
    build_floorplan_buckets,
    parse_available_units,
    parse_bedrooms,
    parse_rent,
    parse_sqft,
    project_matched_floorplan,
)


def _model(details, price, sqft, avail, model_id="m"):
    return {
        "modelId": model_id,
        "details": details,
        "totalPrice": price,
        "squareFeet": sqft,
        "availability": avail,
    }


# Trimmed but faithful slice of Peninsula's 34 floorplans.
PENINSULA = [
    _model(["Studio", "1 Bath"], "$2,762 - 2,871", "644", "3 Available units", "s1"),
    _model(["Studio", "1 Bath"], "Call for Rent", "469", "0 Available units", "s2"),
    _model(["1 Bed", "1 Bath"], "$2,504", "643", "1 Available units", "a1"),
    _model(["1 Bed", "1 Bath"], "$2,684 - 2,710", "698 - 741", "3 Available units", "a2"),
    _model(["1 Bed", "1 Bath"], "Call for Rent", "643", "0 Available units", "a3"),
    _model(["2 Beds", "2 Baths"], "$3,497 - 3,773", "968", "2 Available units", "b1"),
    _model(["2 Beds", "1 Bath"], "$3,766", "974", "1 Available units", "b2"),
    _model(["3 Beds", "2 Baths"], "$4,624 - 4,952", "1,444", "3 Available units", "c1"),
    _model(["3 Beds", "2 Baths"], "Call for Rent", "1,233", "0 Available units", "c2"),
    # Price-on-request but genuinely available (decision D1):
    _model(["3 Beds", "3 Baths"], "Call for Rent", "1,600", "1 Available units", "c3"),
]


def _bucket(buckets, beds, baths):
    for b in buckets:
        if b["bedrooms"] == beds and b["bathrooms"] == baths:
            return b
    return None


def test_parse_helpers():
    assert parse_rent("$4,624 - 4,952") == 4624
    assert parse_rent("$2,504") == 2504
    assert parse_rent("Call for Rent") is None
    assert parse_rent(None) is None
    assert parse_bedrooms("Studio") == 0
    assert parse_bedrooms("3 Beds") == 3
    assert parse_bedrooms("1 Bed") == 1
    assert parse_sqft("698 - 741") == 698
    assert parse_sqft("1,444") == 1444
    assert parse_available_units("3 Available units") == 3
    assert parse_available_units("0 Available units") == 0


def test_three_bedroom_surfaces_under_budget():
    """The whole point: Peninsula's available 3BR at $4,624 must appear."""
    buckets = build_floorplan_buckets(PENINSULA)
    b3 = _bucket(buckets, 3, 2.0)
    assert b3 is not None
    assert b3["min_rent"] == 4624
    assert b3["max_rent"] == 4952
    assert b3["available_units"] == 3
    assert b3["min_sqft"] == 1444


def test_zero_available_floorplans_skipped():
    """0-available units never inflate counts or set a price."""
    buckets = build_floorplan_buckets(PENINSULA)
    # 1BR: only the two available models (1 + 3 units); the call-for-rent
    # 0-available one is skipped, so min_rent is the real $2,504, not null.
    b1 = _bucket(buckets, 1, 1.0)
    assert b1["available_units"] == 4
    assert b1["min_rent"] == 2504
    # The 3BR/2BA call-for-rent model (c2) is 0-available → excluded, so the
    # 3BR/2BA bucket stays priced at 4624 (not turned into price-on-request).
    assert _bucket(buckets, 3, 2.0)["min_rent"] == 4624


def test_price_on_request_bucket():
    """A Call-for-Rent floorplan WITH availability → bucket with null rent (D1)."""
    buckets = build_floorplan_buckets(PENINSULA)
    b = _bucket(buckets, 3, 3.0)
    assert b is not None
    assert b["min_rent"] is None
    assert b["available_units"] == 1


def test_bucket_shape_and_studio():
    buckets = build_floorplan_buckets(PENINSULA)
    # Distinct (beds, baths): studio/1, 1BR/1, 2BR/2, 2BR/1, 3BR/2, 3BR/3.
    keys = {(b["bedrooms"], b["bathrooms"]) for b in buckets}
    assert keys == {(0, 1.0), (1, 1.0), (2, 2.0), (2, 1.0), (3, 2.0), (3, 3.0)}
    assert _bucket(buckets, 0, 1.0)["available_units"] == 3


def test_no_models_uses_building_fallback():
    """Non-apartments.com sources (no models) get one implicit bucket."""
    buckets = build_floorplan_buckets(
        None,
        fallback_bedrooms=2,
        fallback_bathrooms=1.0,
        fallback_rent=1800,
        fallback_sqft=850,
    )
    assert len(buckets) == 1
    b = buckets[0]
    assert (b["bedrooms"], b["bathrooms"], b["min_rent"], b["available_units"]) == (2, 1.0, 1800, 1)


def test_models_present_but_none_available_returns_empty():
    """A building whose every floorplan is 0-available must NOT get a phantom
    bucket — nothing is rentable, so it should match no search."""
    all_unavail = [
        _model(["Studio", "1 Bath"], "Call for Rent", "500", "0 Available units", "z1"),
        _model(["2 Beds", "1 Bath"], "Call for Rent", "900", "0 Available units", "z2"),
    ]
    buckets = build_floorplan_buckets(
        all_unavail, fallback_bedrooms=0, fallback_rent=2000
    )
    assert buckets == []


def test_availability_date_from_rentals():
    models = [_model(["3 Beds", "2 Baths"], "$4,624", "1,444", "2 Available units", "c1")]
    rentals = [
        {"modelId": "c1", "availableDate": "2026-06-01T00:00:00-04:00"},
        {"modelId": "c1", "availableDate": "2026-08-15T00:00:00-04:00"},
    ]
    buckets = build_floorplan_buckets(models, rentals, today="2026-07-16")
    # Earliest upcoming (>= today) is 2026-08-15; the June date is past.
    assert buckets[0]["earliest_available_date"] == "2026-08-15"


# ── Phase 2: projection of a matched floorplan onto the building dict ──

# A building stored (collapsed) as a studio — what to_summary_dict() returns.
BUILDING = {"id": "q3c2q7z", "rent": 2150, "bedrooms": 0, "bathrooms": 1, "sqft": 398}


def test_projection_overrides_to_matched_floorplan():
    """A 3BR match must present the 3BR's rent/beds, not the studio's."""
    out = project_matched_floorplan(
        BUILDING, bedrooms=3, bathrooms=2.0,
        min_rent=4624, max_rent=4952, min_sqft=1444, max_sqft=1444,
        available_units=3, earliest_available_date="2026-08-01",
    )
    assert out["rent"] == 4624
    assert out["bedrooms"] == 3
    assert out["bathrooms"] == 2
    assert out["sqft"] == 1444
    assert out["price_on_request"] is False
    assert out["matched_floorplan"]["max_rent"] == 4952
    assert out["matched_floorplan"]["available_units"] == 3
    # Building identity preserved.
    assert out["id"] == "q3c2q7z"


def test_projection_does_not_mutate_input():
    project_matched_floorplan(BUILDING, bedrooms=3, bathrooms=2.0,
                              min_rent=4624, max_rent=4952, min_sqft=1444,
                              max_sqft=1444)
    assert BUILDING["bedrooms"] == 0 and BUILDING["rent"] == 2150


def test_projection_price_on_request_keeps_rent_numeric():
    """Null min_rent (D1) must still yield a numeric rent so scoring's
    ``rent <= budget`` never hits None; falls back max_rent → building rent."""
    # max_rent present → use it.
    out = project_matched_floorplan(BUILDING, bedrooms=3, bathrooms=2.0,
                                    min_rent=None, max_rent=5200, min_sqft=1400,
                                    max_sqft=1400, available_units=1)
    assert out["rent"] == 5200
    assert out["price_on_request"] is True
    assert out["matched_floorplan"]["min_rent"] is None
    # No prices at all → fall back to the building's own rent (never None).
    out2 = project_matched_floorplan(BUILDING, bedrooms=3, bathrooms=2.0,
                                     min_rent=None, max_rent=None, min_sqft=None,
                                     max_sqft=None, available_units=1)
    assert out2["rent"] == 2150
    assert isinstance(out2["rent"], int)


def test_projection_half_bath_preserved():
    out = project_matched_floorplan(BUILDING, bedrooms=2, bathrooms=1.5,
                                    min_rent=3000, max_rent=3000, min_sqft=900,
                                    max_sqft=900)
    assert out["bathrooms"] == 1.5


if __name__ == "__main__":
    # Standalone runner so the suite works even when pytest mis-collects the
    # tests package. Runs every test_* function in this module.
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:  # noqa: BLE001
            failures += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns) - failures}/{len(fns)} passed")
    raise SystemExit(1 if failures else 0)
