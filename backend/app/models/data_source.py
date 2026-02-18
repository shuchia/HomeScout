"""
SQLAlchemy ORM model for data source configuration.
"""
from sqlalchemy import Column, String, Integer, DateTime, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class DataSourceModel(Base):
    """
    ORM model for data source configuration.

    Stores configuration for each data source (Zillow, Apartments.com, etc.)
    including API keys, rate limits, and scraping settings.
    """
    __tablename__ = "data_sources"

    # Primary key
    id = Column(String(50), primary_key=True)  # e.g., "zillow", "apartments_com"

    # Display information
    name = Column(String(100), nullable=False)  # Human-readable name
    description = Column(Text, nullable=True)

    # Status
    is_enabled = Column(Boolean, default=True)
    is_healthy = Column(Boolean, default=True)

    # Provider configuration
    provider = Column(String(50), nullable=False)  # apify, scrapingbee, direct
    provider_config = Column(JSONB, nullable=True)  # Provider-specific settings
    # e.g., {"actor_id": "maxcopell/zillow-scraper", "max_items": 1000}

    # Rate limiting
    rate_limit_per_hour = Column(Integer, default=100)
    rate_limit_per_day = Column(Integer, default=1000)
    current_hour_calls = Column(Integer, default=0)
    current_day_calls = Column(Integer, default=0)
    rate_limit_reset_hour = Column(DateTime(timezone=True), nullable=True)
    rate_limit_reset_day = Column(DateTime(timezone=True), nullable=True)

    # Scheduling
    scrape_frequency_hours = Column(Integer, default=24)  # How often to scrape
    last_scrape_at = Column(DateTime(timezone=True), nullable=True)
    next_scrape_at = Column(DateTime(timezone=True), nullable=True)

    # Quality metrics
    total_listings_scraped = Column(Integer, default=0)
    successful_scrapes = Column(Integer, default=0)
    failed_scrapes = Column(Integer, default=0)
    average_data_quality = Column(Integer, default=0)  # 0-100

    # Cost tracking
    cost_per_listing_cents = Column(Integer, default=0)
    total_cost_cents = Column(Integer, default=0)
    monthly_budget_cents = Column(Integer, default=0)  # 0 = unlimited
    current_month_cost_cents = Column(Integer, default=0)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self) -> dict:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_enabled": self.is_enabled,
            "is_healthy": self.is_healthy,
            "provider": self.provider,
            "rate_limits": {
                "per_hour": self.rate_limit_per_hour,
                "per_day": self.rate_limit_per_day,
                "current_hour": self.current_hour_calls,
                "current_day": self.current_day_calls,
            },
            "schedule": {
                "frequency_hours": self.scrape_frequency_hours,
                "last_scrape_at": self.last_scrape_at.isoformat() if self.last_scrape_at else None,
                "next_scrape_at": self.next_scrape_at.isoformat() if self.next_scrape_at else None,
            },
            "metrics": {
                "total_listings_scraped": self.total_listings_scraped,
                "successful_scrapes": self.successful_scrapes,
                "failed_scrapes": self.failed_scrapes,
                "average_data_quality": self.average_data_quality,
            },
            "cost": {
                "per_listing_cents": self.cost_per_listing_cents,
                "total_cents": self.total_cost_cents,
                "monthly_budget_cents": self.monthly_budget_cents,
                "current_month_cents": self.current_month_cost_cents,
            },
        }

    def can_make_request(self) -> bool:
        """Check if rate limits allow another request."""
        if not self.is_enabled:
            return False

        # Check monthly budget
        if self.monthly_budget_cents > 0 and self.current_month_cost_cents >= self.monthly_budget_cents:
            return False

        # Check rate limits
        if self.current_hour_calls >= self.rate_limit_per_hour:
            return False
        if self.current_day_calls >= self.rate_limit_per_day:
            return False

        return True

    def __repr__(self):
        return f"<DataSource {self.id}: {self.name}>"
