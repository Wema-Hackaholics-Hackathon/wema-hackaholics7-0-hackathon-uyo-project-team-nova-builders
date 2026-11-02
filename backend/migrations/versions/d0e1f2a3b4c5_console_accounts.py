"""business console accounts, separate from FOID user accounts

Adds console_users, console_refresh_tokens, console_otps. Organisation
membership (org_members) and organisations.created_by now point at
console_users instead of users.

Existing data: every FOID user who is a member (or creator) of an organisation
gets a console account with the same name, email and password hash, marked
email-verified, so existing organisations keep their owners and nobody is
locked out. From here on the two accounts are independent — changing one
password does not change the other.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-11-02
"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = 'd0e1f2a3b4c5'
down_revision = 'c9d0e1f2a3b4'
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

# Lets batch mode (SQLite) address foreign keys that were created without a name.
_NC = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def _insp() -> sa.engine.Inspector:
    return sa.inspect(op.get_bind())


def _fk_name(table: str, column: str, referred: str) -> str:
    for fk in _insp().get_foreign_keys(table):
        if fk['constrained_columns'] == [column] and fk['referred_table'] == referred:
            return fk['name'] or f"fk_{table}_{column}_{referred}"
    raise RuntimeError(f"no FK {table}.{column} → {referred}")


def _swap_created_by_fk(old: str, new: str, mapping: dict[str, str]) -> None:
    """organisations.created_by: drop FK to `old`, remap the ids, add FK to `new`."""
    with op.batch_alter_table('organisations', naming_convention=_NC) as b:
        b.drop_constraint(_fk_name('organisations', 'created_by', old), type_='foreignkey')
    bind = op.get_bind()
    for org_id, created_by in bind.execute(sa.text("SELECT id, created_by FROM organisations")).all():
        bind.execute(sa.text("UPDATE organisations SET created_by=:c WHERE id=:o"),
                     {"c": mapping.get(created_by) if created_by else None, "o": org_id})
    with op.batch_alter_table('organisations', naming_convention=_NC) as b:
        b.create_foreign_key(f"fk_organisations_created_by_{new}", new, ['created_by'], ['id'], ondelete='SET NULL')


def _rebuild_members(member_col: str, referred: str, rows: list[tuple[str, str, str, str, object]]) -> None:
    """Replace org_members with a copy whose person column is `member_col` → `referred`."""
    op.create_table(
        'org_members_new',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('org_id', sa.String(), nullable=False),
        sa.Column(member_col, sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organisations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint([member_col], [f'{referred}.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_id', member_col),
    )
    if rows:
        op.bulk_insert(sa.table('org_members_new', sa.column('id'), sa.column('org_id'), sa.column(member_col),
                                sa.column('role'), sa.column('created_at')),
                       [dict(zip(('id', 'org_id', member_col, 'role', 'created_at'), r)) for r in rows])
    op.drop_table('org_members')
    op.rename_table('org_members_new', 'org_members')
    op.create_index(op.f('ix_org_members_org_id'), 'org_members', ['org_id'], unique=False)
    op.create_index(op.f(f'ix_org_members_{member_col}'), 'org_members', [member_col], unique=False)


def upgrade() -> None:
    _create_table(
        'console_users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('first_name', sa.String(), nullable=False),
        sa.Column('last_name', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('email_verified_at', sa.DateTime(), nullable=True),
        sa.Column('last_active_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_console_users_email'), 'console_users', ['email'], unique=True)
    _create_table(
        'console_refresh_tokens',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('console_user_id', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['console_user_id'], ['console_users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_console_refresh_tokens_console_user_id'), 'console_refresh_tokens', ['console_user_id'], unique=False)
    _create_index(op.f('ix_console_refresh_tokens_token_hash'), 'console_refresh_tokens', ['token_hash'], unique=True)
    _create_table(
        'console_otps',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('console_user_id', sa.String(), nullable=False),
        sa.Column('purpose', sa.String(), nullable=False),
        sa.Column('code_hash', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['console_user_id'], ['console_users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_console_otps_console_user_id'), 'console_otps', ['console_user_id'], unique=False)

    # ── console accounts for existing org members / creators ────────────────
    bind = op.get_bind()
    user_ids = {r[0] for r in bind.execute(sa.text("SELECT user_id FROM org_members")).all()}
    user_ids |= {r[0] for r in bind.execute(sa.text("SELECT created_by FROM organisations WHERE created_by IS NOT NULL")).all()}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    to_console: dict[str, str] = {}
    for uid in sorted(user_ids):
        u = bind.execute(sa.text("SELECT first_name, last_name, email, hashed_password FROM users WHERE id=:u"),
                         {"u": uid}).first()
        if u is None:
            continue
        cid = str(uuid.uuid4())
        bind.execute(sa.text(
            "INSERT INTO console_users (id, first_name, last_name, email, hashed_password, email_verified_at, created_at) "
            "VALUES (:id, :f, :l, :e, :p, :now, :now)"),
            {"id": cid, "f": u[0], "l": u[1], "e": u[2].lower(), "p": u[3], "now": now})
        to_console[uid] = cid

    members = bind.execute(sa.text("SELECT id, org_id, user_id, role, created_at FROM org_members")).all()
    _rebuild_members('console_user_id', 'console_users',
                     [(m[0], m[1], to_console[m[2]], m[3], m[4]) for m in members if m[2] in to_console])
    _swap_created_by_fk('users', 'console_users', to_console)
    for old, new in to_console.items():
        bind.execute(sa.text("UPDATE api_keys SET created_by=:n WHERE created_by=:o"), {"n": new, "o": old})


def downgrade() -> None:
    """Maps console accounts back to FOID users by email; memberships without a match are dropped."""
    bind = op.get_bind()
    to_user: dict[str, str] = {}
    for cid, email in bind.execute(sa.text("SELECT id, email FROM console_users")).all():
        u = bind.execute(sa.text("SELECT id FROM users WHERE lower(email)=:e"), {"e": email}).first()
        if u:
            to_user[cid] = u[0]
    members = bind.execute(sa.text("SELECT id, org_id, console_user_id, role, created_at FROM org_members")).all()
    _rebuild_members('user_id', 'users', [(m[0], m[1], to_user[m[2]], m[3], m[4]) for m in members if m[2] in to_user])
    _swap_created_by_fk('console_users', 'users', to_user)
    for old, new in to_user.items():
        bind.execute(sa.text("UPDATE api_keys SET created_by=:n WHERE created_by=:o"), {"n": new, "o": old})
    op.drop_table('console_otps')
    op.drop_table('console_refresh_tokens')
    op.drop_table('console_users')
