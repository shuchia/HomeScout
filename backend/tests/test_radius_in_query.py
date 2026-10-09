"""Radius applied before pagination, not after.

The filter used to run on the ten rows already selected by score, so "within
5 miles of Fenway" meant "whichever of the top ten happen to qualify". A real
QA search returned *zero* results out of 35 matches, and has_more was forced
False because paging a post-filtered slice is meaningless — so there was no
way to reach the listings that did qualify.
"""
import math

import pytest

from app.services.distance import bounding_box, haversine_miles

FENWAY = (42.3467, -71.0972)


class TestBoundingBox:
    """The box is a SQL prefilter. It must never be tighter than the circle,
    or listings near the edge vanish before the exact check ever sees them."""

    def test_contains_points_at_the_radius(self):
        lat, lng = FENWAY
        min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, 5)
        # due north, south, east, west at ~5 miles
        for plat, plng in [
            (lat + 5 / 69.0, lng),
            (lat - 5 / 69.0, lng),
            (lat, lng + 5 / (69.0 * math.cos(math.radians(lat)))),
            (lat, lng - 5 / (69.0 * math.cos(math.radians(lat)))),
        ]:
            assert min_lat <= plat <= max_lat
            assert min_lng <= plng <= max_lng

    def test_is_a_superset_not_the_circle(self):
        """The corners sit ~1.4x the radius out, which is why the exact
        haversine still has to run afterwards."""
        lat, lng = FENWAY
        _, max_lat, _, max_lng = bounding_box(lat, lng, 5)
        assert haversine_miles(lat, lng, max_lat, max_lng) > 5

    def test_widens_with_latitude(self):
        """A degree of longitude shrinks toward the poles, so the box must get
        wider in degrees to cover the same miles."""
        _, _, lo_min, lo_max = bounding_box(25.0, 0.0, 10)
        _, _, hi_min, hi_max = bounding_box(65.0, 0.0, 10)
        assert (hi_max - hi_min) > (lo_max - lo_min)

    def test_does_not_blow_up_at_the_pole(self):
        box = bounding_box(89.999, 0.0, 10)
        assert all(math.isfinite(v) for v in box)


class TestBboxPredicates:
    def test_no_near_yields_no_predicates(self):
        """Callers splat this unconditionally, so it must be empty, not None."""
        from app.services.apartment_service import ApartmentService

        assert ApartmentService._bbox_predicates(None) == ()

    def test_near_yields_coordinate_predicates(self):
        from app.services.apartment_service import ApartmentService

        preds = ApartmentService._bbox_predicates((*FENWAY, 5))
        # not-null lat, not-null lng, lat between, lng between
        assert len(preds) == 4


class TestCacheKeySeparatesRadius:
    """A radius search and an unfiltered one over the same city are different
    result sets. Sharing a cache entry would serve one as the other."""

    @pytest.mark.asyncio
    async def test_radius_changes_the_cache_key(self, monkeypatch):
        from app.services.apartment_service import ApartmentService

        svc = ApartmentService.__new__(ApartmentService)
        svc._redis = None
        svc._use_database = True

        seen = []

        async def _fake_search(**kwargs):
            seen.append(kwargs.get("near"))
            return []

        monkeypatch.setattr(svc, "search_apartments", _fake_search)

        common = dict(
            city="Boston, MA", budget=3000, bedrooms=1, bathrooms=1,
            property_type="Apartment", move_in_date="2026-11-01",
        )
        await svc.get_apartments_paginated(**common)
        await svc.get_apartments_paginated(**common, near=(*FENWAY, 5))

        assert seen == [None, (*FENWAY, 5)]


class TestCoordinatelessRowsUnderARadius:
    """A listing with no coordinates cannot satisfy "within N miles".

    add_distances appended these *after* the distance check, so they survived
    a radius filter untouched. The SQL already excludes them in DB mode, but
    the function has to be correct on its own: JSON mode has no query behind
    it, and a helper that quietly defeats its own filter is a trap.
    """

    def _rows(self):
        return [
            {"id": "near", "latitude": 42.3467, "longitude": -71.0972},
            {"id": "far", "latitude": 42.9, "longitude": -71.9},
            {"id": "nocoords", "latitude": None, "longitude": None},
        ]

    def test_dropped_when_a_radius_is_set(self):
        from app.services.distance import add_distances

        out = add_distances(self._rows(), *FENWAY, 5)
        assert [a["id"] for a in out] == ["near"]

    def test_kept_when_no_radius_is_set(self):
        """Without a radius this is pure annotation — nothing should vanish."""
        from app.services.distance import add_distances

        out = add_distances(self._rows(), *FENWAY, None)
        assert {a["id"] for a in out} == {"near", "far", "nocoords"}
        assert next(a for a in out if a["id"] == "nocoords")["distance_miles"] is None
