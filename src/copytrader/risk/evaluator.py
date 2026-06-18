"""Risk evaluation: 7 halt conditions + 4 soft limits + kill switch.

Designed to be called once per executor tick. Returns a `RiskCheck` with
`allow_new_orders` boolean and a list of which conditions tripped. Also
persists a row in `risk_evaluations` for audit.

Thresholds are read from the `settings` table (via `settings_table.get()`)
on each call so they can be tuned at runtime without restart.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from copytrader.db import settings_table
from copytrader.db.engine import get_session
from copytrader.db.models import (
    Cursor,
    Execution,
    Position,
    RiskEvaluation,
    TradePnl,
)
from copytrader.indexer.backfill import CURSOR_NAME

log = logging.getLogger("risk.evaluator")


@dataclass(frozen=True)
class RiskCheck:
    allow_new_orders: bool
    halted_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


def _get(key: str, default):
    """settings_table.get returns the parsed JSON value or default."""
    try:
        v = settings_table.get(key)
    except Exception:  # noqa: BLE001
        return default
    return v if v is not None else default


def _today_pnl(session) -> Decimal:
    """Realized PnL since 00:00 UTC today."""
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    total = session.execute(
        select(func.coalesce(func.sum(TradePnl.realized_usdc), 0))
        .where(TradePnl.ts >= midnight)
    ).scalar_one()
    return Decimal(str(total))


def _weekly_pnl(session) -> Decimal:
    since = datetime.now(UTC) - timedelta(days=7)
    total = session.execute(
        select(func.coalesce(func.sum(TradePnl.realized_usdc), 0))
        .where(TradePnl.ts >= since)
    ).scalar_one()
    return Decimal(str(total))


def _consecutive_losses(session, limit: int = 20) -> int:
    """Count trailing losing trades (most recent first)."""
    rows = session.execute(
        select(TradePnl.realized_usdc)
        .order_by(TradePnl.ts.desc())
        .limit(limit)
    ).scalars().all()
    count = 0
    for pnl in rows:
        if Decimal(str(pnl)) < 0:
            count += 1
        else:
            break
    return count


def _total_exposure_usdc(session) -> Decimal:
    total = session.execute(
        select(func.coalesce(func.sum(Position.open_size_usdc), 0))
    ).scalar_one()
    return Decimal(str(total))


def _max_single_market_usdc(session) -> tuple[Decimal, str | None]:
    row = session.execute(
        select(Position.open_size_usdc, Position.market_label)
        .order_by(Position.open_size_usdc.desc())
        .limit(1)
    ).first()
    if not row:
        return Decimal(0), None
    return Decimal(str(row[0])), row[1]


def _daily_trades(session) -> int:
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(session.execute(
        select(func.count()).select_from(Execution).where(Execution.placed_at >= midnight)
    ).scalar_one())


def _indexer_lag_seconds(session) -> int | None:
    cur = session.get(Cursor, CURSOR_NAME)
    if not cur or not cur.updated_at:
        return None
    return int((datetime.now(UTC) - cur.updated_at).total_seconds())


def _capital_usdc() -> Decimal:
    """Total trading capital. For now reads from settings.capital_usdc;
    in production should query the on-chain USDC balance + open positions.
    """
    v = _get("capital_usdc", 1000.0)
    try:
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return Decimal("1000")


def evaluate_risk(*, persist: bool = True) -> RiskCheck:
    """Evaluate all risk conditions and return a RiskCheck.

    persist=True (default): insert a row in risk_evaluations.
    """
    halted: list[str] = []
    warnings: list[str] = []
    metrics: dict = {}

    # Kill switch overrides everything
    if bool(_get("kill_switch_on", False)):
        halted.append("kill_switch_on")

    with get_session() as s:
        # Halt conditions
        capital = _capital_usdc()
        metrics["capital_usdc"] = float(capital)

        today_pnl = _today_pnl(s)
        metrics["today_pnl_usdc"] = float(today_pnl)
        today_pct = float(today_pnl / capital * 100) if capital > 0 else 0.0
        metrics["today_pnl_pct"] = round(today_pct, 2)
        if today_pct < float(_get("halt_daily_pnl_pct", -5.0)):
            halted.append("halt_daily_pnl_pct")

        weekly_pnl = _weekly_pnl(s)
        metrics["weekly_pnl_usdc"] = float(weekly_pnl)
        weekly_pct = float(weekly_pnl / capital * 100) if capital > 0 else 0.0
        metrics["weekly_pnl_pct"] = round(weekly_pct, 2)
        if weekly_pct < float(_get("halt_weekly_pnl_pct", -8.0)):
            halted.append("halt_weekly_pnl_pct")

        cl = _consecutive_losses(s)
        metrics["consecutive_losses"] = cl
        if cl >= int(_get("halt_consecutive_losses", 5)):
            halted.append("halt_consecutive_losses")

        max_market_usdc, max_market_label = _max_single_market_usdc(s)
        max_pct = float(max_market_usdc / capital * 100) if capital > 0 else 0.0
        metrics["max_single_market_pct"] = round(max_pct, 2)
        metrics["max_single_market_label"] = max_market_label
        if max_pct > float(_get("halt_single_market_pct", 25.0)):
            halted.append("halt_single_market_pct")

        lag = _indexer_lag_seconds(s)
        metrics["indexer_lag_seconds"] = lag
        if lag is not None and lag > int(_get("halt_indexer_lag_seconds", 120)):
            halted.append("halt_indexer_lag_seconds")

        # USDC / MATIC balance, refreshed by the balance_refresh job
        # (execution.balance_client). The cache is None until a reading exists:
        # None = unknown → cannot halt (no data); a real reading (including 0,
        # i.e. an empty wallet) → enforce the floor. The previous `> 0` guard
        # treated an empty wallet as "fine" and never halted — not fail-safe.
        usdc_raw = _get("usdc_balance_cache", None)
        matic_raw = _get("matic_balance_cache", None)
        metrics["usdc_balance"] = float(usdc_raw) if usdc_raw is not None else None
        metrics["matic_balance"] = float(matic_raw) if matic_raw is not None else None
        if usdc_raw is not None and float(usdc_raw) < float(_get("halt_usdc_min", 500)):
            halted.append("halt_usdc_min")
        if matic_raw is not None and float(matic_raw) < float(_get("halt_matic_min", 1.0)):
            halted.append("halt_matic_min")

        # Soft limits (don't block, just warn for now; executor enforces skip)
        total_exposure = _total_exposure_usdc(s)
        exp_pct = float(total_exposure / capital * 100) if capital > 0 else 0.0
        metrics["total_exposure_pct"] = round(exp_pct, 2)
        if exp_pct > float(_get("limit_total_exposure_pct", 70.0)):
            warnings.append("limit_total_exposure_pct")

        if max_pct > float(_get("limit_single_token_pct", 25.0)):
            warnings.append("limit_single_token_pct")

        daily_trades = _daily_trades(s)
        metrics["daily_trades"] = daily_trades
        if daily_trades > int(_get("limit_daily_trades", 100)):
            warnings.append("limit_daily_trades")

        if cl >= int(_get("risk_loss_size_halve_at", 3)):
            warnings.append("risk_loss_size_halve_at")

    allow = len(halted) == 0
    check = RiskCheck(
        allow_new_orders=allow,
        halted_reasons=halted,
        warnings=warnings,
        metrics=metrics,
    )

    if persist:
        try:
            with get_session() as s:
                s.add(RiskEvaluation(
                    allow_new=allow,
                    halted_reasons=halted,
                    warnings=warnings,
                    metrics_snapshot=metrics,
                ))
        except Exception as e:  # noqa: BLE001
            log.warning("failed to persist risk_evaluation: %s", e)

    if not allow:
        log.warning("RISK HALT: %s | metrics=%s", halted, metrics)

    return check
