"""add address to users

Revision ID: 63e8311473ca
Revises: 89ce76ea1215
Create Date: 2025-01-01 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '63e8311473ca'
down_revision = '89ce76ea1215'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('address', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'address')
