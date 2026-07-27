"""add pricing_model to apartment_floorplans

Per-floorplan pricing model (per_unit vs per_person / by-the-bed). The building
level pricing_model is unreliable for buckets — detect_pricing_model treats
bedrooms==0 as always per_unit, and by-the-bed buildings are stored collapsed as
studios (bedrooms=0). Detecting per bucket (using the bucket's real beds/baths)
fixes that so by-the-bed floorplans can be labeled "$X/bed" with a whole-unit
total. See docs/floorplan-search-design.md (per-bedroom pricing finding).

Revision ID: o1k2l3m4n5o6
Revises: n0j1k2l3m4n5
Create Date: 2026-07-26 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'o1k2l3m4n5o6'
down_revision: str = 'n0j1k2l3m4n5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'apartment_floorplans',
        sa.Column('pricing_model', sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('apartment_floorplans', 'pricing_model')
