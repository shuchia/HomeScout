"""add admin_fee column

Revision ID: i4d5e6f7g8h9
Revises: h3c4d5e6f7g8
Create Date: 2026-04-06 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i4d5e6f7g8h9'
down_revision: str = 'h3c4d5e6f7g8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('apartments', sa.Column('admin_fee', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('apartments', 'admin_fee')
