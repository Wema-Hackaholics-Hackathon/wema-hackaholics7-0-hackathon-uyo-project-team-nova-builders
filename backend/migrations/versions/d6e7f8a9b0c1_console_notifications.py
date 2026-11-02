"""console notification bell (one row per team member)

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = 'd6e7f8a9b0c1'
down_revision = 'c5d6e7f8a9b0'
branch_labels = None
depends_on = None


def _insp() -> sa.engine.Inspector:
    return sa.inspect(op.get_bind())


def _create_table(name: str, *args: object, **kw: object) -> None:
    """Skip if it exists (an older app start may have created it before this migration ran)."""
    if not _insp().has_table(name):
        op.create_table(name, *args, **kw)


def _create_index(name: str, table: str, columns: list[str], **kw: object) -> None:
    if name not in {ix['name'] for ix in _insp().get_indexes(table)}:
        op.create_index(name, table, columns, **kw)


def _add_column(table: str, column: sa.Column) -> None:  # type: ignore[type-arg]
    if column.name not in {c['name'] for c in _insp().get_columns(table)}:
        op.add_column(table, column)

_INDEXES = ('org_id', 'console_user_id', 'created_at')


def upgrade() -> None:
    _create_table(
        'console_notifications',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('org_id', sa.String(), nullable=False),
        sa.Column('console_user_id', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('body', sa.String(), nullable=False),
        sa.Column('link', sa.String(), nullable=True),
        sa.Column('ref', sa.String(), nullable=True),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organisations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['console_user_id'], ['console_users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    for c in _INDEXES:
        _create_index(op.f(f'ix_console_notifications_{c}'), 'console_notifications', [c], unique=False)


def downgrade() -> None:
    for c in _INDEXES:
        op.drop_index(op.f(f'ix_console_notifications_{c}'), table_name='console_notifications')
    op.drop_table('console_notifications')
