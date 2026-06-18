"""Backfill cursor is a contiguous low-water mark (no silent gap skips).

iter_logs yields chunks in completion order (parallel), and chunks can FAIL.
Before the frontier fix, a later successful chunk advanced the cursor past an
earlier failed/missing one, so that range was never re-scanned by catchup =
silent data loss. These tests pin that the cursor only ever reflects a fully
contiguous scanned prefix.
"""
from __future__ import annotations

from copytrader.chain.client import ChunkResult
from copytrader.indexer import cursor as cursor_mod
from copytrader.indexer.backfill import CURSOR_NAME, backfill_range


class _FakeClient:
    """Yields a fixed list of ChunkResults from iter_logs (in given order)."""

    def __init__(self, chunks: list[ChunkResult]) -> None:
        self._chunks = chunks

    async def get_block_timestamp(self, block: int) -> int:
        return 1_700_000_000

    async def iter_logs(self, *, from_block, to_block, topics, addresses, chunk_size):
        for c in self._chunks:
            yield c


async def test_out_of_order_chunks_advance_to_full_frontier(fresh_db) -> None:
    # All three chunks succeed but arrive out of block order.
    chunks = [
        ChunkResult(300, 399, "EMPTY"),
        ChunkResult(100, 199, "EMPTY"),
        ChunkResult(200, 299, "EMPTY"),
    ]
    await backfill_range(_FakeClient(chunks), from_block=100, to_block=399,
                         chunk_size=100)
    assert cursor_mod.get(CURSOR_NAME) == 399


async def test_failed_first_chunk_holds_cursor(fresh_db) -> None:
    # The earliest chunk fails; later ones succeed. Cursor must NOT advance.
    chunks = [
        ChunkResult(200, 299, "EMPTY"),
        ChunkResult(300, 399, "EMPTY"),
        ChunkResult(100, 199, "FAILED", error="boom"),
    ]
    await backfill_range(_FakeClient(chunks), from_block=100, to_block=399,
                         chunk_size=100)
    # No contiguous prefix from 100 → cursor never set.
    assert cursor_mod.get(CURSOR_NAME) is None


async def test_failed_middle_chunk_caps_cursor_below_gap(fresh_db) -> None:
    # Middle chunk fails; the higher chunk succeeded but must not pull the
    # cursor past the gap (this is the silent-data-loss case).
    chunks = [
        ChunkResult(100, 199, "EMPTY"),
        ChunkResult(300, 399, "EMPTY"),
        ChunkResult(200, 299, "FAILED", error="boom"),
    ]
    await backfill_range(_FakeClient(chunks), from_block=100, to_block=399,
                         chunk_size=100)
    assert cursor_mod.get(CURSOR_NAME) == 199


async def test_cursor_never_regresses_on_rerun(fresh_db) -> None:
    cursor_mod.advance(CURSOR_NAME, 399)
    # A later run that only confirms a lower frontier must not move it back.
    chunks = [ChunkResult(100, 199, "EMPTY")]
    await backfill_range(_FakeClient(chunks), from_block=100, to_block=199,
                         chunk_size=100)
    assert cursor_mod.get(CURSOR_NAME) == 399
