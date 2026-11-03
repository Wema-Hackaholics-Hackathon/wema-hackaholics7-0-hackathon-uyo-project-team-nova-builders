"""'Continue with FOID' sign-in requests (popup → one-time code → server exchange)

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = 'a9b0c1d2e3f4'
down_revision = 'f8a9b0c1d2e3'
branch_labels = None
depends_on = None

_INDEXES = (('app_id', False), ('org_id', False), ('status', False), ('user_id', False), ('code_hash', True))


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


def upgrade() -> None:
    _create_table(
        'oauth_requests',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('app_id', sa.String(), nullable=False),
        sa.Column('org_id', sa.String(), nullable=False),
        sa.Column('env', sa.String(), nullable=False),
        sa.Column('response_mode', sa.String(), nullable=False),
        sa.Column('origin', sa.String(), nullable=True),
        sa.Column('redirect_uri', sa.String(), nullable=True),
        sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('state', sa.String(), nullable=False),
        sa.Column('nonce', sa.String(), nullable=True),
        sa.Column('code_challenge', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('otp_hash', sa.String(), nullable=True),
        sa.Column('otp_expires_at', sa.DateTime(), nullable=True),
        sa.Column('otp_attempts', sa.Integer(), nullable=False),
        sa.Column('otp_sends', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=True),
        sa.Column('verification_id', sa.String(), nullable=True),
        sa.Column('subject_id', sa.String(), nullable=True),
        sa.Column('grant_id', sa.String(), nullable=True),
        sa.Column('rematched_at', sa.DateTime(), nullable=True),
        sa.Column('code_hash', sa.String(), nullable=True),
        sa.Column('code_expires_at', sa.DateTime(), nullable=True),
        sa.Column('code_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['app_id'], ['oauth_apps.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    for c, unique in _INDEXES:
        _create_index(op.f(f'ix_oauth_requests_{c}'), 'oauth_requests', [c], unique=unique)


def downgrade() -> None:
    for c, _ in _INDEXES:
        op.drop_index(op.f(f'ix_oauth_requests_{c}'), table_name='oauth_requests')
    op.drop_table('oauth_requests')
