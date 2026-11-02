"""billing per business: plan on organisations + invoices

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = 'a3b4c5d6e7f8'
down_revision = 'f2a3b4c5d6e7'
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
    _add_column('organisations', sa.Column('plan_code', sa.String(), nullable=False, server_default='starter'))
    _add_column('organisations', sa.Column('plan_period_start', sa.DateTime(), nullable=True))
    _add_column('organisations', sa.Column('plan_period_end', sa.DateTime(), nullable=True))
    _create_table(
        'invoices',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('org_id', sa.String(), nullable=False),
        sa.Column('number', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('plan_code', sa.String(), nullable=False),
        sa.Column('period_start', sa.DateTime(), nullable=False),
        sa.Column('period_end', sa.DateTime(), nullable=False),
        sa.Column('amount_kobo', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('bachs_reference', sa.String(), nullable=True),
        sa.Column('checkout_url', sa.String(), nullable=True),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organisations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    _create_index(op.f('ix_invoices_org_id'), 'invoices', ['org_id'], unique=False)
    _create_index(op.f('ix_invoices_number'), 'invoices', ['number'], unique=True)
    _create_index(op.f('ix_invoices_status'), 'invoices', ['status'], unique=False)
    _create_index(op.f('ix_invoices_bachs_reference'), 'invoices', ['bachs_reference'], unique=True)


def downgrade() -> None:
    for ix in ('bachs_reference', 'status', 'number', 'org_id'):
        op.drop_index(op.f(f'ix_invoices_{ix}'), table_name='invoices')
    op.drop_table('invoices')
    with op.batch_alter_table('organisations') as b:
        for c in ('plan_period_end', 'plan_period_start', 'plan_code'):
            b.drop_column(c)
