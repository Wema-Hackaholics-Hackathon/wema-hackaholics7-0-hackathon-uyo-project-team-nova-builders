"""face liveness SDK: face enrolments, used nonces, liveness attempts

Replaces the Haar-cascade liveness_sessions table (sessions now live in memory)
with face_enrolments / used_liveness_nonces / liveness_attempts, and adds
users.liveness_verified_at.

identity_verified used to default to True at signup.  It is now only set by
enrolling a face through a passed liveness check, so existing users without a
liveness selfie have the claim reset to False.

Written defensively (inspect before create/drop) because init_db() runs
SQLModel.metadata.create_all on startup and may already have created the new
tables — and liveness_sessions / liveness_selfie_url were never migrated.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-01
"""

import sqlalchemy as sa
from alembic import op

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _user_columns() -> set[str]:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns('users')}


def upgrade() -> None:
    cols = _user_columns()
    with op.batch_alter_table('users') as batch:
        if 'liveness_selfie_url' not in cols:
            batch.add_column(sa.Column('liveness_selfie_url', sa.String(), nullable=True))
        if 'liveness_verified_at' not in cols:
            batch.add_column(sa.Column('liveness_verified_at', sa.DateTime(), nullable=True))

    if not _has_table('face_enrolments'):
        op.create_table(
            'face_enrolments',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('user_id', sa.String(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('template_enc', sa.LargeBinary(), nullable=False),
            sa.Column('face_png', sa.LargeBinary(), nullable=False),
            sa.Column('face_sha256', sa.String(), nullable=False),
            sa.Column('receipt', sa.Text(), nullable=False),
            sa.Column('face_quality', sa.Float(), nullable=False),
            sa.Column('model', sa.String(), nullable=False),
            sa.Column('consent_at', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_face_enrolments_user_id', 'face_enrolments', ['user_id'], unique=True)

    if not _has_table('used_liveness_nonces'):
        op.create_table(
            'used_liveness_nonces',
            sa.Column('nonce', sa.String(), primary_key=True),
            sa.Column('user_id', sa.String(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('purpose', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_used_liveness_nonces_user_id', 'used_liveness_nonces', ['user_id'])

    if not _has_table('liveness_attempts'):
        op.create_table(
            'liveness_attempts',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('user_id', sa.String(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('nonce', sa.String(), nullable=False),
            sa.Column('purpose', sa.String(), nullable=False),
            sa.Column('passed', sa.Boolean(), nullable=False),
            sa.Column('fail_reason', sa.String(), nullable=True),
            sa.Column('face_quality', sa.Float(), nullable=True),
            sa.Column('real_score', sa.Float(), nullable=True),
            sa.Column('match_score', sa.Float(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_liveness_attempts_user_id', 'liveness_attempts', ['user_id'])

    if _has_table('liveness_sessions'):
        op.drop_table('liveness_sessions')

    # Existing users kept identity_verified=True from the old default; reset it
    # unless they actually completed the old liveness flow.
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT c.id, c.claims FROM credentials c JOIN users u ON u.id = c.user_id "
        "WHERE u.liveness_selfie_url IS NULL"
    )).fetchall()
    import json
    claims_param = "CAST(:claims AS JSON)" if bind.dialect.name == "postgresql" else ":claims"
    for cred_id, claims in rows:
        data = json.loads(claims) if isinstance(claims, str) else dict(claims)
        if data.get('identity_verified'):
            data['identity_verified'] = False
            bind.execute(
                sa.text(f"UPDATE credentials SET claims = {claims_param} WHERE id = :id"),
                {"claims": json.dumps(data), "id": cred_id},
            )


def downgrade() -> None:
    for name in ('liveness_attempts', 'used_liveness_nonces', 'face_enrolments'):
        if _has_table(name):
            op.drop_table(name)
    if 'liveness_verified_at' in _user_columns():
        with op.batch_alter_table('users') as batch:
            batch.drop_column('liveness_verified_at')
