"""
SQLAlchemy ORM model for market configuration.
Drives the scraping schedule — one row per city/market.
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.sql import func

from app.database import Base


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
    def decay_rate(self) -> int:
        """Confidence points lost per hour based on tier."""
        rates = {"hot": 3, "standard": 2, "cool": 1}
        return rates.get(self.tier, 1)

    def __repr__(self):
        return f"<Market {self.id}: {self.display_name} ({self.tier})>"
