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
    return n


def mark_blocks_seen(blocks: dict[int, int]) -> None:
    """blocks: {block_number: log_count}."""
    if not blocks:
        return
    rows = [{"block_number": b, "log_count": c} for b, c in blocks.items()]
    with get_session() as s:
        stmt = pg_insert(BlockSeen).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=[BlockSeen.block_number])
        s.execute(stmt)
