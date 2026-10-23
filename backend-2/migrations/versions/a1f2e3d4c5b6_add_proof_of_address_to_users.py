"""add proof_of_address_url to users

Revision ID: a1f2e3d4c5b6
Revises: 63e8311473ca
Create Date: 2025-01-02 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = 'a1f2e3d4c5b6'
down_revision = '63e8311473ca'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('proof_of_address_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'proof_of_address_url')
