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


def _row(t) -> dict:
    return dict(
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


def _flush(rows: list[dict], cursor_name: str, block_number: int) -> int:
    """trade insert と cursor 更新を 1 トランザクションで commit。

    まとめてコミットするので、interrupted した場合は cursor が指す位置までは
    確実に永続化されている。それより先のチャンクは ON CONFLICT DO NOTHING で
    再実行時に冪等。

    cursor は **単調増加のみ** にする。古い from_block で再実行された場合や
    並列実行で順序が前後した場合でも、進捗を後退させない。

    INSERT は **PostgreSQL の 65535 パラメータ制限** を考慮して、
    1 statement あたり高々 PG_MAX_PARAMS_PER_STMT パラメータに分割する。
    transaction は 1 つに保つので atomicity は維持される。
    """
    PG_MAX_PARAMS_PER_STMT = 60_000
    with session_scope() as session:
        if rows:
            cols = len(rows[0])
            batch_size = max(1, PG_MAX_PARAMS_PER_STMT // cols)
            for i in range(0, len(rows), batch_size):
                chunk = rows[i : i + batch_size]
                stmt = insert(Trade).values(chunk).on_conflict_do_nothing(
                    index_elements=["tx_hash", "log_index"]
                )
                session.execute(stmt)
        cur = session.get(IngestCursor, cursor_name)
        now = datetime.now(timezone.utc)
        if cur is None:
            session.add(IngestCursor(name=cursor_name, block_number=block_number, updated_at=now))
        else:
            if block_number > (cur.block_number or 0):
                cur.block_number = block_number
            cur.updated_at = now
    return len(rows)


def _read_cursor(name: str) -> int | None:
    with session_scope() as session:
        cur = session.get(IngestCursor, name)
        return cur.block_number if cur else None


def _max_indexed_block(exchange: str) -> int | None:
    """この exchange で実際に DB に取り込み済みの最大 block。

    cursor が古い値で残っていても、trade テーブルから「ここまで処理済み」を
    再構成できるので、無駄な再取得を避けられる。
    """
    from sqlalchemy import func, select

    with session_scope() as session:
        return session.execute(
            select(func.max(Trade.block_number)).where(Trade.exchange == exchange)
        ).scalar()


# Polygon は約 2 秒/block (1日あたりおよそ 43,200 ブロック)。
# 30日分 ≈ 1.3M ブロックなので、catchup を直近 N 日分に限定すると現実的な時間で完走できる。
POLYGON_BLOCKS_PER_DAY = 43_200


def backfill(
    from_block: int | None = None,
    to_block: int | None = None,
    chunk_size: int = 2000,
    max_workers: int = 10,
    commit_every: int = 5,
    sample_block_ts: bool = True,
    recent_days: int | None = None,
) -> int:
    """Backfill both CTF and NegRisk exchanges over a block range.

    block timestamps are sampled per chunk-end (cheap) and applied to all trades
    in that chunk; precision within a 1k-block window is ~30 minutes which is
    sufficient for ranking. The live stream attaches exact timestamps.

    `commit_every` 個のチャンクをまとめて DB にコミットするので、
    トランザクション数が 1/N に減り backfill が大幅に速くなる。

    `recent_days` が指定された場合、`from_block` 未指定時の開始ブロックを
    `max(cursor, head - recent_days * blocks_per_day)` に切り上げる。
    古い履歴を諦めることで catchup を有限時間で完走できる。`from_block` を
    明示的に渡せばこの制限は無視されるので、完全履歴も従来通り取り込める。
    """
    settings = get_settings()
    client = PolygonClient()
    head = client.block_number()
    end = to_block if to_block is not None else head
    recent_floor: int | None = None
    if from_block is None and recent_days is not None and recent_days > 0:
        recent_floor = max(0, head - recent_days * POLYGON_BLOCKS_PER_DAY)

    log.info(
        "backfill to %s (head=%s) chunk=%s workers=%s commit_every=%s from_block=%s",
        end, head, chunk_size, max_workers, commit_every, from_block,
    )
    total = 0

    for exchange in ("ctf", "negrisk"):
        cursor_name = f"backfill_{exchange}"
        if from_block is not None:
            exch_start = from_block
        else:
            cursor_block = _read_cursor(cursor_name)
            max_trade_block = _max_indexed_block(exchange)
            known = [b for b in (cursor_block, max_trade_block) if b is not None]
            if known:
                # cursor or 取り込み済みの最大 block の **大きい方** + 1 から再開。
                # これで cursor が誤って巻き戻されていても進捗は失われない。
                exch_start = max(known) + 1
            else:
                exch_start = settings.polymarket_start_block
            if recent_floor is not None and exch_start < recent_floor:
                log.info(
                    "exchange=%s skipping ancient blocks: %s -> %s (recent_days=%s)",
                    exchange, exch_start, recent_floor, recent_days,
                )
                exch_start = recent_floor
        if exch_start > end:
            log.info("exchange=%s already up-to-date (cursor=%s end=%s)", exchange, exch_start - 1, end)
            continue
        log.info("exchange=%s resume from block %s -> %s", exchange, exch_start, end)

        buffer_rows: list[dict] = []
        buffer_chunks = 0
        last_chunk_end = exch_start - 1

        for logs, chunk_start, chunk_end in client.iter_logs(
            exch_start, end, exchange=exchange,
            chunk_size=chunk_size, max_workers=max_workers,
        ):
            log.debug(
                "exchange=%s chunk start=%s end=%s raw_logs=%s",
                exchange, chunk_start, chunk_end, len(logs),
            )
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

            for t in decoded:
                if t.block_number in block_ts:
                    attach_timestamp(t, block_ts[t.block_number])
                buffer_rows.append(_row(t))

            last_chunk_end = chunk_end
            buffer_chunks += 1

            if buffer_chunks >= commit_every:
                saved = _flush(buffer_rows, cursor_name, last_chunk_end)
                total += saved
                log.info(
                    "exchange=%s flushed up_to=%s raw_logs_in_chunk=%s decoded=%s rows_saved=%s total=%s",
                    exchange, last_chunk_end, len(logs), len(decoded), saved, total,
                )
                buffer_rows = []
                buffer_chunks = 0

        if buffer_chunks > 0:
            saved = _flush(buffer_rows, cursor_name, last_chunk_end)
            total += saved
            log.info(
                "exchange=%s final flush up_to=%s rows=%s total=%s",
                exchange, last_chunk_end, saved, total,
            )

    return total
