"""Job handlers.

Each handler takes a JobHandle and returns nothing. Logs / progress / result
all go through `handle.log()`, `handle.progress()`, `handle.result()`.
"""
from __future__ import annotations

import logging
from typing import Any

from copytrader.analysis.rank import rank_wallets
from copytrader.analysis.replay import replay_copytrade
from copytrader.jobs.queue import JobHandle

log = logging.getLogger(__name__)


def _to_jsonable(obj: Any) -> Any:
    from decimal import Decimal
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, bytes):
        return "0x" + obj.hex()
    return obj


def handle_backfill(handle: JobHandle) -> None:
    """Run backfill_range over the configured window synchronously.

    This handler is only invoked when a user explicitly requests a backfill
    (e.g. clicking "Re-run backfill" in the UI). Normal day-to-day catchup
    happens inside the indexer process; this is a manual reset.
    """
    import asyncio as _aio

    from copytrader.chain.client import JsonRpcClient
    from copytrader.config import settings
    from copytrader.indexer.backfill import backfill_range
    from copytrader.indexer.cursor import ensure_floor
    from copytrader.indexer.supervisor import BLOCKS_PER_DAY, CURSOR_NAME

    window = int(handle.params.get("window", settings.indexer_window_days))
    handle.log(f"backfill: window={window}d")

    async def _run() -> dict:
        client = JsonRpcClient(
            settings.polygon_rpc_http,
            max_parallel=settings.indexer_max_parallel,
            max_retries=settings.indexer_max_retries,
        )
        try:
            head = await client.get_block_number()
            floor = head - window * BLOCKS_PER_DAY
            cursor = ensure_floor(CURSOR_NAME, floor)
            from_block = cursor + 1
            summary = await backfill_range(
                client,
                from_block=from_block,
                to_block=head,
                chunk_size=settings.indexer_chunk_size,
                progress_cb=handle.progress,
            )
            return summary
        finally:
            await client.aclose()

    summary = _aio.run(_run())
    handle.log(f"backfill done: {summary}")
    handle.result(_to_jsonable(summary))


def handle_rank(handle: JobHandle) -> None:
    window = int(handle.params.get("window", 30))
    min_trades = int(handle.params.get("min_trades", 30))
    min_volume = float(handle.params.get("min_volume_usdc", 5000))
    top_n = int(handle.params.get("top_n", 50))
    handle.log(f"rank: window={window}d, min_trades={min_trades}, min_vol={min_volume}, top_n={top_n}")
    rows = rank_wallets(
        window_days=window,
        min_trades=min_trades,
        min_volume_usdc=min_volume,
        top_n=top_n,
    )
    out = [{
        "address": r.address,
        "trades": r.trades,
        "volume_usdc": str(r.volume_usdc),
        "realized_pnl_usdc": str(r.realized_pnl_usdc),
        "win_rate": str(r.win_rate) if r.win_rate is not None else None,
    } for r in rows]
    handle.log(f"rank: {len(out)} qualified wallets")
    handle.result({"wallets": out})


def handle_replay(handle: JobHandle) -> None:
    window = int(handle.params.get("window", 30))
    delays = handle.params.get("delays", [30, 60, 120])
    copy_usd = float(handle.params.get("copy_usd_per_trade", 50))
    top_wallets = handle.params.get("top_wallets", [])
    handle.log(f"replay: window={window}d delays={delays} copy_usd={copy_usd} wallets={len(top_wallets)}")
    results = []
    for d in delays:
        r = replay_copytrade(
            window_days=window,
            top_wallets=top_wallets,
            delay_seconds=int(d),
            copy_usd_per_trade=copy_usd,
        )
        results.append({
            "delay_seconds": r.delay_seconds,
            "copy_usd_per_trade": str(r.copy_usd_per_trade),
            "signals_total": r.signals_total,
            "signals_executed": r.signals_executed,
            "signals_unfilled": r.signals_unfilled,
            "realized_pnl_usdc": str(r.realized_pnl_usdc),
            "invested_usdc": str(r.invested_usdc),
            "roi_pct": str(r.roi_pct) if r.roi_pct is not None else None,
        })
        handle.log(
            f"replay delay={d}s -> executed={r.signals_executed}/{r.signals_total} "
            f"pnl={r.realized_pnl_usdc} roi={r.roi_pct}%"
        )
    handle.result({"per_delay": results})


def handle_phase0(handle: JobHandle) -> None:
    """End-to-end: backfill -> rank -> replay.

    Runs the sub-steps directly (not via the queue) so a single-worker
    deployment can complete phase0 without deadlocking on its own children.
    """
    window = int(handle.params.get("window", 30))
    top_n = int(handle.params.get("watchlist_top", 10))
    delays = handle.params.get("delays", [30, 60, 120])
    copy_usd = float(handle.params.get("copy_usd_per_trade", 50))

    # Step 1: backfill (best-effort; if it raises we still continue with whatever
    # data is in the DB, since the indexer is also catching up in parallel).
    handle.log("phase0: step 1/3 backfill")
    backfill_sub = _SubHandle(handle, "backfill", {"window": window})
    try:
        handle_backfill(backfill_sub)
    except Exception as e:  # noqa: BLE001
        handle.log(f"backfill step failed (continuing): {e}", level=30)

    # Step 2: rank
    handle.log("phase0: step 2/3 rank")
    rank_sub = _SubHandle(handle, "rank", {"window": window, "top_n": top_n})
    handle_rank(rank_sub)
    top_wallets = [w["address"] for w in (rank_sub.captured_result or {}).get("wallets", [])]
    handle.log(f"phase0: rank produced {len(top_wallets)} wallets")

    # Step 3: replay
    handle.log("phase0: step 3/3 replay")
    replay_sub = _SubHandle(handle, "replay", {
        "window": window,
        "delays": delays,
        "copy_usd_per_trade": copy_usd,
        "top_wallets": top_wallets,
    })
    handle_replay(replay_sub)

    handle.result({
        "top_wallets": top_wallets,
        "rank": rank_sub.captured_result,
        "replay": replay_sub.captured_result,
    })


class _SubHandle(JobHandle):
    """In-process sub-handle that records into the parent job's logs/progress
    without inserting a separate job row.
    """

    def __init__(self, parent: JobHandle, kind: str, params: dict[str, Any]):
        # Bypass parent __init__ which requires a Job instance.
        self.id = parent.id
        self.kind = kind
        self.params = params
        self._parent = parent
        self.captured_result: dict[str, Any] | None = None

    def log(self, msg: str, level: int = 20) -> None:
        self._parent.log(f"[{self.kind}] {msg}", level=level)

    def progress(self, p: dict[str, Any]) -> None:
        self._parent.progress({self.kind: p})

    def result(self, r: dict[str, Any]) -> None:
        self.captured_result = r


def handle_gamma_resolve_fetch(handle: JobHandle) -> None:
    """Pull resolved markets from Polymarket Gamma into market_resolutions."""
    from copytrader.gamma.resolver import run_gamma_resolve_fetch_job

    params = handle.params or {}
    handle.log(f"gamma fetch start params={params}")
    summary = run_gamma_resolve_fetch_job(params)
    handle.log(f"gamma fetch done: {summary}")
    handle.result(_to_jsonable(summary))


HANDLERS = {
    "backfill": handle_backfill,
    "rank": handle_rank,
    "replay": handle_replay,
    "phase0": handle_phase0,
    "gamma_resolve_fetch": handle_gamma_resolve_fetch,
}
