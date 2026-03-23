"""Initial database schema for Snugd data collection.

Revision ID: 001_initial_schema
Revises:
Create Date: 2025-01-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create apartments table
    op.create_table(
        'apartments',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('external_id', sa.String(255), nullable=True),
        sa.Column('source', sa.String(50), nullable=False, server_default='manual'),
        sa.Column('source_url', sa.Text(), nullable=True),

        # Address fields
        sa.Column('address', sa.String(500), nullable=False),
        sa.Column('address_normalized', sa.String(500), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('state', sa.String(50), nullable=True),
        sa.Column('zip_code', sa.String(20), nullable=True),
        sa.Column('neighborhood', sa.String(100), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),

        # Listing details
        sa.Column('rent', sa.Integer(), nullable=False),
        sa.Column('bedrooms', sa.Integer(), nullable=False),
        sa.Column('bathrooms', sa.Float(), nullable=False),
        sa.Column('sqft', sa.Integer(), nullable=True),
        sa.Column('property_type', sa.String(50), nullable=False),
        sa.Column('available_date', sa.String(20), nullable=True),

        # Rich content
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('amenities', postgresql.JSONB(), server_default='[]'),
        sa.Column('images', postgresql.JSONB(), server_default='[]'),
        sa.Column('images_cached', postgresql.JSONB(), server_default='[]'),

        # Deduplication and quality
        sa.Column('content_hash', sa.String(64), nullable=True, unique=True),
        sa.Column('data_quality_score', sa.Integer(), server_default='50'),

        # Metadata
        sa.Column('raw_data', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('is_active', sa.Integer(), server_default='1'),
    )

    # Create indexes for apartments
    op.create_index('idx_apartments_city', 'apartments', ['city'])
    op.create_index('idx_apartments_rent', 'apartments', ['rent'])
    op.create_index('idx_apartments_bedrooms', 'apartments', ['bedrooms'])
    op.create_index('idx_apartments_bathrooms', 'apartments', ['bathrooms'])
    op.create_index('idx_apartments_property_type', 'apartments', ['property_type'])
    op.create_index('idx_apartments_source', 'apartments', ['source'])
    op.create_index('idx_apartments_content_hash', 'apartments', ['content_hash'])
    op.create_index('idx_apartments_is_active', 'apartments', ['is_active'])
    op.create_index('idx_apartments_city_rent_beds', 'apartments', ['city', 'rent', 'bedrooms'])

    # Create scrape_jobs table
    op.create_table(
        'scrape_jobs',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('job_type', sa.String(50), nullable=False, server_default='full'),

        # Target parameters
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('state', sa.String(50), nullable=True),
        sa.Column('search_params', postgresql.JSONB(), nullable=True),

        # Status
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),

        # Timing
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),

        # Metrics
        sa.Column('listings_found', sa.Integer(), server_default='0'),
        sa.Column('listings_new', sa.Integer(), server_default='0'),
        sa.Column('listings_updated', sa.Integer(), server_default='0'),
        sa.Column('listings_duplicates', sa.Integer(), server_default='0'),
        sa.Column('listings_errors', sa.Integer(), server_default='0'),

        # Error handling
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_details', postgresql.JSONB(), nullable=True),

        # External reference
        sa.Column('external_job_id', sa.String(255), nullable=True),
        sa.Column('external_job_url', sa.Text(), nullable=True),

        # Cost tracking
        sa.Column('api_calls_made', sa.Integer(), server_default='0'),
        sa.Column('estimated_cost_usd', sa.Integer(), server_default='0'),
    )

    # Create indexes for scrape_jobs
    op.create_index('idx_scrape_jobs_status', 'scrape_jobs', ['status'])
    op.create_index('idx_scrape_jobs_source', 'scrape_jobs', ['source'])
    op.create_index('idx_scrape_jobs_created_at', 'scrape_jobs', ['created_at'])

    # Create data_sources table
    op.create_table(
        'data_sources',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),

        # Status
        sa.Column('is_enabled', sa.Boolean(), server_default='true'),
        sa.Column('is_healthy', sa.Boolean(), server_default='true'),

        # Provider configuration
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('provider_config', postgresql.JSONB(), nullable=True),

        # Rate limiting
        sa.Column('rate_limit_per_hour', sa.Integer(), server_default='100'),
        sa.Column('rate_limit_per_day', sa.Integer(), server_default='1000'),
        sa.Column('current_hour_calls', sa.Integer(), server_default='0'),
        sa.Column('current_day_calls', sa.Integer(), server_default='0'),
        sa.Column('rate_limit_reset_hour', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rate_limit_reset_day', sa.DateTime(timezone=True), nullable=True),

        # Scheduling
        sa.Column('scrape_frequency_hours', sa.Integer(), server_default='24'),
        sa.Column('last_scrape_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_scrape_at', sa.DateTime(timezone=True), nullable=True),

        # Quality metrics
        sa.Column('total_listings_scraped', sa.Integer(), server_default='0'),
        sa.Column('successful_scrapes', sa.Integer(), server_default='0'),
        sa.Column('failed_scrapes', sa.Integer(), server_default='0'),
        sa.Column('average_data_quality', sa.Integer(), server_default='0'),

        # Cost tracking
        sa.Column('cost_per_listing_cents', sa.Integer(), server_default='0'),
        sa.Column('total_cost_cents', sa.Integer(), server_default='0'),
        sa.Column('monthly_budget_cents', sa.Integer(), server_default='0'),
        sa.Column('current_month_cost_cents', sa.Integer(), server_default='0'),

        # Metadata
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('data_sources')
    op.drop_table('scrape_jobs')
    op.drop_table('apartments')
