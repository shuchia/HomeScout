"""Ingestion invariants — does the data still look like data?

Every pipeline fault found in 2026 produced output that looked like data
rather than an error: an Akamai 403 read as "verified", a payload field that
moved read as "price on request", availability gated on a key single-unit
listings never carry read as "date unknown", a 100-row config cap read as
"this market only has 100 listings". /health stayed green through all of them,
and pipeline-health only asked whether work *happened*, not whether its output
was sane.

These tests pin the two properties that make the check worth having: the
ratios are actually reported (a response_model has silently eaten a new metric
here before), and drift is measured against a blessed baseline rather than the
previous run.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.routers.data_collection import (
    INVARIANT_STEP_PCT,
    MetricsResponse,
    _get_invariant_baseline,
)


class TestMetricsResponseDeclaresInvariants:
    """A response_model silently discards fields it does not declare. That has
    already happened once here, to floorplans."""

    def test_invariants_survives_serialisation(self):
        m = MetricsResponse(
            total_listings=1, active_listings=1, listings_by_source={},
            listings_by_city={}, avg_quality_score=1.0, jobs_last_24h=0,
            successful_jobs_last_24h=0, timestamp="now",
            invariants={"pct_listings_without_rent": 1.23},
        )
        assert m.model_dump()["invariants"]["pct_listings_without_rent"] == 1.23

    def test_invariants_defaults_empty_not_missing(self):
        m = MetricsResponse(
            total_listings=1, active_listings=1, listings_by_source={},
            listings_by_city={}, avg_quality_score=1.0, jobs_last_24h=0,
            successful_jobs_last_24h=0, timestamp="now",
        )
        assert m.model_dump()["invariants"] == {}


class TestBaselineIsExplicit:
    @pytest.mark.asyncio
    async def test_no_redis_means_no_baseline_not_an_error(self):
        """A missing baseline must degrade to 'no drift reported'. If it threw,
        the health check that exists to catch silent failure would itself fail
        silently."""
        with patch("app.routers.data_collection._invariant_redis",
                   AsyncMock(return_value=None)):
            assert await _get_invariant_baseline() is None

    @pytest.mark.asyncio
    async def test_unreadable_baseline_is_treated_as_absent(self):
        r = AsyncMock()
        r.get = AsyncMock(side_effect=Exception("redis down"))
        with patch("app.routers.data_collection._invariant_redis",
                   AsyncMock(return_value=r)):
            assert await _get_invariant_baseline() is None

    @pytest.mark.asyncio
    async def test_baseline_round_trips(self):
        stored = {"pct_listings_without_rent": 2.0, "_set_at": "2026-10-09T00:00:00Z"}
        r = AsyncMock()
        r.get = AsyncMock(return_value=json.dumps(stored))
        with patch("app.routers.data_collection._invariant_redis",
                   AsyncMock(return_value=r)):
            assert await _get_invariant_baseline() == stored


class TestStepThreshold:
    """The threshold has to catch the faults actually seen without firing on
    ordinary market movement."""

    def test_catches_the_faults_that_were_missed(self):
        # availability gap: ~56% of the corpus had no date
        assert abs(56.1 - 0.0) >= INVARIANT_STEP_PCT
        # rentLabel drove price-on-request buckets to 18%
        assert abs(18.0 - 4.0) >= INVARIANT_STEP_PCT

    def test_ignores_ordinary_week_to_week_movement(self):
        assert abs(12.4 - 11.1) < INVARIANT_STEP_PCT
        assert abs(4.9 - 5.2) < INVARIANT_STEP_PCT


class TestPerCityBaselines:
    """A global ratio cannot survive the corpus growing.

    Adding a market with a different character — more by-the-room listings,
    more price-on-request — shifts every global ratio at once. That both
    raises a false alarm and masks a real regression elsewhere at the same
    time. Per-city baselines are independent.
    """

    from app.routers.data_collection import _compare_invariants as _cmp

    def _current(self, cities):
        return {"overall": {"pct_listings_without_rent": 2.0}, "by_city": cities}

    def test_new_city_is_unblessed_not_a_problem(self):
        """Adding Austin must not fire an alert — it has no baseline, which is
        the expected state for a market that was just added."""
        from app.routers.data_collection import _compare_invariants

        problems = []
        current = self._current({
            "Boston": {"active_listings": 500, "pct_listings_without_rent": 2.0},
            "Austin": {"active_listings": 300, "pct_listings_without_rent": 44.0},
        })
        baseline = {
            "overall": {"pct_listings_without_rent": 2.0},
            "by_city": {"Boston": {"pct_listings_without_rent": 2.0}},
        }
        drift, unblessed = _compare_invariants(current, baseline, problems)
        assert unblessed == ["Austin"]
        assert problems == []
        assert "Austin" not in drift["by_city"]

    def test_existing_city_regression_still_caught_alongside_a_new_city(self):
        """The point of per-city: a new market must not drown out a real
        regression in an established one."""
        from app.routers.data_collection import _compare_invariants

        problems = []
        current = self._current({
            "Boston": {"active_listings": 500, "pct_listings_without_rent": 30.0},
            "Austin": {"active_listings": 300, "pct_listings_without_rent": 44.0},
        })
        baseline = {
            "overall": {},
            "by_city": {"Boston": {"pct_listings_without_rent": 2.0}},
        }
        drift, unblessed = _compare_invariants(current, baseline, problems)
        assert unblessed == ["Austin"]
        assert len(problems) == 1 and "Boston" in problems[0]
        assert drift["by_city"]["Boston"]["pct_listings_without_rent"]["delta"] == 28.0

    def test_small_city_is_not_judged_on_ratios(self):
        """A market with a handful of listings swings wildly on one row."""
        from app.routers.data_collection import _compare_invariants

        problems = []
        current = self._current({
            "Bryn Mawr": {"active_listings": 8, "pct_listings_without_rent": 50.0},
        })
        baseline = {"overall": {}, "by_city": {"Bryn Mawr": {"pct_listings_without_rent": 0.0}}}
        _compare_invariants(current, baseline, problems)
        assert problems == []

    def test_overall_drift_is_still_reported(self):
        from app.routers.data_collection import _compare_invariants

        problems = []
        current = {"overall": {"pct_listings_without_available_date": 56.0}, "by_city": {}}
        baseline = {"overall": {"pct_listings_without_available_date": 0.0}, "by_city": {}}
        drift, _ = _compare_invariants(current, baseline, problems)
        assert len(problems) == 1 and "overall" in problems[0]
        assert drift["overall"]["pct_listings_without_available_date"]["delta"] == 56.0

    def test_non_pct_fields_are_not_compared(self):
        """active_listings legitimately changes every sweep."""
        from app.routers.data_collection import _compare_invariants

        problems = []
        current = {"overall": {"active_listings": 9999}, "by_city": {}}
        baseline = {"overall": {"active_listings": 10}, "by_city": {}}
        _compare_invariants(current, baseline, problems)
        assert problems == []
