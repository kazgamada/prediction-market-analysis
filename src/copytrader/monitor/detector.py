"""Detect trades by watchlisted wallets in the live stream and emit Signals."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import select

from copytrader.db import session_scope
from copytrader.indexer.decoder import DecodedTrade
from copytrader.indexer.stream import persist_trade, subscribe_logs
from copytrader.models import Signal, Trade
from copytrader.monitor.watchlist import get_watchlist

log = logging.getLogger(__name__)

SignalHandler = Callable[[Signal], Awaitable[None]]


class WatchlistDetector:
    """In-memory copy of the watchlist with periodic refresh."""

    def __init__(self, refresh_seconds: int = 60):
        self._watchlist: set[str] = set()
        self._refresh_seconds = refresh_seconds

    async def refresh_loop(self) -> None:
        while True:
            try:
                self._watchlist = set(get_watchlist())
                log.info("watchlist refreshed: %s wallets", len(self._watchlist))
            except Exception as e:
                log.warning("watchlist refresh failed: %s", e)
            await asyncio.sleep(self._refresh_seconds)

    def matches(self, trade: DecodedTrade) -> str | None:
        if trade.maker.lower() in self._watchlist:
            return trade.maker.lower()
        if trade.taker.lower() in self._watchlist:
            return trade.taker.lower()
        return None

    @staticmethod
    def wallet_side(trade: DecodedTrade, wallet: str) -> str:
        is_maker = trade.maker.lower() == wallet
        maker_provides_usdc = trade.maker_asset_id == "0"
        if maker_provides_usdc:
            return "BUY" if is_maker else "SELL"
        return "SELL" if is_maker else "BUY"


async def emit_signal(trade: DecodedTrade, wallet: str, on_signal: SignalHandler | None) -> None:
    side = WatchlistDetector.wallet_side(trade, wallet)
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        # find the trade row we just inserted
        trade_row = session.execute(
            select(Trade.id).where(
                Trade.tx_hash == trade.tx_hash, Trade.log_index == trade.log_index
            )
        ).scalar_one_or_none()

        sig = Signal(
            source_wallet=wallet,
            source_trade_id=trade_row,
            token_id=trade.token_id,
            side=side,
            source_price=trade.price,
            source_size=trade.size,
            detected_at=now,
            status="new",
        )
        session.add(sig)
        session.flush()
        sig_id = sig.id

    log.info(
        "signal emitted: id=%s wallet=%s side=%s token=%s size=%s price=%s",
        sig_id,
        wallet,
        side,
        trade.token_id,
        trade.size,
        trade.price,
    )

    if on_signal is not None:
        # Re-fetch a detached object the handler can use
        with session_scope() as session:
            sig = session.get(Signal, sig_id)
            if sig:
                session.expunge(sig)
        await on_signal(sig)


async def _supervise(name: str, factory: Callable[[], Awaitable[None]]) -> None:
    """1 つのバックグラウンドタスクを監督し、例外で死んだら再起動する。

    `asyncio.TaskGroup` は 1 タスクの未捕捉例外で全体を殺してしまうため、
    monitor 全体が落ちて Fly が再起動を諦める事象 (max restart count) に
    繋がっていた。各タスクをこの supervisor で包むことで、live WS と
    catchup が独立して回り続ける。
    """
    backoff = 1.0
    while True:
        try:
            await factory()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("supervised task %s crashed; restarting in %.1fs", name, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
            continue
        backoff = 1.0


async def run(
    on_signal: SignalHandler | None = None,
    periodic_tasks: list[tuple[str, float, Callable[[], Awaitable[None]]]] | None = None,
) -> None:
    """Run the live monitor: subscribe, persist trades, emit signals on matches.

    `periodic_tasks` is a list of (name, interval_seconds, async_callable) tuples
    co-scheduled alongside the WS subscriber. Each task is supervised: if it
    raises, only that task restarts (with exponential backoff). The other tasks
    keep running. This is the key invariant for keeping monitor alive on Fly.
    """
    from copytrader.runtime.scheduler import run_every

    detector = WatchlistDetector()

    async def handle(trade: DecodedTrade) -> None:
        try:
            await persist_trade(trade)
            wallet = detector.matches(trade)
            if wallet:
                await emit_signal(trade, wallet, on_signal)
        except Exception:
            log.exception("handle(trade) failed for tx=%s log=%s", trade.tx_hash, trade.log_index)

    tasks: list[asyncio.Task] = [
        asyncio.create_task(_supervise("watchlist_refresh", detector.refresh_loop)),
        asyncio.create_task(_supervise("subscribe_logs", lambda: subscribe_logs(handle))),
    ]
    for name, interval, fn in periodic_tasks or []:
        tasks.append(asyncio.create_task(_supervise(name, lambda fn=fn: run_every(name, interval, fn))))

    log.info("monitor started: %s tasks", len(tasks))
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for t in tasks:
            t.cancel()
        raise
