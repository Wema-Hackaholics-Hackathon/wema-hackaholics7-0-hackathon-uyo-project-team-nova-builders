"""Delete rows and everything that depends on them — on any database.

The models declare ON DELETE CASCADE / SET NULL, but SQLite only enforces them
with `PRAGMA foreign_keys=ON` (never enabled here), so raw deletes left orphans
(e.g. credentials of purged users). delete_cascade() follows the declared
foreign keys in application code: CASCADE children are deleted first
(recursively), SET NULL references are cleared. On Postgres the database would
do the same; doing it explicitly keeps both backends identical.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, Table, delete, select, update
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


def _referencing(table: Table) -> list[tuple[Table, Any, str | None]]:
    """(child table, child FK column, ondelete) for every FK pointing at `table`."""
    out: list[tuple[Table, Any, str | None]] = []
    for child in SQLModel.metadata.tables.values():
        for fk in child.foreign_keys:
            if fk.column.table is table:
                out.append((child, fk.parent, fk.ondelete))
    return out


async def delete_cascade(db: AsyncSession, table_name: str, ids: Sequence[Any]) -> int:
    """Delete rows of `table_name` with these primary keys, plus dependants. Caller commits."""
    if not ids:
        return 0
    table = SQLModel.metadata.tables[table_name]
    pk = list(table.primary_key.columns)[0]
    for child, fk_col, ondelete in _referencing(table):
        if (ondelete or "").upper() == "SET NULL":
            await db.execute(update(child).where(fk_col.in_(ids)).values({fk_col.name: None}))
        else:   # CASCADE (and undeclared, which would otherwise leave orphans)
            child_pk = list(child.primary_key.columns)[0]
            child_ids = list((await db.execute(select(child_pk).where(fk_col.in_(ids)))).scalars())
            await delete_cascade(db, child.name, child_ids)
    result = cast(CursorResult[Any], await db.execute(delete(table).where(pk.in_(ids))))
    return result.rowcount or 0
