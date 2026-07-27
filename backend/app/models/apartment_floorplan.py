"""ApartmentFloorplanModel — per-(bedrooms, bathrooms) buckets for a building.

apartments.com returns one *building* per listing with many floorplans. To make
larger units searchable while still showing one card per building, each building
gets a set of aggregated floorplan buckets (see
``app/services/floorplans.build_floorplan_buckets`` and
``docs/floorplan-search-design.md``).

This table is a child of ``apartments`` (one row per building, unchanged). Rows
are derived data: rebuilt wholesale (delete + reinsert keyed by ``apartment_id``)
on every scrape and by the backfill task. Building identity, dedup, favorites and
tours all continue to key off ``apartments`` — never this table.
"""

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy import DateTime

from app.database import Base


class ApartmentFloorplanModel(Base):
    __tablename__ = "apartment_floorplans"

    id = Column(String(50), primary_key=True)  # uuid4 hex

    # Parent building. CASCADE so buckets vanish with the building; the backfill
    # and scraper also delete+reinsert by this key for idempotent rebuilds.
    apartment_id = Column(
        String(50),
        ForeignKey("apartments.id", ondelete="CASCADE"),
        nullable=False,
    )

    bedrooms = Column(Integer, nullable=False)   # 0 = studio
    bathrooms = Column(Float, nullable=False)    # exact bath count of this bucket

    # Rent range across the available units in this bucket. NULL when every unit
    # is "Call for Rent" (price-on-request, decision D1) — never treat as 0.
    min_rent = Column(Integer, nullable=True)
    max_rent = Column(Integer, nullable=True)

    min_sqft = Column(Integer, nullable=True)
    max_sqft = Column(Integer, nullable=True)

    # Sum of "N Available units" across the models in this bucket. Buckets are
    # only materialized when this is > 0.
    available_units = Column(Integer, nullable=False, default=0)

    # Earliest upcoming move-in date for this bucket (YYYY-MM-DD), if known.
    earliest_available_date = Column(String(20), nullable=True)

    # Provenance: the source modelIds that rolled up into this bucket.
    model_ids = Column(JSONB, nullable=True)

    # "per_unit" (min_rent is whole-unit) or "per_person" (min_rent is the
    # by-the-bed share; whole-unit ≈ min_rent × bedrooms). Detected per bucket,
    # not from the building's collapsed pricing_model.
    pricing_model = Column(String(20), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # One bucket per (building, beds, baths).
        UniqueConstraint("apartment_id", "bedrooms", "bathrooms", name="uq_floorplan_bucket"),
        # Search join: filter buckets by size + price, then group by building.
        Index("idx_floorplan_beds_rent", "bedrooms", "min_rent"),
        Index("idx_floorplan_apartment", "apartment_id"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "apartment_id": self.apartment_id,
            "bedrooms": self.bedrooms,
            "bathrooms": self.bathrooms,
            "min_rent": self.min_rent,
            "max_rent": self.max_rent,
            "min_sqft": self.min_sqft,
            "max_sqft": self.max_sqft,
            "available_units": self.available_units,
            "earliest_available_date": self.earliest_available_date,
            "price_on_request": self.min_rent is None,
            "pricing_model": self.pricing_model,
        }
