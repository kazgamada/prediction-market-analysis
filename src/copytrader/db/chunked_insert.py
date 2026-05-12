"""Chunked bulk INSERT helper (T7 prevention).

PostgreSQL's wire protocol caps a single statement at 65535 bind parameters.
A naive `INSERT ... VALUES (...), (...), ...` blows past that with even a few
hundred wide rows. This module centralizes the chunk-size computation so
every bulk insert path goes through one well-tested function.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from sqlalchemy import Table
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection

# Pad below the Postgres limit a bit so we never tickle the edge case.
MAX_BIND_PARAMS = 65000


def max_rows_per_chunk(column_count: int) -> int:
    """Compute how many rows fit in one INSERT for a given column count."""
    if column_count <= 0:
        raise ValueError("column_count must be positive")
    n = MAX_BIND_PARAMS // column_count
    if n < 1:
        raise ValueError(
            f"row has too many columns ({column_count}) to fit any rows in a single statement"
        )
    return n


def chunked(seq: Sequence[dict], size: int) -> Iterable[Sequence[dict]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def bulk_upsert(
    conn: Connection,
    table: Table,
    rows: Sequence[dict],
    *,
    conflict_index: Sequence[str],
    update_columns: Sequence[str] | None = None,
) -> int:
    """ON CONFLICT DO {UPDATE|NOTHING} bulk insert in safe chunks.

    Returns total rows attempted (not rows actually changed).
    """
    if not rows:
        return 0
    columns_in_payload = len(rows[0].keys())
    per_chunk = max_rows_per_chunk(columns_in_payload)
    written = 0
    for chunk in chunked(rows, per_chunk):
        stmt = pg_insert(table).values(list(chunk))
        if update_columns:
            stmt = stmt.on_conflict_do_update(
                index_elements=list(conflict_index),
                set_={c: stmt.excluded[c] for c in update_columns},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=list(conflict_index))
        conn.execute(stmt)
        written += len(chunk)
    return written


def chunk_count(row_count: int, column_count: int) -> int:
    """Public helper used by tests."""
    if row_count == 0:
        return 0
    return math.ceil(row_count / max_rows_per_chunk(column_count))
