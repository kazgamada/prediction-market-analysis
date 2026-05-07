"""Run a nautilus backtest over local Polymarket parquet data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from nautilus_trader.adapters.polymarket.common.constants import POLYMARKET_VENUE
from nautilus_trader.adapters.polymarket.loaders import PolymarketDataLoader
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import USDC_POS as USDC
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.objects import Money

from src.trading.data import load_trade_dicts
from src.trading.instrument import build_binary_option
from src.trading.risk import RiskLimits, RiskManager
from src.trading.strategies.threshold import ThresholdConfig, ThresholdStrategy


@dataclass
class BacktestParams:
    condition_id: str
    token_id: str
    question: str
    outcome: str = "YES"
    end_date_iso: str | None = None
    start: str | None = None
    end: str | None = None
    starting_cash: float = 1000.0
    buy_below: float = 0.10
    sell_above: float = 0.50
    max_order_pct: float = 0.05
    max_position_pct: float = 0.20
    max_daily_loss_pct: float = 0.10
    tick_limit: int | None = None


@dataclass
class BacktestResult:
    params: dict
    n_trade_ticks: int
    final_equity: float
    pnl: float
    return_pct: float
    n_orders: int
    n_fills: int
    equity_curve: list[dict]
    stats: dict
    error: str | None = None


def _equity_curve_from_engine(engine: BacktestEngine, instrument) -> list[dict]:
    account = engine.trader.generate_account_report(instrument.venue)
    if account is None or account.empty:
        return []
    out = []
    for ts, row in account.iterrows():
        out.append({"timestamp": ts.isoformat(), "equity": float(row.get("total", 0))})
    return out


def run_backtest(params: BacktestParams, data_dir: Path | str) -> BacktestResult:
    instrument = build_binary_option(
        condition_id=params.condition_id,
        token_id=params.token_id,
        question=params.question,
        outcome=params.outcome,
        end_date_iso=params.end_date_iso,
    )

    raw = load_trade_dicts(
        token_id=params.token_id,
        data_dir=data_dir,
        start=params.start,
        end=params.end,
        limit=params.tick_limit,
    )

    if not raw:
        return BacktestResult(
            params=asdict(params),
            n_trade_ticks=0,
            final_equity=params.starting_cash,
            pnl=0.0,
            return_pct=0.0,
            n_orders=0,
            n_fills=0,
            equity_curve=[],
            stats={},
            error="No trades found for token_id in date range",
        )

    loader = PolymarketDataLoader(instrument=instrument, token_id=params.token_id)
    ticks = loader.parse_trades(raw)

    engine = BacktestEngine(
        config=BacktestEngineConfig(
            trader_id="BACKTESTER-001",
            logging=LoggingConfig(log_level="WARN"),
        ),
    )

    engine.add_venue(
        venue=POLYMARKET_VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=USDC,
        starting_balances=[Money(params.starting_cash, USDC)],
    )
    engine.add_instrument(instrument)
    engine.add_data(ticks)

    risk = RiskManager(
        limits=RiskLimits(
            max_order_pct=params.max_order_pct,
            max_position_pct=params.max_position_pct,
            max_daily_loss_pct=params.max_daily_loss_pct,
        ),
        starting_cash=params.starting_cash,
    )

    strategy = ThresholdStrategy(
        config=ThresholdConfig(
            instrument_id=instrument.id,
            buy_below=params.buy_below,
            sell_above=params.sell_above,
        ),
        risk=risk,
    )
    engine.add_strategy(strategy)

    engine.run()

    account_balance = engine.portfolio.account(POLYMARKET_VENUE).balance_total(USDC)
    final_equity = float(account_balance) if account_balance is not None else params.starting_cash
    orders_report = engine.trader.generate_orders_report()
    fills_report = engine.trader.generate_order_fills_report()
    stats: dict[str, Any] = {}
    try:
        stats = {
            k: float(v) if isinstance(v, (int, float, Decimal)) else str(v)
            for k, v in engine.portfolio.analyzer.get_performance_stats_pnls(USDC).items()
        }
    except Exception:
        stats = {}

    equity_curve = _equity_curve_from_engine(engine, instrument)
    pnl = final_equity - params.starting_cash

    result = BacktestResult(
        params=asdict(params),
        n_trade_ticks=len(ticks),
        final_equity=final_equity,
        pnl=pnl,
        return_pct=(pnl / params.starting_cash) * 100.0 if params.starting_cash else 0.0,
        n_orders=len(orders_report) if orders_report is not None else 0,
        n_fills=len(fills_report) if fills_report is not None else 0,
        equity_curve=equity_curve,
        stats=stats,
    )

    engine.dispose()
    return result
