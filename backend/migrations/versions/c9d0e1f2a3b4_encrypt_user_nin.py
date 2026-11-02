"""encrypt users.nin; add date_of_birth and nin_verified_at

The NIN was stored in plain text. It becomes nin_enc (Fernet,
DATA_ENCRYPTION_KEY) + nin_last4 (display) + nin_hash (keyed lookup hash,
PII_HASH_KEY), and the plain `nin` column is dropped.

Also adds date_of_birth (collected at NIN verification, not signup) and
nin_verified_at (when name + DOB matched the NIN record; locks the identity).
Users an admin had already marked nin_verified are stamped verified now.

Set DATA_ENCRYPTION_KEY and PII_HASH_KEY BEFORE running this in production —
the data is encrypted/hashed with them. Downgrade needs the same key.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-02
"""

import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def _cols() -> set[str]:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns('users')}


def _indexes() -> set[str]:
    return {ix['name'] for ix in sa.inspect(op.get_bind()).get_indexes('users')}


def upgrade() -> None:
    from app.core.crypto import encrypt_str, pii_hash

    cols = _cols()
    with op.batch_alter_table('users') as batch:
        for name, type_ in (('nin_enc', sa.String()), ('nin_last4', sa.String()),
                            ('date_of_birth', sa.String()), ('nin_verified_at', sa.DateTime())):
            if name not in cols:
                batch.add_column(sa.Column(name, type_, nullable=True))

    bind = op.get_bind()
    if 'nin' in cols:
        for user_id, nin in bind.execute(sa.text("SELECT id, nin FROM users WHERE nin IS NOT NULL")).fetchall():
            nin = nin.strip()
            bind.execute(
                sa.text("UPDATE users SET nin_enc = :e, nin_last4 = :l, nin_hash = :h WHERE id = :id"),
                {"e": encrypt_str(nin), "l": nin[-4:], "h": pii_hash(nin), "id": user_id},
            )

    # Admin-verified NINs (claims.nin_verified) count as verified → identity locked.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for user_id, claims in bind.execute(sa.text("SELECT user_id, claims FROM credentials")).fetchall():
        data = json.loads(claims) if isinstance(claims, str) else dict(claims or {})
        if data.get("nin_verified"):
            bind.execute(sa.text("UPDATE users SET nin_verified_at = :t WHERE id = :id AND nin_verified_at IS NULL"),
                         {"t": now, "id": user_id})

    if 'nin' in cols:
        with op.batch_alter_table('users') as batch:
            if 'ix_users_nin' in _indexes():
                batch.drop_index('ix_users_nin')
            batch.drop_column('nin')


def downgrade() -> None:
    from app.core.crypto import decrypt_str

    if 'nin' not in _cols():
        with op.batch_alter_table('users') as batch:
            batch.add_column(sa.Column('nin', sa.String(), nullable=True))
            batch.create_index('ix_users_nin', ['nin'])
    bind = op.get_bind()
    for user_id, enc in bind.execute(sa.text("SELECT id, nin_enc FROM users WHERE nin_enc IS NOT NULL")).fetchall():
        bind.execute(sa.text("UPDATE users SET nin = :n WHERE id = :id"), {"n": decrypt_str(enc), "id": user_id})
    with op.batch_alter_table('users') as batch:
        for name in ('nin_enc', 'nin_last4', 'date_of_birth', 'nin_verified_at'):
            if name in _cols():
                batch.drop_column(name)
