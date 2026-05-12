"""T1 / T8: per-chunk failures are isolated; parallelism honored."""
from __future__ import annotations

import asyncio

import pytest

from copytrader.chain.client import ChunkResult, JsonRpcClient, _split


def test_split_basic() -> None:
    assert _split(0, 9, 5) == [(0, 4), (5, 9)]


def test_split_unaligned() -> None:
    # 0..12 in chunks of 5 -> (0,4), (5,9), (10,12)
    assert _split(0, 12, 5) == [(0, 4), (5, 9), (10, 12)]


def test_split_single_chunk() -> None:
    assert _split(100, 102, 1000) == [(100, 102)]


def test_split_exact_multiple() -> None:
    assert _split(0, 19, 10) == [(0, 9), (10, 19)]


@pytest.mark.asyncio
async def test_iter_logs_yields_failed_chunks_without_stopping(monkeypatch) -> None:
    """A failing chunk must not break the iterator (T1)."""
    client = JsonRpcClient("https://x.example.com/v2/dummykeyabcdefghij", max_parallel=2)

    call_count = {"n": 0}

    async def fake_logs_range(from_block, to_block, topics, addresses):  # noqa: ARG001
        call_count["n"] += 1
        if from_block == 1000:
            raise RuntimeError("simulated chunk failure")
        # one synthetic log per non-failing chunk
        return [{"blockNumber": hex(from_block), "logIndex": "0x0",
                 "transactionHash": "0x" + "00" * 32, "topics": [], "data": "0x",
                 "address": "0x0"}]

    monkeypatch.setattr(client, "_logs_range", fake_logs_range)

    results: list[ChunkResult] = []
    async for chunk in client.iter_logs(
        from_block=0, to_block=2999, topics=[None], addresses=[], chunk_size=1000,
    ):
        results.append(chunk)

    await client.aclose()
    statuses = sorted(c.status for c in results)
    assert "FAILED" in statuses
    assert statuses.count("OK") >= 1, f"non-failed chunks should still yield: {statuses}"
    assert len(results) == 3, f"got {len(results)} chunks, expected 3"


@pytest.mark.asyncio
async def test_iter_logs_concurrent_calls_capped(monkeypatch) -> None:
    client = JsonRpcClient("https://x.example.com", max_parallel=2)
    in_flight = {"now": 0, "max": 0}
    lock = asyncio.Lock()

    async def fake(from_block, to_block, topics, addresses):  # noqa: ARG001
        async with lock:
            in_flight["now"] += 1
            in_flight["max"] = max(in_flight["max"], in_flight["now"])
        await asyncio.sleep(0.02)
        async with lock:
            in_flight["now"] -= 1
        return []

    monkeypatch.setattr(client, "_logs_range", fake)
    chunks = []
    async for c in client.iter_logs(
        from_block=0, to_block=999, topics=[None], addresses=[], chunk_size=100,
    ):
        chunks.append(c)
    await client.aclose()
    assert in_flight["max"] <= 2, f"semaphore breached: {in_flight['max']}"
    assert len(chunks) == 10
