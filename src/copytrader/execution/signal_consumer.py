"""Convert watchlist OrderFilled trades into signals rows.

Called by the indexer after each trade is persisted: if the taker is an
active watchlist wallet, INSERT a signals row with status=PENDING and
execute_after = now + copy_delay_seconds.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from copytrader.db import settings_table
from copytrader.db.engine import get_session
from copytrader.db.models import Signal, Watchlist
from copytrader.execution.order_state import SIGNAL_PENDING

log = logging.getLogger("execution.signal_consumer")


def is_watchlist_active(address: bytes) -> bool:
    with get_session() as s:
        row = s.execute(
            select(Watchlist).where(Watchlist.address == address)
        ).scalar_one_or_none()
        return bool(row and row.active)


def maybe_record_signal(
    *,
    address: bytes,
    token_id: int,
    side: int,
    price: Decimal,
    size_usdc: Decimal,
    trade_ts: datetime,
    tx_hash: bytes | None = None,
    log_index: int | None = None,
    source: str = "watchlist_orderfill",
) -> int | None:
    """If `address` is on the active watchlist, INSERT a signals row.

    Idempotent on the originating trade identity (`tx_hash`, `log_index`):
    the catchup loop and the live WS stream can both observe the same
    OrderFilled log, so we INSERT ... ON CONFLICT DO NOTHING against the
    partial unique index. This dedup is race-safe (enforced by the DB), not
    by a read-then-write check.

    Returns the signal id, or None if not a watchlist address or if the
    signal already existed (duplicate source trade).
    """
    if not is_watchlist_active(address):
        return None

    delay_seconds = int(settings_table.get("copy_delay_seconds") or 30)
    now = datetime.now(UTC)
    execute_after = now + timedelta(seconds=delay_seconds)

    values = {
        "address": address,
        "token_id": Decimal(token_id),
        "side": side,
        "price": price,
        "size_usdc": size_usdc,
        "ts": trade_ts,
        "source": source,
        "tx_hash": tx_hash,
        "log_index": log_index,
        "detected_at": now,
        "execute_after": execute_after,
        "status": SIGNAL_PENDING,
    }
    with get_session() as s:
        stmt = pg_insert(Signal).values(**values)
        if tx_hash is not None:
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["tx_hash", "log_index"],
                index_where=text("tx_hash IS NOT NULL"),
            )
        stmt = stmt.returning(Signal.id)
        sid = s.execute(stmt).scalar_one_or_none()

    if sid is None:
        log.debug(
            "signal skipped (duplicate source trade): addr=%s token=%s tx=%s/%s",
            "0x" + address.hex()[:8], token_id,
            tx_hash.hex()[:8] if tx_hash else None, log_index,
        )
        return None
    log.info(
        "signal recorded: id=%s addr=%s token=%s side=%s execute_after=%s",
        sid, "0x" + address.hex()[:8], token_id, side, execute_after,
    )
    return sid
