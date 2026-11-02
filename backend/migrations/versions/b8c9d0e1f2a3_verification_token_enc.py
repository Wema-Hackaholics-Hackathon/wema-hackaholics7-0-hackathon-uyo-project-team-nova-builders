"""verifications.session_token_enc — let businesses re-fetch an open hosted link

The hosted verification token was stored only as a SHA-256 hash, so
`hosted_url` / `client_token` could be returned exactly once. This adds a
Fernet-encrypted copy (DATA_ENCRYPTION_KEY) so GET /verifications/{id} can
return the link again while the verification is still pending / in progress.
Existing rows stay NULL (their link is simply not re-offered).

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns('verifications')}


def upgrade() -> None:
    if 'session_token_enc' not in _columns():
        with op.batch_alter_table('verifications') as batch:
            batch.add_column(sa.Column('session_token_enc', sa.String(), nullable=True))


def downgrade() -> None:
    if 'session_token_enc' in _columns():
        with op.batch_alter_table('verifications') as batch:
            batch.drop_column('session_token_enc')
