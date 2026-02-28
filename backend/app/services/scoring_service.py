"""Heuristic scoring engine for apartment search results.

Computes a 0-100 score for each apartment against search criteria
using weighted components: budget fit, freshness, data quality,
amenity match, and space fit. No AI calls — pure math.
"""


class ScoringService:
    """Stateless heuristic scoring for apartments."""

    @staticmethod
    def budget_fit_score(rent: int, budget: int) -> int:
        """Score how well rent fits the budget (0-100).

        100 if rent <= budget. Linear decay from 100 to 0
        across the 0-10% overshoot range. 0 if >10% over.
        """
        if budget <= 0:
            return 0
        if rent <= budget:
            return 100
        overshoot = (rent - budget) / budget
        if overshoot >= 0.10:
            return 0
        return int(100 * (1 - overshoot / 0.10))
