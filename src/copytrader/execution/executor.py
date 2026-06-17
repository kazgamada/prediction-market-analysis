"""Executor worker: PENDING signals → risk check → CLOB → executions row.

Long-running coroutine. Polls signals table every 2s for PENDING rows whose
execute_after has passed. For each:

1. Re-check risk via risk.evaluate_risk()
2. If halted → mark signal SKIPPED reason=halted_*
3. Re-check watchlist (might have been deactivated in delay window)
4. Re-check settings.execution_enabled
5. POST to CLOB (or dry-run if creds missing / paper mode)
6. INSERT executions row, link signal.execution_id
7. Update signal.status

`settings.execution_enabled=false` → Phase A paper mode: signal is marked
SKIPPED with skip_reason="paper", no CLOB call made.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, update

from copytrader.db import settings_table
from copytrader.db.engine import get_session
from copytrader.db.models import Execution, Signal, Watchlist
from copytrader.execution.clob_client import get_clob
from copytrader.execution.order_state import (
    EXEC_PLACED,
    EXEC_REJECTED,
    SIGNAL_EXECUTED,
    SIGNAL_EXECUTING,
    SIGNAL_PENDING,
    SIGNAL_REJECTED,
    SIGNAL_SKIPPED,
)
from copytrader.risk.evaluator import evaluate_risk

log = logging.getLogger("execution.executor")


def _settings_size(source_size_usdc: Decimal) -> Decimal:
    """Resolve the copy size based on settings."""
    mode = settings_table.get("copy_size_mode") or "fixed"
    if mode == "proportional":
        # Future: scale to source trader's bankroll. For now, cap at fixed.
        ratio = Decimal(str(settings_table.get("copy_proportional_ratio") or 0.01))
        return source_size_usdc * ratio
    return Decimal(str(settings_table.get("copy_size_usdc") or 10))


def _claim_pending() -> list[Signal]:
    """Atomically pull PENDING signals whose execute_after has passed.

    Marks them EXECUTING so a second worker (or this same worker re-entering)
    doesn't double-execute.
    """
    now = datetime.now(UTC)
    with get_session() as s:
        ids = s.execute(
            select(Signal.id)
            .where(Signal.status == SIGNAL_PENDING)
            .where(Signal.execute_after <= now)
            .order_by(Signal.id)
            .limit(50)
        ).scalars().all()
        if not ids:
            return []
        # Optimistic lock: only EXECUTING from PENDING
        s.execute(
            update(Signal)
            .where(Signal.id.in_(ids))
            .where(Signal.status == SIGNAL_PENDING)
            .values(status=SIGNAL_EXECUTING)
        )
        rows = s.execute(
            select(Signal).where(Signal.id.in_(ids))
        ).scalars().all()
        return [r for r in rows if r.status == SIGNAL_EXECUTING]


def _is_active_watchlist(addr: bytes) -> bool:
    with get_session() as s:
        w = s.execute(
            select(Watchlist).where(Watchlist.address == addr)
        ).scalar_one_or_none()
        return bool(w and w.active)


def _execute_signal(sig: Signal, halt_reasons: list[str]) -> None:
    """Execute one signal: risk check (already done in caller) → CLOB."""
    # Snapshot reason if halted
    if halt_reasons:
        _mark_signal(sig.id, SIGNAL_SKIPPED,
                     skip_reason=f"halted:{','.join(halt_reasons)}")
        return

    # Re-check watchlist (might have been deactivated)
    if not _is_active_watchlist(sig.address):
        _mark_signal(sig.id, SIGNAL_SKIPPED, skip_reason="watchlist_inactive")
        return

    # Paper mode?
    if not bool(settings_table.get("execution_enabled") or False):
        _mark_signal(sig.id, SIGNAL_SKIPPED, skip_reason="paper")
        log.info("signal %s: paper mode, skipped", sig.id)
        return

    # Size resolution
    size_usdc = _settings_size(Decimal(str(sig.size_usdc)))
    # Convert USDC to shares using source price (limit order)
    src_price = Decimal(str(sig.price))
    if src_price <= 0 or src_price >= 1:
        _mark_signal(sig.id, SIGNAL_REJECTED, skip_reason="bad_price")
        return
    size_shares = (size_usdc / src_price).quantize(Decimal("0.000001"))

    # Slippage budget
    slip_bps = int(settings_table.get("limit_slippage_bps") or 100)
    # For BUY pay up to mid + slippage; for SELL accept down to mid - slippage
    if sig.side == 0:
        limit_price = src_price * (Decimal(1) + Decimal(slip_bps) / Decimal(10000))
    else:
        limit_price = src_price * (Decimal(1) - Decimal(slip_bps) / Decimal(10000))
    limit_price = limit_price.quantize(Decimal("0.0001"))
    # Clamp to (0.01, 0.99) for Polymarket
    if limit_price <= Decimal("0.01"):
        limit_price = Decimal("0.01")
    if limit_price >= Decimal("0.99"):
        limit_price = Decimal("0.99")

    tif = str(settings_table.get("order_tif") or "GTC")
    idem = f"sig-{sig.id}"

    placed_at = datetime.now(UTC)
    signal_to_place_ms = int(
        (placed_at - (sig.detected_at or placed_at)).total_seconds() * 1000
    )

    clob = get_clob()
    result = clob.post_order(
        token_id=int(sig.token_id),
        side=int(sig.side),
        size_shares=size_shares,
        price=limit_price,
        tif=tif,
    )

    with get_session() as s:
        ex = Execution(
            signal_id=sig.id,
            clob_order_id=result.order_id,
            token_id=sig.token_id,
            side=sig.side,
            size_usdc=size_usdc,
            limit_price=limit_price,
            placed_at=placed_at,
            status=EXEC_PLACED if result.success else EXEC_REJECTED,
            signal_to_place_ms=signal_to_place_ms,
            error_text=result.error,
            idempotency_key=idem,
        )
        s.add(ex)
        s.flush()
        ex_id = ex.id
        s.execute(
            update(Signal)
            .where(Signal.id == sig.id)
            .values(
                status=SIGNAL_EXECUTED if result.success else SIGNAL_REJECTED,
                execution_id=ex_id,
                skip_reason=None if result.success else f"clob:{result.error}",
            )
        )
    log.info(
        "signal %s → execution %s: %s (dry_run=%s, order_id=%s)",
        sig.id, ex_id,
        "PLACED" if result.success else "REJECTED",
        result.dry_run, result.order_id,
    )


def _mark_signal(sid: int, status: str, *, skip_reason: str | None = None) -> None:
    with get_session() as s:
        s.execute(
            update(Signal)
            .where(Signal.id == sid)
            .values(status=status, skip_reason=skip_reason)
        )


async def run_executor(*, tick_seconds: int = 2) -> None:
    """Long-running coroutine: poll signals every tick_seconds."""
    log.info("executor: starting, tick=%ds", tick_seconds)
    while True:
        try:
            risk = evaluate_risk(persist=True)
            claimed = _claim_pending()
            if claimed:
                log.info(
                    "executor: %d signals claimed (allow=%s, halted=%s)",
                    len(claimed), risk.allow_new_orders, risk.halted_reasons,
                )
            halt_reasons = list(risk.halted_reasons) if not risk.allow_new_orders else []
            for sig in claimed:
                try:
                    _execute_signal(sig, halt_reasons)
                except Exception as e:  # noqa: BLE001
                    log.exception("executor failed on signal %s: %s", sig.id, e)
                    _mark_signal(sig.id, SIGNAL_REJECTED,
                                 skip_reason=f"executor_error:{e}")
        except Exception as e:  # noqa: BLE001
            log.exception("executor tick failed: %s", e)
        await asyncio.sleep(tick_seconds)
