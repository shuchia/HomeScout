"""
SQLAlchemy ORM model for tracking scrape jobs.
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class ScrapeJobModel(Base):
    """
    ORM model for tracking scraping job status and metrics.
    """
    __tablename__ = "scrape_jobs"

    # Primary key
    id = Column(String(50), primary_key=True)  # UUID

    # Job identification
    source = Column(String(50), nullable=False)  # zillow, apartments_com, craigslist
    job_type = Column(String(50), nullable=False, default="full")  # full, incremental, targeted

    # Target parameters
    city = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    search_params = Column(JSONB, nullable=True)  # Additional search parameters

    # Status tracking
    status = Column(String(20), nullable=False, default="pending")
    # pending, running, completed, failed, cancelled

    # Timing
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Metrics
    listings_found = Column(Integer, default=0)  # Total listings scraped
    listings_new = Column(Integer, default=0)  # New listings added
    listings_updated = Column(Integer, default=0)  # Existing listings updated
    listings_duplicates = Column(Integer, default=0)  # Duplicates detected
    listings_errors = Column(Integer, default=0)  # Listings with errors

    # Error handling
    error_message = Column(Text, nullable=True)
    error_details = Column(JSONB, nullable=True)

    # External job reference (e.g., Apify run ID)
    external_job_id = Column(String(255), nullable=True)
    external_job_url = Column(Text, nullable=True)

    # Cost tracking
    api_calls_made = Column(Integer, default=0)
    estimated_cost_usd = Column(Integer, default=0)  # Stored as cents

    # Indexes
    __table_args__ = (
        Index('idx_scrape_jobs_status', 'status'),
        Index('idx_scrape_jobs_source', 'source'),
        Index('idx_scrape_jobs_created_at', 'created_at'),
    )

    def to_dict(self) -> dict:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "source": self.source,
            "job_type": self.job_type,
            "city": self.city,
            "state": self.state,
            "search_params": self.search_params,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metrics": {
                "listings_found": self.listings_found,
                "listings_new": self.listings_new,
                "listings_updated": self.listings_updated,
                "listings_duplicates": self.listings_duplicates,
                "listings_errors": self.listings_errors,
            },
            "error_message": self.error_message,
            "external_job_id": self.external_job_id,
            "external_job_url": self.external_job_url,
            "api_calls_made": self.api_calls_made,
            "estimated_cost_usd": self.estimated_cost_usd / 100 if self.estimated_cost_usd else 0,
        }

    @property
    def duration_seconds(self) -> int:
        """Calculate job duration in seconds."""
        if not self.started_at:
            return 0
        end = self.completed_at or datetime.utcnow()
        return int((end - self.started_at).total_seconds())

    def __repr__(self):
        return f"<ScrapeJob {self.id}: {self.source} - {self.status}>"
