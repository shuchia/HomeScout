"""
SQLAlchemy ORM model for apartments with source tracking.
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Text, Index
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.sql import func

from app.database import Base


class ApartmentModel(Base):
    """
    ORM model for apartment listings.

    Tracks listings from multiple sources with normalization
    and deduplication support.
    """
    __tablename__ = "apartments"

    # Primary key and external identifiers
    id = Column(String(50), primary_key=True)  # Internal UUID
    external_id = Column(String(255), nullable=True)  # ID from source (e.g., Zillow listing ID)
    source = Column(String(50), nullable=False, default="manual")  # zillow, apartments_com, craigslist, manual
    source_url = Column(Text, nullable=True)  # Original listing URL

    # Address fields (normalized)
    address = Column(String(500), nullable=False)
    address_normalized = Column(String(500), nullable=True)  # Standardized address format
    city = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    zip_code = Column(String(20), nullable=True)
    neighborhood = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Listing details
    rent = Column(Integer, nullable=False)
    bedrooms = Column(Integer, nullable=False)
    bathrooms = Column(Float, nullable=False)  # Float to support 1.5 baths
    sqft = Column(Integer, nullable=True)
    property_type = Column(String(50), nullable=False)  # Apartment, Condo, House, Townhouse
    available_date = Column(String(20), nullable=True)  # YYYY-MM-DD format

    # Rich content
    description = Column(Text, nullable=True)
    amenities = Column(JSONB, default=list)  # List of amenity strings
    images = Column(JSONB, default=list)  # List of image URLs
    images_cached = Column(JSONB, default=list)  # List of S3 cached image URLs

    # Deduplication and quality
    content_hash = Column(String(64), nullable=True, unique=True)  # SHA256 hash for dedup
    data_quality_score = Column(Integer, default=50)  # 0-100 quality score

    # Metadata
    raw_data = Column(JSONB, nullable=True)  # Original scraped data for debugging
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())  # Last time seen in scrape
    is_active = Column(Integer, default=1)  # 1=active, 0=inactive/removed

    # Freshness tracking
    freshness_confidence = Column(Integer, nullable=False, default=100)  # 0-100
    confidence_updated_at = Column(DateTime(timezone=True), nullable=True)
    verification_status = Column(String(20), nullable=True)  # null, pending, verified, gone
    verified_at = Column(DateTime(timezone=True), nullable=True)
    times_seen = Column(Integer, nullable=False, default=1)
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    market_id = Column(String(50), nullable=True)  # FK to market_configs.id

    # Indexes for common query patterns
    __table_args__ = (
        Index('idx_apartments_city', 'city'),
        Index('idx_apartments_rent', 'rent'),
        Index('idx_apartments_bedrooms', 'bedrooms'),
        Index('idx_apartments_bathrooms', 'bathrooms'),
        Index('idx_apartments_property_type', 'property_type'),
        Index('idx_apartments_source', 'source'),
        Index('idx_apartments_content_hash', 'content_hash'),
        Index('idx_apartments_is_active', 'is_active'),
        Index('idx_apartments_city_rent_beds', 'city', 'rent', 'bedrooms'),
        Index('idx_apartments_freshness', 'freshness_confidence'),
        Index('idx_apartments_verification', 'verification_status'),
        Index('idx_apartments_market', 'market_id'),
    )

    def to_dict(self) -> dict:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "address": self.address,
            "rent": self.rent,
            "bedrooms": self.bedrooms,
            "bathrooms": int(self.bathrooms) if self.bathrooms == int(self.bathrooms) else self.bathrooms,
            "sqft": self.sqft or 0,
            "property_type": self.property_type,
            "available_date": self.available_date or "",
            "amenities": self.amenities or [],
            "neighborhood": self.neighborhood or "",
            "description": self.description or "",
            "images": self.images_cached if self.images_cached else (self.images or []),
            # Additional fields for detailed view
            "city": self.city,
            "state": self.state,
            "zip_code": self.zip_code,
            "source": self.source,
            "source_url": self.source_url,
            "data_quality_score": self.data_quality_score,
            "freshness_confidence": self.freshness_confidence,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "times_seen": self.times_seen,
        }

    def __repr__(self):
        return f"<Apartment {self.id}: {self.address} - ${self.rent}/mo>"
