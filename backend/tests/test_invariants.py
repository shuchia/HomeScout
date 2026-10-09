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
