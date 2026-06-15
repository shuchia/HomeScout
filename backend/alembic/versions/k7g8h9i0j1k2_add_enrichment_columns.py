"""add enrichment columns extracted from raw_data

Adds columns for data the epctex Apify scrape already returns but the
normalizer was discarding. Filling these out gives beta testers a much
richer listing view (specials, walk/transit scores, available units,
virtual tours, transit options) without any extra Apify cost — a
backfill task re-processes existing raw_data to populate the new
columns retroactively.

Revision ID: k7g8h9i0j1k2
Revises: j5e6f7g8h9i0
Create Date: 2026-06-15 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'k7g8h9i0j1k2'
down_revision: str = 'j5e6f7g8h9i0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Scalar enrichment fields
    op.add_column('apartments', sa.Column('contact_name', sa.String(255), nullable=True))
    op.add_column('apartments', sa.Column('walk_score', sa.Integer(), nullable=True))
    op.add_column('apartments', sa.Column('transit_score', sa.Integer(), nullable=True))
    op.add_column('apartments', sa.Column('apartments_com_rating', sa.Float(), nullable=True))
    op.add_column('apartments', sa.Column('property_website', sa.Text(), nullable=True))

    # Structured enrichment payloads (kept as JSONB so we can iterate on shape
    # without further migrations).
    op.add_column('apartments', sa.Column('specials', JSONB(), nullable=True))           # {title, label, description}
    op.add_column('apartments', sa.Column('available_units', JSONB(), nullable=True))    # list of rentals
    op.add_column('apartments', sa.Column('transit_options', JSONB(), nullable=True))    # list of transit stops with walk/drive
    op.add_column('apartments', sa.Column('virtual_tour_urls', JSONB(), nullable=True))  # list of URL strings

    # When the per-tour detail-mode enrichment (Commit 2) runs against a URL,
    # this marks when it last ran. Bulk-scrape extraction (this commit) does
    # NOT set this — only the detail-mode task does.
    op.add_column('apartments', sa.Column('last_enriched_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('apartments', 'last_enriched_at')
    op.drop_column('apartments', 'virtual_tour_urls')
    op.drop_column('apartments', 'transit_options')
    op.drop_column('apartments', 'available_units')
    op.drop_column('apartments', 'specials')
    op.drop_column('apartments', 'property_website')
    op.drop_column('apartments', 'apartments_com_rating')
    op.drop_column('apartments', 'transit_score')
    op.drop_column('apartments', 'walk_score')
    op.drop_column('apartments', 'contact_name')
