"""Signal -> order placement, paper or live."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal


from copytrader.clob.client import ClobClient
from copytrader.db import session_scope
from copytrader.executor.sizing import CopyConfig, desired_usd
from copytrader.executor.state import (
    get_position,
    total_exposure_usd,
    upsert_position,
)
from copytrader.models import Order, Signal
from copytrader.risk.killswitch import record as risk_record
from copytrader.risk.killswitch import trip
from copytrader.risk.limits import RiskLimits, RiskState, decide_size

log = logging.getLogger(__name__)


class Trader:
    def __init__(
        self,
        *,
        mode: str,
        copy_cfg: CopyConfig,
        limits: RiskLimits,
    ):
        if mode not in ("paper", "live"):
            raise ValueError("mode must be 'paper' or 'live'")
        self.mode = mode
        self.copy_cfg = copy_cfg
        self.limits = limits
        self.state = RiskState()
        self._clob = ClobClient(signed=(mode == "live"))

    def _estimate_fill_price(self, token_id: str, side: str, source_price: float) -> float:
        """Look at orderbook midpoint or fall back to source price."""
        try:
            mid = self._clob.midpoint(token_id)
            if mid is not None:
                return float(mid)
        except Exception:
            pass
        return float(source_price)

    def handle_signal(self, signal_id: int) -> Order | None:
        if self.state.halted:
            log.warning("signal %s skipped: halted", signal_id)
            return None

        with session_scope() as session:
            sig = session.get(Signal, signal_id)
            if sig is None:
                return None
            if sig.status != "new":
                return None
            session.expunge(sig)

        # Sizing
        target_usd = desired_usd(float(sig.source_size), float(sig.source_price), self.copy_cfg)
        side = sig.side  # source wallet's side; we mirror it
        fill_estimate = self._estimate_fill_price(sig.token_id, side, float(sig.source_price))

        existing = get_position(sig.token_id, self.mode)
        existing_usd = (
            float((existing.size or Decimal(0)) * (existing.avg_entry_price or Decimal(0)))
            if existing
            else 0.0
        )
        decision = decide_size(
            side=side,
            fill_price_estimate=fill_estimate,
            desired_usd=target_usd,
            current_position_usd=existing_usd,
            total_exposure_usd=total_exposure_usd(self.mode),
            limits=self.limits,
            state=self.state,
        )
        if not decision.allowed:
            log.info("signal %s blocked: %s", signal_id, decision.reason)
            risk_record("blocked", f"signal={signal_id} reason={decision.reason}")
            self._mark_signal(signal_id, "blocked", decision.reason)
            return None

        size_tokens = decision.size_tokens
        limit_price = self._limit_for(side, fill_estimate)

        order = self._place(
            signal_id=signal_id,
            token_id=sig.token_id,
            side=side,
            size_tokens=size_tokens,
            limit_price=limit_price,
            fill_estimate=fill_estimate,
        )
        return order

    def _limit_for(self, side: str, fill_estimate: float) -> float:
        # Cross the book: BUY at +1%, SELL at -1% of mid
        if side == "BUY":
            return min(0.99, fill_estimate * 1.01)
        return max(0.01, fill_estimate * 0.99)

    def _place(
        self,
        *,
        signal_id: int,
        token_id: str,
        side: str,
        size_tokens: float,
        limit_price: float,
        fill_estimate: float,
    ) -> Order:
        now = datetime.now(timezone.utc)
        order_kwargs = dict(
            signal_id=signal_id,
            mode=self.mode,
            token_id=token_id,
            side=side,
            size=Decimal(str(size_tokens)),
            limit_price=Decimal(str(limit_price)),
            placed_at=now,
        )

        if self.mode == "paper":
            # Pretend the order fills immediately at the estimate
            fill_price = Decimal(str(fill_estimate))
            order = Order(
                **order_kwargs,
                status="filled",
                filled_size=Decimal(str(size_tokens)),
                avg_fill_price=fill_price,
                closed_at=now,
            )
            with session_scope() as session:
                session.add(order)
                session.flush()
                oid = order.id
                session.expunge(order)
            upsert_position(
                token_id=token_id,
                mode="paper",
                side=side,
                size_tokens=Decimal(str(size_tokens)),
                fill_price=fill_price,
            )
            self._mark_signal(signal_id, "executed", f"paper-fill@{fill_price}")
            log.info(
                "[paper] order=%s %s %s @ %s size=%s",
                oid,
                side,
                token_id,
                fill_price,
                size_tokens,
            )
            return order

        # live
        self.state.open_orders += 1
        try:
            result = self._clob.place_market(
                token_id=token_id, side=side, size_tokens=size_tokens, limit_price=limit_price
            )
        finally:
            self.state.open_orders = max(0, self.state.open_orders - 1)

        order = Order(
            **order_kwargs,
            clob_order_id=result.order_id,
            status=("placed" if result.success else "rejected"),
            error=result.error,
        )
        with session_scope() as session:
            session.add(order)
            session.flush()
            oid = order.id
            session.expunge(order)

        if not result.success:
            self._mark_signal(signal_id, "failed", result.error or "unknown")
            risk_record("order_rejected", f"signal={signal_id} err={result.error}")
            return order

        # Optimistic position update assuming fill at limit (reconciler corrects later)
        upsert_position(
            token_id=token_id,
            mode="live",
            side=side,
            size_tokens=Decimal(str(size_tokens)),
            fill_price=Decimal(str(limit_price)),
        )
        self._mark_signal(signal_id, "executed", f"live-order={result.order_id}")
        log.info(
            "[live] order=%s %s %s @ %s size=%s clob=%s",
            oid,
            side,
            token_id,
            limit_price,
            size_tokens,
            result.order_id,
        )
        return order

    def _mark_signal(self, signal_id: int, status: str, note: str | None) -> None:
        with session_scope() as session:
            sig = session.get(Signal, signal_id)
            if sig is None:
                return
            sig.status = status
            if note:
                sig.notes = note

    def record_pnl(self, realized_delta: float) -> None:
        self.state.realized_pnl_usd += realized_delta
        if realized_delta < 0:
            self.state.daily_loss_usd += abs(realized_delta)
            if self.state.daily_loss_usd >= self.limits.max_daily_loss_usd:
                trip(self.state, "daily_loss", f"loss={self.state.daily_loss_usd:.2f}")
