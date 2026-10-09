"""Canonical city spelling.

Distinct from the NYC and Boston metro folds, which decide *which market* a
listing belongs to. This decides whether two rows use the same string for the
same place — a listing can be in the right market and still be filed under a
spelling nothing else matches.

Measured on QA 2026-10-09: 95 distinct city strings collapsing to 91, with
four collision groups. Six rows, but every per-market metric, comp and median
keys on this string.
"""
from app.services.normalization.city_names import canonicalize_city


class TestObservedCollisions:
    """The four groups actually found in the corpus."""

    def test_uppercase_folds_to_title(self):
        assert canonicalize_city("SAN FRANCISCO") == "San Francisco"

    def test_mc_spacing(self):
        assert canonicalize_city("Mc Kees Rocks") == "McKees Rocks"

    def test_mt_expands(self):
        assert canonicalize_city("Mt Lebanon") == "Mount Lebanon"
        assert canonicalize_city("Mt. Lebanon") == "Mount Lebanon"

    def test_leading_article_dropped(self):
        assert canonicalize_city("The Bronx") == "Bronx"

    def test_each_group_converges(self):
        for a, b in [
            ("SAN FRANCISCO", "San Francisco"),
            ("Mc Kees Rocks", "McKees Rocks"),
            ("Mt Lebanon", "Mount Lebanon"),
            ("The Bronx", "Bronx"),
        ]:
            assert canonicalize_city(a) == canonicalize_city(b)


class TestDoesNotMakeThingsWorse:
    """The failure mode to avoid is over-normalizing. A blanket .title() turns
    "McKees Rocks" into "Mckees Rocks" — breaking exactly the names that need
    care."""

    def test_mixed_case_is_left_alone(self):
        assert canonicalize_city("McKees Rocks") == "McKees Rocks"
        assert canonicalize_city("DeWitt") == "DeWitt"

    def test_already_canonical_is_unchanged(self):
        for c in ["San Francisco", "New York", "State College", "Bryn Mawr",
                  "Mount Lebanon", "Bronx", "Boston"]:
            assert canonicalize_city(c) == c

    def test_idempotent(self):
        for c in ["SAN FRANCISCO", "Mc Kees Rocks", "Mt Lebanon", "The Bronx"]:
            once = canonicalize_city(c)
            assert canonicalize_city(once) == once

    def test_saint_is_deliberately_not_expanded(self):
        """Left out on purpose: the corpus has no such city and the canonical
        direction is genuinely ambiguous (USPS writes "St Louis")."""
        assert canonicalize_city("St Louis") == "St Louis"


class TestEmptyAndWhitespace:
    def test_empty_is_none(self):
        assert canonicalize_city("") is None
        assert canonicalize_city("   ") is None
        assert canonicalize_city(None) is None

    def test_internal_whitespace_collapsed(self):
        assert canonicalize_city("  new   york  ") == "New York"
