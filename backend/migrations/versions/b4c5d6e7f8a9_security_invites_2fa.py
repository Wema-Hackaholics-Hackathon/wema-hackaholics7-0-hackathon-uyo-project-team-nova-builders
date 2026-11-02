"""security settings, deactivation, team invites, two-step sign-in for console accounts

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = 'b4c5d6e7f8a9'
down_revision = 'a3b4c5d6e7f8'
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
    _add_column('organisations', sa.Column('require_2fa', sa.Boolean(), nullable=False, server_default=sa.false()))
    _add_column('organisations', sa.Column('alert_on_key_create', sa.Boolean(), nullable=False, server_default=sa.true()))
    _add_column('organisations', sa.Column('ip_allowlist', sa.JSON(), nullable=False, server_default='[]'))
    _add_column('organisations', sa.Column('deactivated_at', sa.DateTime(), nullable=True))
    _add_column('console_users', sa.Column('totp_secret_enc', sa.String(), nullable=True))
    _add_column('console_users', sa.Column('totp_enabled_at', sa.DateTime(), nullable=True))
    _add_column('console_users', sa.Column('totp_last_step', sa.Integer(), nullable=True))
    _create_table(
        'org_invites',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('org_id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('invited_by', sa.String(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organisations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_org_invites_org_id'), 'org_invites', ['org_id'], unique=False)
    _create_index(op.f('ix_org_invites_email'), 'org_invites', ['email'], unique=False)
    _create_index(op.f('ix_org_invites_token_hash'), 'org_invites', ['token_hash'], unique=True)


def downgrade() -> None:
    for ix in ('token_hash', 'email', 'org_id'):
        op.drop_index(op.f(f'ix_org_invites_{ix}'), table_name='org_invites')
    op.drop_table('org_invites')
    with op.batch_alter_table('console_users') as b:
        for c in ('totp_last_step', 'totp_enabled_at', 'totp_secret_enc'):
            b.drop_column(c)
    with op.batch_alter_table('organisations') as b:
        for c in ('deactivated_at', 'ip_allowlist', 'alert_on_key_create', 'require_2fa'):
            b.drop_column(c)
