"""
SQLAlchemy ORM model for market configuration.
Drives the scraping schedule — one row per city/market.
"""
import os

from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.sql import func

from app.database import Base

# Confidence points lost per hour, by market tier.
#
# A listing enters at 100 and is hidden from search once it drops below
# SEARCH_FLOOR (40, see apartments.py). So the rate is really a statement about
# how long we are willing to keep showing a listing we have not re-seen.
#
# These used to be 3/2/1 per hour, which hid hot-tier listings 20 hours after a
# scrape and deactivated them at 33 hours. That made the whole product
# load-bearing on scrape uptime — two silent pipeline outages took search down
# with them — and it was never justified by the data: rental listings stay on
# the market for weeks, not hours.
#
# It is also unreachable in practice. The bulk scrape has no pagination, so it
# only ever re-sees the same ~100 listings per market. A market holding 338 rows
# can refresh at most ~100 of them per run; the rest can never have their
# freshness reset no matter how often we scrape. Aggressive decay therefore does
# not expire stale listings, it deletes the corpus.
#
# Rates below are derived from "days until a listing falls below the search
# floor": (100 - 40) / (days * 24).
# Recalibrated 2026-09-25 for weekly sweeps. At the previous 7/10/14 days a
# hot-tier market scraped weekly reached the search floor at the exact moment
# its next sweep was due — any delay dropped the market out of search. These
# give roughly three missed sweeps of headroom.
#
# The corpus's job is now comps and reference data, where a listing that
# vanished a fortnight ago still carries price signal. The sharper test for "is
# this listing gone" is absence from a sweep that exhausted its market, which is
# now possible since a sweep returns the complete market (measured: State
# College 102, Boston 700, both exhausting below maxItems). Decay is the
# fallback for when a sweep fails, not the primary signal.
_DAYS_TO_SEARCH_FLOOR = {
    "hot": float(os.getenv("DECAY_DAYS_HOT", "21")),
    "standard": float(os.getenv("DECAY_DAYS_STANDARD", "28")),
    "cool": float(os.getenv("DECAY_DAYS_COOL", "35")),
}
SEARCH_FLOOR = 40

TIER_DECAY_RATES = {
    tier: (100 - SEARCH_FLOOR) / (days * 24)
    for tier, days in _DAYS_TO_SEARCH_FLOOR.items()
}
DEFAULT_DECAY_RATE = TIER_DECAY_RATES["cool"]


class MarketConfigModel(Base):
    """
    Configuration for a scraping market (city).
    The dispatcher queries this table hourly to decide what to scrape.
    """
    __tablename__ = "market_configs"

    id = Column(String(50), primary_key=True)  # e.g. "nyc", "philadelphia"
    display_name = Column(String(200), nullable=False)
    city = Column(String(100), nullable=False)
    state = Column(String(10), nullable=False)
    tier = Column(String(20), nullable=False, default="cool")  # hot, standard, cool
    is_enabled = Column(Boolean, nullable=False, default=True)
    max_listings_per_scrape = Column(Integer, nullable=False, default=100)
    scrape_frequency_hours = Column(Integer, nullable=False, default=24)
    last_scrape_at = Column(DateTime(timezone=True), nullable=True)
    last_scrape_status = Column(String(20), nullable=True)  # completed, failed, partial
    consecutive_failures = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Decay rate per hour for freshness confidence
    @property
    def decay_rate(self) -> float:
        """Confidence points lost per hour based on tier."""
        return TIER_DECAY_RATES.get(self.tier, DEFAULT_DECAY_RATE)

    def __repr__(self):
        return f"<Market {self.id}: {self.display_name} ({self.tier})>"
