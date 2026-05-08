"""Backfill OrderFilled trades from a block range into the database."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert

from copytrader.chain.client import PolygonClient
from copytrader.config import get_settings
from copytrader.db import session_scope
from copytrader.indexer.decoder import attach_timestamp, decode
from copytrader.models import IngestCursor, Trade

log = logging.getLogger(__name__)


def _persist(decoded: list, block_ts: dict[int, int]) -> int:
    if not decoded:
        return 0
    rows = []
    for t in decoded:
        if t.block_number in block_ts:
            attach_timestamp(t, block_ts[t.block_number])
        rows.append(
            dict(
                tx_hash=t.tx_hash,
                log_index=t.log_index,
                block_number=t.block_number,
                block_timestamp=t.block_timestamp,
                exchange=t.exchange,
                order_hash=t.order_hash,
                maker=t.maker,
                taker=t.taker,
                maker_asset_id=t.maker_asset_id,
                taker_asset_id=t.taker_asset_id,
                maker_amount=t.maker_amount,
                taker_amount=t.taker_amount,
                fee=t.fee,
                token_id=t.token_id,
                side=t.side,
                price=t.price,
                size=t.size,
                notional_usd=t.notional_usd,
            )
        )
    with session_scope() as session:
        stmt = insert(Trade).values(rows).on_conflict_do_nothing(
            index_elements=["tx_hash", "log_index"]
        )
        session.execute(stmt)
    return len(rows)


def _read_cursor(name: str) -> int | None:
    with session_scope() as session:
        cur = session.get(IngestCursor, name)
        return cur.block_number if cur else None


def _write_cursor(name: str, block_number: int) -> None:
    with session_scope() as session:
        cur = session.get(IngestCursor, name)
        now = datetime.now(timezone.utc)
        if cur is None:
            session.add(IngestCursor(name=name, block_number=block_number, updated_at=now))
        else:
            cur.block_number = block_number
            cur.updated_at = now


def backfill(
    from_block: int | None = None,
    to_block: int | None = None,
    chunk_size: int = 1000,
    sample_block_ts: bool = True,
) -> int:
    """Backfill both CTF and NegRisk exchanges over a block range.

    block timestamps are sampled per chunk-end (cheap) and applied to all trades
    in that chunk; precision within a 1k-block window is ~30 minutes which is
    sufficient for ranking. The live stream attaches exact timestamps.
    """
    settings = get_settings()
    client = PolygonClient()
    head = client.block_number()
    start = from_block if from_block is not None else (
        _read_cursor("backfill") or settings.polymarket_start_block
    )
    end = to_block if to_block is not None else head

    log.info("backfill from %s to %s (head=%s)", start, end, head)
    total = 0

    for exchange in ("ctf", "negrisk"):
        for logs, chunk_start, chunk_end in client.iter_logs(
            start, end, exchange=exchange, chunk_size=chunk_size
        ):
            decoded = []
            for raw in logs:
                try:
                    args = client.decode_log(raw, exchange)
                    t = decode(raw, args, exchange)
                    if t:
                        decoded.append(t)
                except Exception as e:
                    log.warning("decode failed: %s", e)

            block_ts: dict[int, int] = {}
            if decoded and sample_block_ts:
                try:
                    block_ts[chunk_end] = client.block_timestamp(chunk_end)
                except Exception:
                    pass

            saved = _persist(decoded, block_ts)
            total += saved
            _write_cursor(f"backfill_{exchange}", chunk_end)
            log.info(
                "exchange=%s chunk=%s..%s logs=%s saved=%s total=%s",
                exchange,
                chunk_start,
                chunk_end,
                len(logs),
                saved,
                total,
            )

    return total
