"""Detect a database whose schema is behind the code.

Without this, an un-migrated database makes every query that touches a new
column fail with a bare 500 — which the frontend used to show as "Invalid email
or password". At startup we compare the database's Alembic revision with the
code's head revision:

- fresh database (no tables before init_db): init_db() just created every table
  at the current schema, so it is stamped at head;
- revision == head: fine;
- anything else: the API answers 503 with the exact command to run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import sqlalchemy
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import AsyncEngine

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
UPGRADE_HINT = "cd backend && uv run alembic upgrade head"


@dataclass
class SchemaStatus:
    ok: bool
    db_revision: str | None
    head_revision: str
    message: str | None = None


def head_revision() -> str:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent / "migrations"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    assert head is not None
    return head


async def has_table(engine: AsyncEngine, name: str) -> bool:
    async with engine.connect() as conn:
        return await conn.run_sync(lambda c: sqlalchemy.inspect(c).has_table(name))


async def _db_revision(engine: AsyncEngine) -> str | None:
    if not await has_table(engine, "alembic_version"):
        return None
    async with engine.connect() as conn:
        row = (await conn.execute(sqlalchemy.text("SELECT version_num FROM alembic_version"))).first()
    return row[0] if row else None


async def _stamp(engine: AsyncEngine, revision: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(sqlalchemy.text(
            "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        await conn.execute(sqlalchemy.text("DELETE FROM alembic_version"))
        await conn.execute(sqlalchemy.text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": revision})


async def check_schema(engine: AsyncEngine, *, was_empty: bool) -> SchemaStatus:
    """Call after init_db(). `was_empty`: no `users` table existed before init_db ran."""
    head = head_revision()
    current = await _db_revision(engine)
    if current is None and was_empty:
        await _stamp(engine, head)
        return SchemaStatus(ok=True, db_revision=head, head_revision=head)
    if current == head:
        return SchemaStatus(ok=True, db_revision=current, head_revision=head)
    return SchemaStatus(
        ok=False,
        db_revision=current,
        head_revision=head,
        message=(
            f"Database schema is out of date (database at {current or 'no revision'}, "
            f"code expects {head}). Run: {UPGRADE_HINT}"
        ),
    )
