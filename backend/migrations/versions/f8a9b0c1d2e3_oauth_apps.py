"""'Continue with FOID' sign-in apps (OAuth clients) and their hashed client secrets

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = 'f8a9b0c1d2e3'
down_revision = 'e7f8a9b0c1d2'
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


def upgrade() -> None:
    _create_table(
        'oauth_apps',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('org_id', sa.String(), nullable=False),
        sa.Column('env', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('client_id', sa.String(), nullable=False),
        sa.Column('origins', sa.JSON(), nullable=False),
        sa.Column('redirect_uris', sa.JSON(), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('auth_method', sa.String(), nullable=False),
        sa.Column('public_jwk', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('disabled_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organisations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_oauth_apps_org_id'), 'oauth_apps', ['org_id'], unique=False)
    _create_index(op.f('ix_oauth_apps_client_id'), 'oauth_apps', ['client_id'], unique=True)
    _create_table(
        'oauth_client_secrets',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('app_id', sa.String(), nullable=False),
        sa.Column('hint', sa.String(), nullable=False),
        sa.Column('secret_hash', sa.String(), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['app_id'], ['oauth_apps.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_oauth_client_secrets_app_id'), 'oauth_client_secrets', ['app_id'], unique=False)
    _create_index(op.f('ix_oauth_client_secrets_secret_hash'), 'oauth_client_secrets', ['secret_hash'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_oauth_client_secrets_secret_hash'), table_name='oauth_client_secrets')
    op.drop_index(op.f('ix_oauth_client_secrets_app_id'), table_name='oauth_client_secrets')
    op.drop_table('oauth_client_secrets')
    op.drop_index(op.f('ix_oauth_apps_client_id'), table_name='oauth_apps')
    op.drop_index(op.f('ix_oauth_apps_org_id'), table_name='oauth_apps')
    op.drop_table('oauth_apps')
