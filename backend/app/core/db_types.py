"""Portable UTC datetime column type.

Models create timezone-aware UTC datetimes, but every column is a plain
`TIMESTAMP` (without time zone). SQLite silently drops the tzinfo; asyncpg
(Postgres) refuses aware values for such columns ("can't subtract offset-naive
and offset-aware datetimes").

UTCDateTime stores naive UTC (what both databases already hold — no data
migration) and always returns aware UTC, so Python comparisons are consistent
on every backend. Applied to all DateTime columns by use_utc_datetimes().
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, MetaData
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value   # naive values are taken to be UTC already

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, str):   # raw SQLite text, just in case
            value = datetime.fromisoformat(value)
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def use_utc_datetimes(metadata: MetaData) -> None:
    """Swap every plain DateTime column in the metadata for UTCDateTime."""
    for table in metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, DateTime) and not isinstance(column.type, UTCDateTime):
                column.type = UTCDateTime()
