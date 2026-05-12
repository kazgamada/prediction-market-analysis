"""Dead-letter queue for failed RPC chunks (T1 prevention)."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from copytrader.db.engine import get_session
from copytrader.db.models import RpcDeadLetter

log = logging.getLogger(__name__)

MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 30  # 30s, 60s, 120s, 240s, 480s


def push(kind: str, request: dict, error_text: str) -> int:
    with get_session() as s:
        row = RpcDeadLetter(
            kind=kind,
            request=request,
            error_text=error_text,
        )
        s.add(row)
        s.flush()
        return row.id


def pending(limit: int = 50) -> list[RpcDeadLetter]:
    now = datetime.now(UTC)
    with get_session() as s:
        rows = s.execute(
            select(RpcDeadLetter)
            .where(RpcDeadLetter.resolved_at.is_(None))
            .where(RpcDeadLetter.next_retry <= now)
            .order_by(RpcDeadLetter.next_retry)
            .limit(limit)
        ).scalars().all()
        # Detach from session so caller can use after `with` exits.
        for r in rows:
            s.expunge(r)
        return list(rows)


def mark_retry(dl_id: int, error_text: str) -> None:
    with get_session() as s:
        row = s.get(RpcDeadLetter, dl_id)
        if row is None:
            return
        row.retries += 1
        row.error_text = error_text
        backoff_s = BACKOFF_BASE_SECONDS * (2 ** (row.retries - 1))
        row.next_retry = datetime.now(UTC) + timedelta(seconds=backoff_s)
        if row.retries >= MAX_RETRIES:
            log.error("dead-letter id=%d gave up after %d retries", dl_id, row.retries)


def mark_resolved(dl_id: int) -> None:
    with get_session() as s:
        s.execute(
            update(RpcDeadLetter)
            .where(RpcDeadLetter.id == dl_id)
            .values(resolved_at=datetime.now(UTC))
        )


def count_unresolved() -> int:
    with get_session() as s:
        return int(
            s.execute(
                select(__import__("sqlalchemy").func.count())
                .select_from(RpcDeadLetter)
                .where(RpcDeadLetter.resolved_at.is_(None))
            ).scalar_one()
        )
