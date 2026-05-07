"""Smoke tests for the trading framework (no actual backtest run; needs data)."""

from __future__ import annotations

import pytest

from src.trading.backtest import BacktestParams
from src.trading.instrument import build_binary_option
from src.trading.risk import RiskLimits, RiskManager
from src.trading.strategies.calibration_fade import interpolate_actual


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


def test_interpolate_actual_clamps_endpoints_and_lerps_between():
    points = ((0.10, 0.05), (0.50, 0.55), (0.90, 0.92))
    # below first point → first y
    assert interpolate_actual(0.05, points) == pytest.approx(0.05)
    # above last point → last y
    assert interpolate_actual(0.99, points) == pytest.approx(0.92)
    # exactly on a knot
    assert interpolate_actual(0.50, points) == pytest.approx(0.55)
    # midpoint between first and second: (0.05 + 0.55) / 2
    assert interpolate_actual(0.30, points) == pytest.approx(0.30)


def test_interpolate_actual_empty_raises():
    with pytest.raises(ValueError):
        interpolate_actual(0.5, ())


def test_backtest_params_rejects_unknown_strategy():
    with pytest.raises(ValueError):
        BacktestParams(
            condition_id="c", token_id="t", question="q", strategy="bogus",
        )


def test_backtest_params_calibration_fade_requires_points():
    with pytest.raises(ValueError):
        BacktestParams(
            condition_id="c", token_id="t", question="q",
            strategy="calibration_fade",
        )
    # ok with points
    params = BacktestParams(
        condition_id="c", token_id="t", question="q",
        strategy="calibration_fade",
        calibration_points=[[0.1, 0.05], [0.9, 0.92]],
    )
    assert params.strategy == "calibration_fade"
