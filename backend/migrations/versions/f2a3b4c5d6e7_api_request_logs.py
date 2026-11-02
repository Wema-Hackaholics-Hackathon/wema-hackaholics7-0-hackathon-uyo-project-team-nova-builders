"""request logs for the business console (Open API calls, 30-day retention)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
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

_INDEXES = ('org_id', 'env', 'key_id', 'status', 'created_at')


def upgrade() -> None:
    _create_table(
        'api_request_logs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('org_id', sa.String(), nullable=False),
        sa.Column('env', sa.String(), nullable=False),
        sa.Column('key_id', sa.String(), nullable=True),
        sa.Column('key_hint', sa.String(), nullable=True),
        sa.Column('request_id', sa.String(), nullable=False),
        sa.Column('method', sa.String(), nullable=False),
        sa.Column('path', sa.String(), nullable=False),
        sa.Column('status', sa.Integer(), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organisations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_api_request_logs_request_id'), 'api_request_logs', ['request_id'], unique=True)
    for c in _INDEXES:
        _create_index(op.f(f'ix_api_request_logs_{c}'), 'api_request_logs', [c], unique=False)


def downgrade() -> None:
    for c in _INDEXES:
        op.drop_index(op.f(f'ix_api_request_logs_{c}'), table_name='api_request_logs')
    op.drop_index(op.f('ix_api_request_logs_request_id'), table_name='api_request_logs')
    op.drop_table('api_request_logs')
