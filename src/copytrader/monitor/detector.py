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


async def run(on_signal: SignalHandler | None = None) -> None:
    """Run the live monitor: subscribe, persist trades, emit signals on matches."""
    detector = WatchlistDetector()

    async def handle(trade: DecodedTrade) -> None:
        await persist_trade(trade)
        wallet = detector.matches(trade)
        if wallet:
            await emit_signal(trade, wallet, on_signal)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(detector.refresh_loop())
        tg.create_task(subscribe_logs(handle))
