"""reduce scrape frequency and disable most cool markets

Revision ID: f1a2b3c4d5e6
Revises: e98533caec98
Create Date: 2026-03-27 22:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: str = 'e98533caec98'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Increase scrape frequency: hot 6→12h, standard 12→24h, cool 24→48h
    op.execute("""
        UPDATE market_configs SET scrape_frequency_hours = 12 WHERE tier = 'hot'
    """)
    op.execute("""
        UPDATE market_configs SET scrape_frequency_hours = 24 WHERE tier = 'standard'
    """)
    op.execute("""
        UPDATE market_configs SET scrape_frequency_hours = 48 WHERE tier = 'cool'
    """)

    # Disable all cool markets except Bryn Mawr
    op.execute("""
        UPDATE market_configs SET is_enabled = false
        WHERE tier = 'cool' AND id != 'bryn-mawr'
    """)


def downgrade() -> None:
    # Restore original frequencies
    op.execute("""
        UPDATE market_configs SET scrape_frequency_hours = 6 WHERE tier = 'hot'
    """)
    op.execute("""
        UPDATE market_configs SET scrape_frequency_hours = 12 WHERE tier = 'standard'
    """)
    op.execute("""
        UPDATE market_configs SET scrape_frequency_hours = 24 WHERE tier = 'cool'
    """)

    # Re-enable all cool markets
    op.execute("""
        UPDATE market_configs SET is_enabled = true WHERE tier = 'cool'
    """)