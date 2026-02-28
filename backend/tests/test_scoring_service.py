"""Tests for ScoringService heuristic scoring."""
import pytest
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
