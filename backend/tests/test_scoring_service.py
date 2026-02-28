"""Tests for ScoringService heuristic scoring."""
import pytest
from datetime import datetime, timedelta
from app.services.scoring_service import ScoringService


class TestBudgetFitScore:
    """Budget fit component: 30% weight, 0-100 scale."""

    def test_rent_at_budget_returns_100(self):
        score = ScoringService.budget_fit_score(rent=2000, budget=2000)
        assert score == 100

    def test_rent_under_budget_returns_100(self):
        score = ScoringService.budget_fit_score(rent=1500, budget=2000)
        assert score == 100

    def test_rent_5_percent_over_returns_50(self):
        score = ScoringService.budget_fit_score(rent=2100, budget=2000)
        assert score == 50

    def test_rent_10_percent_over_returns_0(self):
        score = ScoringService.budget_fit_score(rent=2200, budget=2000)
        assert score == 0

    def test_rent_over_10_percent_returns_0(self):
        score = ScoringService.budget_fit_score(rent=2500, budget=2000)
        assert score == 0

    def test_rent_1_percent_over(self):
        score = ScoringService.budget_fit_score(rent=2020, budget=2000)
        assert 85 <= score <= 95


class TestFreshnessScore:
    """Freshness component: 20% weight, 0-100 scale."""

    def test_high_confidence_recent_returns_high(self):
        last_seen = datetime.utcnow() - timedelta(hours=6)
        score = ScoringService.freshness_score(
            freshness_confidence=90, last_seen_at=last_seen.isoformat()
        )
        assert score >= 85

    def test_low_confidence_old_returns_low(self):
        last_seen = datetime.utcnow() - timedelta(days=14)
        score = ScoringService.freshness_score(
            freshness_confidence=40, last_seen_at=last_seen.isoformat()
        )
        assert score <= 45

    def test_missing_data_returns_50(self):
        score = ScoringService.freshness_score(
            freshness_confidence=None, last_seen_at=None
        )
        assert score == 50


class TestDataQualityScore:
    """Data quality component: 15% weight, uses DB field directly."""

    def test_returns_db_score(self):
        score = ScoringService.data_quality_score(quality=85)
        assert score == 85

    def test_none_returns_50(self):
        score = ScoringService.data_quality_score(quality=None)
        assert score == 50

    def test_clamps_to_100(self):
        score = ScoringService.data_quality_score(quality=120)
        assert score == 100
