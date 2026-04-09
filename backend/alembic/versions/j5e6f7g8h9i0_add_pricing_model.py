"""add pricing_model columns

Revision ID: j5e6f7g8h9i0
Revises: i4d5e6f7g8h9
Create Date: 2026-04-08 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'j5e6f7g8h9i0'
down_revision: str = 'i4d5e6f7g8h9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('apartments', sa.Column('pricing_model', sa.String(20), server_default='per_unit'))
    op.add_column('apartments', sa.Column('pricing_model_confidence', sa.Float(), nullable=True))

def downgrade() -> None:
    op.drop_column('apartments', 'pricing_model_confidence')
    op.drop_column('apartments', 'pricing_model')
