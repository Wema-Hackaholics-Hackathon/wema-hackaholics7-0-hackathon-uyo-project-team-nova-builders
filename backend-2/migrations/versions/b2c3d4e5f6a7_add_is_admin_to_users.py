"""add is_admin to users

Revision ID: b2c3d4e5f6a7
Revises: a1f2e3d4c5b6
Create Date: 2025-01-03 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1f2e3d4c5b6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('users', 'is_admin')
