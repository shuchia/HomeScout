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


def test_fully_leased_building_still_gets_buckets_marked_zero():
    """A building with no current inventory is shown, not hidden.

    It used to return no buckets at all, which made it invisible to search —
    124 active QA listings, 8% of the corpus. A building that fits someone's
    criteria is worth knowing about even when fully leased: you can call, join
    a waitlist, or check back. available_units = 0 is what marks it, and the
    search orders those behind anything rentable.
    """
    all_unavail = [
        _model(["Studio", "1 Bath"], "$2,400", "500", "0 Available units", "z1"),
        _model(["2 Beds", "1 Bath"], "$3,100", "900", "0 Available units", "z2"),
    ]
    buckets = build_floorplan_buckets(
        all_unavail, fallback_bedrooms=0, fallback_rent=2000
    )
    assert len(buckets) == 2
    assert all(b["available_units"] == 0 for b in buckets)
    # Real prices survive, so the card and budget filter still work.
    assert _bucket(buckets, 2, 1.0)["min_rent"] == 3100


def test_partially_available_building_ignores_the_leased_floorplans():
    """The zero-unit path only fires when nothing at all is available.

    A building with one rentable floorplan must not pick up phantom buckets for
    its leased ones — those would compete with real inventory.
    """
    mixed = [
        _model(["Studio", "1 Bath"], "$2,400", "500", "0 Available units", "m1"),
        _model(["2 Beds", "1 Bath"], "$3,100", "900", "2 Available units", "m2"),
    ]
    buckets = build_floorplan_buckets(mixed, fallback_bedrooms=0, fallback_rent=2000)
    assert len(buckets) == 1
    assert buckets[0]["bedrooms"] == 2
    assert buckets[0]["available_units"] == 2


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


def test_projection_uses_max_rent_when_min_is_missing():
    """max_rent is a real price for this bucket, so `rent` may carry it."""
    out = project_matched_floorplan(BUILDING, bedrooms=3, bathrooms=2.0,
                                    min_rent=None, max_rent=5200, min_sqft=1400,
                                    max_sqft=1400, available_units=1)
    assert out["rent"] == 5200
    assert out["rent_for_scoring"] == 5200
    assert out["price_on_request"] is True
    assert out["matched_floorplan"]["min_rent"] is None


def test_projection_never_passes_off_the_building_rent_as_a_price():
    """The contract this replaced.

    `rent` used to fall back to the building's collapsed studio rent so
    scoring's `rent <= budget` always had a number. Every consumer that read
    `rent` as a price then published a figure the property never quoted — a
    card showing "Price on request" above "Est. True Cost $2,700/mo", and AI
    reasoning asserting "$3,390 advertised rent" on an unpriced listing.

    So `rent` is now None when the bucket has no price, and the fallback moved
    to `rent_for_scoring`. A consumer wanting something displayable gets None
    and must decide what to do about it.
    """
    out = project_matched_floorplan(BUILDING, bedrooms=3, bathrooms=2.0,
                                    min_rent=None, max_rent=None, min_sqft=None,
                                    max_sqft=None, available_units=1)
    assert out["rent"] is None, "the building's rent must not masquerade as the bucket's"
    assert out["price_on_request"] is True

    # Scoring still gets a number — that was the point of the fallback.
    assert out["rent_for_scoring"] == 2150
    assert isinstance(out["rent_for_scoring"], int)


def test_priced_bucket_sets_both_fields_the_same():
    out = project_matched_floorplan(BUILDING, bedrooms=2, bathrooms=1.0,
                                    min_rent=3100, max_rent=3400, min_sqft=800,
                                    max_sqft=850, available_units=2)
    assert out["rent"] == 3100
    assert out["rent_for_scoring"] == 3100
    assert out["price_on_request"] is False


def test_projection_half_bath_preserved():
    out = project_matched_floorplan(BUILDING, bedrooms=2, bathrooms=1.5,
                                    min_rent=3000, max_rent=3000, min_sqft=900,
                                    max_sqft=900)
    assert out["bathrooms"] == 1.5


# ── Per-bedroom (by-the-bed) pricing ──

def test_bucket_detects_per_person_from_description():
    """A by-the-bed 3BR description → the 3BR bucket is flagged per_person,
    even though the building is stored collapsed as a studio."""
    models = [
        _model(["Studio", "1 Bath"], "$1,769", "236", "2 Available units", "s1"),
        _model(["3 Beds", "3 Baths"], "$1,792", "236", "3 Available units", "c1"),
    ]
    buckets = build_floorplan_buckets(
        models, description="Off-campus student housing leased by the bed.",
        city="Boston",
    )
    b3 = _bucket(buckets, 3, 3.0)
    assert b3["pricing_model"] == "per_person"
    # Studio bucket is never per-person.
    assert _bucket(buckets, 0, 1.0)["pricing_model"] == "per_unit"


def test_bucket_per_unit_without_signals():
    models = [_model(["3 Beds", "2 Baths"], "$4,624", "1,444", "2 Available units", "c1")]
    buckets = build_floorplan_buckets(
        models, description="Spacious 3 bedroom luxury apartment.", city="Boston",
    )
    assert _bucket(buckets, 3, 2.0)["pricing_model"] == "per_unit"


