"""Smoke tests for the trading framework (no actual backtest run; needs data)."""

from __future__ import annotations

import pytest

from src.trading.instrument import build_binary_option
from src.trading.risk import RiskLimits, RiskManager


def test_risk_limits_validates_range():
    with pytest.raises(ValueError):
        RiskLimits(max_order_pct=0, max_position_pct=0.1, max_daily_loss_pct=0.1)
    with pytest.raises(ValueError):
        RiskLimits(max_order_pct=0.1, max_position_pct=0.05, max_daily_loss_pct=0.1)
    RiskLimits(max_order_pct=0.05, max_position_pct=0.2, max_daily_loss_pct=0.1)


def test_risk_manager_halts_after_daily_loss():
    rm = RiskManager(
        limits=RiskLimits(max_order_pct=0.05, max_position_pct=0.2, max_daily_loss_pct=0.1),
        starting_cash=1000.0,
    )
    assert not rm.halted
    rm.record_pnl(-50)
    assert not rm.halted
    rm.record_pnl(-60)
    assert rm.halted
    assert rm.order_size(equity=900, price=0.5) == 0.0


def test_risk_manager_order_size_respects_cap():
    rm = RiskManager(
        limits=RiskLimits(max_order_pct=0.05, max_position_pct=0.2, max_daily_loss_pct=0.1),
        starting_cash=1000.0,
    )
    # 5% of 1000 = 50 USDC budget; at price 0.25 → 200 tokens
    assert rm.order_size(equity=1000, price=0.25) == pytest.approx(200.0)


def test_build_binary_option_constructs_without_api():
    inst = build_binary_option(
        condition_id="0x" + "a" * 64,
        token_id="12345",
        question="Test market",
    )
    assert inst.id is not None
    assert "12345" in str(inst.id)
