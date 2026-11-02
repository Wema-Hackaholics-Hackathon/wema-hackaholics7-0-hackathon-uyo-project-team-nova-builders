"""encrypt users.bvn; reset bvn_validated (it was never really checked)

The BVN was stored in plain text (and indexed) and returned in full by the API.
It becomes bvn_enc (Fernet, DATA_ENCRYPTION_KEY) + bvn_last4 + bvn_hash (keyed,
PII_HASH_KEY), and the plain `bvn` column and its index are dropped.

Every bvn_validated claim is reset to False: until now PATCH /auth/me/bvn set it
for any 11 digits without a registry lookup, and businesses could read that
claim. Users verify again through the real check (registry + name match).

Set DATA_ENCRYPTION_KEY and PII_HASH_KEY BEFORE running this in production.
Downgrade needs the same key.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-11-02
"""

import json

import sqlalchemy as sa
from alembic import op

revision = 'c5d6e7f8a9b0'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None

_NEW = (('bvn_enc', sa.String()), ('bvn_last4', sa.String()), ('bvn_hash', sa.String()), ('bvn_verified_at', sa.DateTime()))


def _cols() -> set[str]:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns('users')}


def _indexes() -> set[str]:
    return {ix['name'] for ix in sa.inspect(op.get_bind()).get_indexes('users')}


def upgrade() -> None:
    from app.core.crypto import encrypt_str, pii_hash

    cols = _cols()
    with op.batch_alter_table('users') as batch:
        for name, type_ in _NEW:
            if name not in cols:
                batch.add_column(sa.Column(name, type_, nullable=True))
    if 'ix_users_bvn_hash' not in _indexes():
        op.create_index('ix_users_bvn_hash', 'users', ['bvn_hash'])

    bind = op.get_bind()
    if 'bvn' in cols:
        for user_id, bvn in bind.execute(sa.text("SELECT id, bvn FROM users WHERE bvn IS NOT NULL AND bvn <> ''")).fetchall():
            bvn = bvn.strip()
            bind.execute(sa.text("UPDATE users SET bvn_enc = :e, bvn_last4 = :l, bvn_hash = :h WHERE id = :id"),
                         {"e": encrypt_str(bvn), "l": bvn[-4:], "h": pii_hash(bvn), "id": user_id})

    for cred_id, claims in bind.execute(sa.text("SELECT id, claims FROM credentials")).fetchall():
        data = json.loads(claims) if isinstance(claims, str) else dict(claims or {})
        if data.get("bvn_validated"):
            data["bvn_validated"] = False
            bind.execute(sa.text("UPDATE credentials SET claims = :c WHERE id = :id"), {"c": json.dumps(data), "id": cred_id})

    if 'bvn' in cols:
        with op.batch_alter_table('users') as batch:
            if 'ix_users_bvn' in _indexes():
                batch.drop_index('ix_users_bvn')
            batch.drop_column('bvn')


def downgrade() -> None:
    from app.core.crypto import decrypt_str

    if 'bvn' not in _cols():
        with op.batch_alter_table('users') as batch:
            batch.add_column(sa.Column('bvn', sa.String(), nullable=True))
            batch.create_index('ix_users_bvn', ['bvn'])
    bind = op.get_bind()
    for user_id, enc in bind.execute(sa.text("SELECT id, bvn_enc FROM users WHERE bvn_enc IS NOT NULL")).fetchall():
        bind.execute(sa.text("UPDATE users SET bvn = :b WHERE id = :id"), {"b": decrypt_str(enc), "id": user_id})
    if 'ix_users_bvn_hash' in _indexes():
        op.drop_index('ix_users_bvn_hash', table_name='users')
    with op.batch_alter_table('users') as batch:
        for name, _ in _NEW:
            if name in _cols():
                batch.drop_column(name)