def test_projection_per_person_exposes_per_bed_and_whole_unit():
    """Per-person 3BR: matching/scoring stays on the $1,792 per-bed price, but
    the card gets per_bed_rent + whole_unit_rent (1792×3) for labeling."""
    out = project_matched_floorplan(
        BUILDING, bedrooms=3, bathrooms=3.0,
        min_rent=1792, max_rent=1792, min_sqft=236, max_sqft=236,
        pricing_model="per_person",
    )
    # rent stays the per-bed price (decision: keep per-bed matching).
    assert out["rent"] == 1792
    assert out["pricing_model"] == "per_person"
    mf = out["matched_floorplan"]
    assert mf["pricing_model"] == "per_person"
    assert mf["per_bed_rent"] == 1792
    assert mf["whole_unit_rent"] == 1792 * 3


def test_projection_per_unit_has_no_per_bed_fields():
    out = project_matched_floorplan(
        BUILDING, bedrooms=3, bathrooms=2.0,
        min_rent=4624, max_rent=4952, min_sqft=1444, max_sqft=1444,
        pricing_model="per_unit",
    )
    mf = out["matched_floorplan"]
    assert mf["pricing_model"] == "per_unit"
    assert mf["per_bed_rent"] is None
    assert mf["whole_unit_rent"] is None


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


class TestRentLabelPayloadShape:
    """apartments.com emits two model shapes; the actor passes through whichever
    the property page uses.

    Reading only totalPrice/basePrice turned every newly-captured priced
    floorplan into "price on request". Measured on QA 2026-10-03: 38 of 781
    models (4.9%) carried a price *only* in rentLabel, and zero models were
    genuinely unpriced — so every price-on-request card in that sample was a
    parse failure, not a property withholding a price.
    """

    def test_rent_label_is_read(self):
        from app.services.floorplans import build_floorplan_buckets

        buckets = build_floorplan_buckets([
            {
                "modelId": "7z0mc3z",
                "details": ["1 Bed", "1 Bath"],
                "rentLabel": "$4,188",
                "squareFeet": "631",
                "availability": "1 Available units",
            },
        ])
        assert len(buckets) == 1
        assert buckets[0]["min_rent"] == 4188
        assert buckets[0]["max_rent"] == 4188

    def test_rent_label_range(self):
        from app.services.floorplans import build_floorplan_buckets

        buckets = build_floorplan_buckets([
            {
                "modelId": "m1",
                "details": ["Studio", "1 Bath"],
                "rentLabel": "$3,500 - 3,630",
                "availability": "2 Available units",
            },
        ])
        assert buckets[0]["min_rent"] == 3500
        assert buckets[0]["max_rent"] == 3630

    def test_old_fields_still_win(self):
        """A payload carrying both must keep the established precedence."""
        from app.services.floorplans import model_price

        low, high = model_price(
            {"totalPrice": "$2,000", "basePrice": "$2,100", "rentLabel": "$9,999"}
        )
        assert (low, high) == (2000, 2000)

    def test_genuinely_unpriced_stays_unpriced(self):
        """"Call for Rent" in any field must remain price-on-request — the whole
        point is that unknown and unread stop being the same thing."""
        from app.services.floorplans import build_floorplan_buckets

        buckets = build_floorplan_buckets([
            {
                "modelId": "m1",
                "details": ["2 Beds", "2 Baths"],
                "rentLabel": "Call for Rent",
                "availability": "1 Available units",
            },
        ])
        assert buckets[0]["min_rent"] is None

    def test_rent_label_on_fully_leased_building(self):
        """The zero-available path parses prices too, or a fully-leased building
        in the new format shows no price at all."""
        from app.services.floorplans import build_floorplan_buckets

        buckets = build_floorplan_buckets([
            {
                "modelId": "m1",
                "details": ["1 Bed", "1 Bath"],
                "rentLabel": "$2,750",
                "availability": "0 Available units",
            },
        ])
        assert len(buckets) == 1
        assert buckets[0]["available_units"] == 0
        assert buckets[0]["min_rent"] == 2750


class TestRentalsWithoutModels:
    """Single-unit and by-the-room listings publish no `models` at all.

    Their rental objects are keyed by `key`, not `modelId`, so the model join
    can never reach them. 9 Hancock St carried availableDate 2026-11-01 while
    the card said availability could not be found.
    """

    HANCOCK = [{
        "key": "zehmbdy",
        "beds": 1,
        "baths": 1,
        "details": ["1 Bed", "1 Bath"],
        "basePrice": 1625,
        "totalPrice": 1625,
        "unitCount": 1,
        "squareFeet": 1100,
        "availability": "11/01/26",
        "availableDate": "2026-11-01T00:00:00-04:00",
    }]

    def test_rental_dates_needs_no_model_id(self):
        from app.services.floorplans import rental_dates

        assert rental_dates(self.HANCOCK) == ["2026-11-01"]

    def test_fallback_bucket_gets_the_date(self):
        from app.services.floorplans import build_floorplan_buckets

        buckets = build_floorplan_buckets(
            [],                      # no models — the whole point
            self.HANCOCK,
            fallback_bedrooms=1,
            fallback_bathrooms=1.0,
            fallback_rent=1625,
            fallback_available_date=None,
            today="2026-10-03",
        )
        assert len(buckets) == 1
        assert buckets[0]["earliest_available_date"] == "2026-11-01"

    def test_explicit_fallback_date_still_wins(self):
        from app.services.floorplans import build_floorplan_buckets

        buckets = build_floorplan_buckets(
            [], self.HANCOCK,
            fallback_bedrooms=1, fallback_bathrooms=1.0, fallback_rent=1625,
            fallback_available_date="2026-10-15", today="2026-10-03",
        )
        assert buckets[0]["earliest_available_date"] == "2026-10-15"

    def test_no_rentals_no_date(self):
        from app.services.floorplans import earliest_rental_date

        assert earliest_rental_date(None) is None
        assert earliest_rental_date([]) is None
        assert earliest_rental_date([{"key": "x"}]) is None
