"""add market configs and freshness tracking

Revision ID: b67261628783
Revises: 001_initial_schema
Create Date: 2026-02-21 09:32:03.168779

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b67261628783'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create market_configs table
    op.create_table(
        'market_configs',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('display_name', sa.String(200), nullable=False),
        sa.Column('city', sa.String(100), nullable=False),
        sa.Column('state', sa.String(10), nullable=False),
        sa.Column('tier', sa.String(20), nullable=False, server_default='cool'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('max_listings_per_scrape', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('scrape_frequency_hours', sa.Integer(), nullable=False, server_default='24'),
        sa.Column('last_scrape_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_scrape_status', sa.String(20), nullable=True),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Add freshness columns to apartments
    op.add_column('apartments', sa.Column('freshness_confidence', sa.Integer(), nullable=False, server_default='100'))
    op.add_column('apartments', sa.Column('confidence_updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('apartments', sa.Column('verification_status', sa.String(20), nullable=True))
    op.add_column('apartments', sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('apartments', sa.Column('times_seen', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('apartments', sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.add_column('apartments', sa.Column('market_id', sa.String(50), nullable=True))

    # Add indexes
    op.create_index('idx_apartments_freshness', 'apartments', ['freshness_confidence'])
    op.create_index('idx_apartments_verification', 'apartments', ['verification_status'])
    op.create_index('idx_apartments_market', 'apartments', ['market_id'])

    # Truncate apartments (fresh start)
    op.execute("TRUNCATE TABLE apartments")

    # Seed market_configs with East Coast markets
    op.execute("""
        INSERT INTO market_configs (id, display_name, city, state, tier, scrape_frequency_hours) VALUES
        ('philadelphia', 'Philadelphia', 'Philadelphia', 'PA', 'hot', 6),
        ('nyc', 'New York City', 'New York', 'NY', 'hot', 6),
        ('boston', 'Boston', 'Boston', 'MA', 'hot', 6),
        ('washington-dc', 'Washington DC', 'Washington', 'DC', 'hot', 6),
        ('pittsburgh', 'Pittsburgh', 'Pittsburgh', 'PA', 'standard', 12),
        ('baltimore', 'Baltimore', 'Baltimore', 'MD', 'standard', 12),
        ('newark', 'Newark', 'Newark', 'NJ', 'standard', 12),
        ('jersey-city', 'Jersey City', 'Jersey City', 'NJ', 'standard', 12),
        ('cambridge', 'Cambridge', 'Cambridge', 'MA', 'standard', 12),
        ('arlington-va', 'Arlington VA', 'Arlington', 'VA', 'standard', 12),
        ('bryn-mawr', 'Bryn Mawr', 'Bryn Mawr', 'PA', 'cool', 24),
        ('hoboken', 'Hoboken', 'Hoboken', 'NJ', 'cool', 24),
        ('stamford', 'Stamford', 'Stamford', 'CT', 'cool', 24),
        ('new-haven', 'New Haven', 'New Haven', 'CT', 'cool', 24),
        ('providence', 'Providence', 'Providence', 'RI', 'cool', 24),
        ('richmond', 'Richmond', 'Richmond', 'VA', 'cool', 24),
        ('charlotte', 'Charlotte', 'Charlotte', 'NC', 'cool', 24),
        ('raleigh', 'Raleigh', 'Raleigh', 'NC', 'cool', 24),
        ('hartford', 'Hartford', 'Hartford', 'CT', 'cool', 24)
    """)


def downgrade() -> None:
    op.drop_index('idx_apartments_market', 'apartments')
    op.drop_index('idx_apartments_verification', 'apartments')
    op.drop_index('idx_apartments_freshness', 'apartments')
    op.drop_column('apartments', 'market_id')
    op.drop_column('apartments', 'first_seen_at')
    op.drop_column('apartments', 'times_seen')
    op.drop_column('apartments', 'verified_at')
    op.drop_column('apartments', 'verification_status')
    op.drop_column('apartments', 'confidence_updated_at')
    op.drop_column('apartments', 'freshness_confidence')
    op.drop_table('market_configs')
