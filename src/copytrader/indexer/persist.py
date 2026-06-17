"""Trade row persistence with chunked upsert (T7 prevention)."""
from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert as pg_insert

from copytrader.chain.decoder import DecodedTrade, decoded_to_row
from copytrader.db.chunked_insert import bulk_upsert
from copytrader.db.engine import get_session
from copytrader.db.models import BlockSeen, Trade

log = logging.getLogger(__name__)


def persist_trades(trades: Sequence[DecodedTrade]) -> int:
    if not trades:
        return 0
    rows = [decoded_to_row(t) for t in trades]
    with get_session() as s:
        n = bulk_upsert(
            s.connection(),
            Trade.__table__,
            rows,
            conflict_index=["tx_hash", "log_index"],
            update_columns=None,  # idempotent: never overwrite trade rows
        )
    log.info("persisted %d trades", n)

    # Phase 1: emit signals for watchlist matches. Errors here must NOT
    # block trade persistence — copy trade is downstream from data ingest.
    try:
        _emit_signals_for_watchlist(trades)
    except Exception as e:  # noqa: BLE001
        log.warning("signal emission failed (ignored): %s", e)

    return n


def _emit_signals_for_watchlist(trades: Sequence[DecodedTrade]) -> None:
    """For each newly-persisted trade whose taker is on the active watchlist,
    record a signals row. Idempotent via (address, token_id, ts) uniqueness
    is enforced by the executor's de-dup, not at the DB level here.
    """
    from copytrader.execution.signal_consumer import maybe_record_signal

    for t in trades:
        row = decoded_to_row(t)
        maybe_record_signal(
            address=row["taker"],
            token_id=int(row["token_id"]),
            side=int(row["side"]),
            price=row["price"],
            size_usdc=row["size_usdc"],
            trade_ts=row["ts"],
        )


def mark_blocks_seen(blocks: dict[int, int]) -> None:
    """blocks: {block_number: log_count}."""
    if not blocks:
        return
    rows = [{"block_number": b, "log_count": c} for b, c in blocks.items()]
    with get_session() as s:
        stmt = pg_insert(BlockSeen).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=[BlockSeen.block_number])
        s.execute(stmt)
