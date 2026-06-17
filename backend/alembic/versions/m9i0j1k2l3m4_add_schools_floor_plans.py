"""add nearby_schools and floor_plans columns

Adds two more columns for data the epctex Apify scrape already returns
but the normalizer was discarding. Mirrors the k7g8h9i0j1k2 enrichment
migration in pattern (same Commit 1 approach: pull from raw_data, no
extra Apify cost). Backfill via the backfill_extended_fields Celery
task populates existing rows.

- nearby_schools (JSONB): {public: [...], private: [...]} with each
  entry {type, name, grades, numberOfStudents}. No school ratings —
  apartments.com doesn't expose them via this actor.
- floor_plans (JSONB): array of {modelId, modelName, totalPrice,
  basePrice, image, details, leaseOptions, availability,
  availabilityInfo, squareFeet}. Sourced from raw.models (not
  raw.floorPlans, which is consistently empty for epctex).

Revision ID: m9i0j1k2l3m4
Revises: k7g8h9i0j1k2
Create Date: 2026-06-17 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'm9i0j1k2l3m4'
down_revision: str = 'k7g8h9i0j1k2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('apartments', sa.Column('nearby_schools', JSONB(), nullable=True))
    op.add_column('apartments', sa.Column('floor_plans', JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('apartments', 'floor_plans')
    op.drop_column('apartments', 'nearby_schools')
