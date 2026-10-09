"""Canonical form for city names.

Separate from the NYC/Boston metro folds in ``apify_service``. Those answer
"which market is this listing in"; this answers "is this the same city string
we already use". Both are needed, and they are not the same question — a
listing can be in the right market and still be filed under a spelling nothing
else matches.

Measured on QA 2026-10-09: 95 distinct city strings collapsed to 91, with four
collision groups — ``SAN FRANCISCO``/``San Francisco``,
``Mc Kees Rocks``/``McKees Rocks``, ``Mt Lebanon``/``Mount Lebanon``,
``The Bronx``/``Bronx``. Only six rows were misfiled, but the ratio metrics,
comps and per-market medians are all keyed on this string, and the scraper
reproduces the variants on every sweep.

Deliberately conservative. Rules cover the variants actually observed plus
casing and whitespace; speculative expansions like ``St`` → ``Saint`` are left
out because the corpus has no such city and the canonical direction is
genuinely ambiguous (USPS writes "St Louis").
"""
from __future__ import annotations

import re
from typing import Optional

# Leading article. "The Bronx" and "Bronx" are one place.
_LEADING_ARTICLE = re.compile(r"^the\s+", re.IGNORECASE)

# "Mt Lebanon" / "Mt. Lebanon" -> "Mount Lebanon".
_ABBREVIATIONS = (
    (re.compile(r"^mt\.?\s+", re.IGNORECASE), "Mount "),
)

# "Mc Kees Rocks" -> "McKees Rocks". The space is a scraping artifact; no US
# place name separates Mc from what follows.
_MC_SPACED = re.compile(r"\bMc\s+([A-Z])")


def canonicalize_city(city: Optional[str]) -> Optional[str]:
    """Return the canonical spelling of a city name.

    Returns None for empty input so callers can distinguish "no city" from
    "a city that normalized to nothing".
    """
    if not city or not city.strip():
        return None

    out = re.sub(r"\s+", " ", city.strip())
    out = _LEADING_ARTICLE.sub("", out)

    # Only re-case when the input is uniformly cased. A blanket .title() would
    # turn "McKees Rocks" into "Mckees Rocks" — making the problem worse on
    # exactly the names that need care.
    if out.isupper() or out.islower():
        out = out.title()

    for pattern, replacement in _ABBREVIATIONS:
        out = pattern.sub(replacement, out)

    out = _MC_SPACED.sub(r"Mc\1", out)

    return out or None
