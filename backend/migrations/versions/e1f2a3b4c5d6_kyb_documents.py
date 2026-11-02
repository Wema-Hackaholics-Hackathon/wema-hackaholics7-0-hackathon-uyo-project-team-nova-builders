"""go-live review: business details + encrypted KYB documents

organisations: tin, registered_address, kyb_submitted_at, kyb_reviewed_at, kyb_note.
kyb_documents: one current file per (org, type), Fernet-encrypted bytes.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = 'e1f2a3b4c5d6'
down_revision = 'd0e1f2a3b4c5'
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

_ORG_COLS = (
    sa.Column('tin', sa.String(), nullable=True),
    sa.Column('registered_address', sa.String(), nullable=True),
    sa.Column('kyb_submitted_at', sa.DateTime(), nullable=True),
    sa.Column('kyb_reviewed_at', sa.DateTime(), nullable=True),
    sa.Column('kyb_note', sa.String(), nullable=True),
)


def upgrade() -> None:
    for col in _ORG_COLS:
        _add_column('organisations', col)
    _create_table(
        'kyb_documents',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('org_id', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('mime', sa.String(), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(), nullable=False),
        sa.Column('data_enc', sa.LargeBinary(), nullable=False),
        sa.Column('uploaded_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organisations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_id', 'type'),
    )
    _create_index(op.f('ix_kyb_documents_org_id'), 'kyb_documents', ['org_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_kyb_documents_org_id'), table_name='kyb_documents')
    op.drop_table('kyb_documents')
    with op.batch_alter_table('organisations') as b:
        for col in reversed(_ORG_COLS):
            b.drop_column(col.name)
