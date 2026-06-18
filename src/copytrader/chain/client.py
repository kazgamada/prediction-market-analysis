"""HTTP JSON-RPC client built around httpx.

Design rules (preventing T1, T3, T4, T8):
  * Per-chunk failures are returned as `ChunkResult(status=FAILED)`, never raised
    past the iterator boundary. The upstream backfill decides whether to retry
    inline or push to the dead-letter table.
  * `redact_url` is applied to every URL appearing in errors.
  * JSON-RPC error bodies are preserved verbatim on the exception.
  * Block ranges are split into chunks and chunks are executed in parallel,
    capped by a semaphore.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from copytrader.chain.errors import (
    RpcAuthError,
    RpcChunkTooLargeError,
    RpcError,
    RpcRateLimitError,
    redact_url,
)

log = logging.getLogger(__name__)


@dataclass
class ChunkResult:
    from_block: int
    to_block: int
    status: str  # 'OK' | 'EMPTY' | 'FAILED'
    logs: list[dict] = field(default_factory=list)
    error: str | None = None
    error_body: Any = None


def _split(from_block: int, to_block: int, size: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    cur = from_block
    while cur <= to_block:
        end = min(cur + size - 1, to_block)
        out.append((cur, end))
        cur = end + 1
    return out


def _classify(status: int, payload: Any, url: str) -> RpcError:
    body = payload
    code = None
    if isinstance(payload, dict) and "error" in payload:
        code = payload["error"].get("code")
    if status in (401, 403):
        return RpcAuthError("RPC auth failed", url=url, status=status, code=code, body=body)
    if status == 429:
        return RpcRateLimitError("RPC rate-limited", url=url, status=status, code=code, body=body)
    msg = "RPC error"
    if isinstance(payload, dict) and "error" in payload:
        em = (payload["error"] or {}).get("message", "")
        if any(s in em.lower() for s in ("more than", "exceeds", "range", "limit exceeded")):
            return RpcChunkTooLargeError(em, url=url, status=status, code=code, body=body)
        msg = em or msg
    return RpcError(msg, url=url, status=status, code=code, body=body)


class JsonRpcClient:
    def __init__(
        self,
        http_url: str,
        *,
        max_parallel: int = 4,
        max_retries: int = 3,
        timeout_s: float = 30.0,
    ):
        self.http_url = http_url
        self.max_parallel = max_parallel
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(timeout=timeout_s)
        self._sem = asyncio.Semaphore(max_parallel)
        self._id = 0

    async def aclose(self) -> None:
        await self._client.aclose()

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def _call(self, method: str, params: list[Any]) -> Any:
        """Single JSON-RPC call with retries on 429/5xx."""
        payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params}
        last: RpcError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await self._client.post(self.http_url, json=payload)
            except httpx.HTTPError as e:
                last = RpcError(
                    f"HTTP transport: {type(e).__name__}: {e}", url=self.http_url
                )
                if attempt >= self.max_retries:
                    raise last from e
                await asyncio.sleep(2 ** attempt)
                continue
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text[:1000]}
            if resp.status_code >= 400 or (isinstance(data, dict) and "error" in data):
                err = _classify(resp.status_code, data, self.http_url)
                if isinstance(err, RpcRateLimitError) and attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    last = err
                    continue
                raise err
            return data.get("result")
        # unreachable
        if last:
            raise last
        raise RpcError("exhausted retries", url=self.http_url)

    async def get_block_number(self) -> int:
        result = await self._call("eth_blockNumber", [])
        return int(result, 16)

    async def get_native_balance(self, address: str) -> int:
        """Native (MATIC/POL) balance in wei."""
        result = await self._call("eth_getBalance", [address, "latest"])
        return int(result, 16)

    async def eth_call(self, to: str, data: str) -> str:
        """Raw eth_call (latest). Returns the hex result string."""
        return await self._call("eth_call", [{"to": to, "data": data}, "latest"])

    async def get_block_timestamp(self, block_number: int) -> int:
        result = await self._call(
            "eth_getBlockByNumber", [hex(block_number), False]
        )
        if not result:
            raise RpcError(f"block {block_number} not found", url=self.http_url)
        return int(result["timestamp"], 16)

    async def _logs_range(
        self,
        from_block: int,
        to_block: int,
        topics: list[str | None],
        addresses: list[str],
    ) -> list[dict]:
        params = [{
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "address": addresses,
            "topics": topics,
        }]
        return await self._call("eth_getLogs", params) or []

    async def iter_logs(
        self,
        *,
        from_block: int,
        to_block: int,
        topics: list[str | None],
        addresses: list[str],
        chunk_size: int = 1000,
    ) -> AsyncIterator[ChunkResult]:
        """Yield one ChunkResult per chunk. Failures yielded as FAILED, never raised.

        T1 prevention: a single chunk failure does not stop the iterator.
        """
        chunks = _split(from_block, to_block, chunk_size)
        log.info(
            "iter_logs: %d chunks across [%d, %d] (chunk_size=%d, parallel=%d)",
            len(chunks), from_block, to_block, chunk_size, self.max_parallel,
        )

        results_q: asyncio.Queue[ChunkResult] = asyncio.Queue()

        async def worker(lo: int, hi: int) -> None:
            async with self._sem:
                started = time.time()
                try:
                    logs = await self._logs_range(lo, hi, topics, addresses)
                    if logs:
                        await results_q.put(
                            ChunkResult(lo, hi, status="OK", logs=logs)
                        )
                    else:
                        await results_q.put(ChunkResult(lo, hi, status="EMPTY"))
                except RpcError as e:
                    await results_q.put(
                        ChunkResult(
                            lo, hi,
                            status="FAILED",
                            error=str(e),
                            error_body=e.body if isinstance(e.body, (dict, str)) else None,
                        )
                    )
                except Exception as e:  # noqa: BLE001
                    await results_q.put(
                        ChunkResult(lo, hi, status="FAILED", error=f"{type(e).__name__}: {e}")
                    )
                finally:
                    elapsed = time.time() - started
                    if elapsed > 5:
                        log.warning(
                            "slow chunk [%d, %d]: %.1fs (url=%s)",
                            lo, hi, elapsed, redact_url(self.http_url),
                        )

        tasks = [asyncio.create_task(worker(lo, hi)) for lo, hi in chunks]
        try:
            for _ in chunks:
                yield await results_q.get()
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
