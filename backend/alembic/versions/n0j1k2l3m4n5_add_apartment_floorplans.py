"""add apartment_floorplans table

Child table of `apartments` holding per-(bedrooms, bathrooms) floorplan buckets
so larger units become searchable while the UI still shows one card per
building. Populated by the `backfill_floorplans` task from the existing
`apartments.floor_plans` JSONB (no re-scrape) and, going forward, by the scraper
on write. Phase 1 of docs/floorplan-search-design.md — this migration only
creates the table; nothing reads it yet.

Revision ID: n0j1k2l3m4n5
Revises: m9i0j1k2l3m4
Create Date: 2026-07-16 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'n0j1k2l3m4n5'
down_revision: str = 'm9i0j1k2l3m4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'apartment_floorplans',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('apartment_id', sa.String(length=50), nullable=False),
        sa.Column('bedrooms', sa.Integer(), nullable=False),
        sa.Column('bathrooms', sa.Float(), nullable=False),
        sa.Column('min_rent', sa.Integer(), nullable=True),
        sa.Column('max_rent', sa.Integer(), nullable=True),
        sa.Column('min_sqft', sa.Integer(), nullable=True),
        sa.Column('max_sqft', sa.Integer(), nullable=True),
        sa.Column('available_units', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('earliest_available_date', sa.String(length=20), nullable=True),
        sa.Column('model_ids', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['apartment_id'], ['apartments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('apartment_id', 'bedrooms', 'bathrooms', name='uq_floorplan_bucket'),
    )
    op.create_index('idx_floorplan_beds_rent', 'apartment_floorplans', ['bedrooms', 'min_rent'])
    op.create_index('idx_floorplan_apartment', 'apartment_floorplans', ['apartment_id'])


def downgrade() -> None:
    op.drop_index('idx_floorplan_apartment', table_name='apartment_floorplans')
    op.drop_index('idx_floorplan_beds_rent', table_name='apartment_floorplans')
    op.drop_table('apartment_floorplans')
