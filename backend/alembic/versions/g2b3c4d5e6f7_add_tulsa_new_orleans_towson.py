"""add tulsa, new orleans, towson, and state college markets

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-29 08:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'g2b3c4d5e6f7'
down_revision: str = 'c3cda027bbfe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO market_configs (id, display_name, city, state, tier, scrape_frequency_hours, is_enabled) VALUES
        ('charleston', 'Charleston', 'Charleston', 'SC', 'cool', 48, true),
        ('new-orleans', 'New Orleans', 'New Orleans', 'LA', 'cool', 48, true),
        ('towson', 'Towson', 'Towson', 'MD', 'cool', 48, true),
        ('state-college', 'State College', 'State College', 'PA', 'cool', 48, true)
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM market_configs WHERE id IN ('charleston', 'new-orleans', 'towson', 'state-college')
    """)
