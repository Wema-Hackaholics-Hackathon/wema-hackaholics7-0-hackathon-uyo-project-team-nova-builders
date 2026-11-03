"""FOID user sign-in security: authenticator-app 2FA, login alerts (known devices), passkeys

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = 'e7f8a9b0c1d2'
down_revision = 'd6e7f8a9b0c1'
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
    _add_column('users', sa.Column('totp_secret_enc', sa.String(), nullable=True))
    _add_column('users', sa.Column('totp_enabled_at', sa.DateTime(), nullable=True))
    _add_column('users', sa.Column('totp_last_step', sa.Integer(), nullable=True))
    _add_column('users', sa.Column('login_alerts', sa.Boolean(), nullable=False, server_default=sa.true()))
    _create_table(
        'user_devices',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('device_hash', sa.String(), nullable=False),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('ip', sa.String(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_user_devices_user_id'), 'user_devices', ['user_id'], unique=False)
    _create_index(op.f('ix_user_devices_device_hash'), 'user_devices', ['device_hash'], unique=False)
    _create_table(
        'user_passkeys',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('credential_id', sa.String(), nullable=False),
        sa.Column('public_key', sa.LargeBinary(), nullable=False),
        sa.Column('sign_count', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_user_passkeys_user_id'), 'user_passkeys', ['user_id'], unique=False)
    _create_index(op.f('ix_user_passkeys_credential_id'), 'user_passkeys', ['credential_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_passkeys_credential_id'), table_name='user_passkeys')
    op.drop_index(op.f('ix_user_passkeys_user_id'), table_name='user_passkeys')
    op.drop_table('user_passkeys')
    op.drop_index(op.f('ix_user_devices_device_hash'), table_name='user_devices')
    op.drop_index(op.f('ix_user_devices_user_id'), table_name='user_devices')
    op.drop_table('user_devices')
    with op.batch_alter_table('users') as b:
        for c in ('login_alerts', 'totp_last_step', 'totp_enabled_at', 'totp_secret_enc'):
            b.drop_column(c)
