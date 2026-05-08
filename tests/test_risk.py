"""Tests for risk caps and sizing decisions."""

import pytest

from copytrader.risk.limits import RiskLimits, RiskState, decide_size


def make_limits(**overrides):
    base = dict(
        max_order_usd=10.0,
        max_position_usd_per_token=50.0,
        max_total_exposure_usd=200.0,
        max_daily_loss_usd=20.0,
    )
    base.update(overrides)
    return RiskLimits(**base)


def test_limits_validate_positive():
    with pytest.raises(ValueError):
        RiskLimits(
            max_order_usd=0,
            max_position_usd_per_token=10,
            max_total_exposure_usd=100,
            max_daily_loss_usd=5,
        )


def test_limits_order_lte_position():
    with pytest.raises(ValueError):
        RiskLimits(
            max_order_usd=20,
            max_position_usd_per_token=10,
            max_total_exposure_usd=100,
            max_daily_loss_usd=5,
        )


def test_decide_size_allows_within_caps():
    limits = make_limits()
    state = RiskState()
    d = decide_size(
        side="BUY",
        fill_price_estimate=0.5,
        desired_usd=8.0,
        current_position_usd=0.0,
        total_exposure_usd=0.0,
        limits=limits,
        state=state,
    )
    assert d.allowed
    assert d.size_tokens == pytest.approx(16.0)


def test_decide_size_caps_at_max_order_usd():
    limits = make_limits()
    state = RiskState()
    d = decide_size(
        side="BUY",
        fill_price_estimate=0.5,
        desired_usd=100.0,  # over cap
        current_position_usd=0.0,
        total_exposure_usd=0.0,
        limits=limits,
        state=state,
    )
    assert d.allowed
    assert d.size_tokens == pytest.approx(20.0)  # 10 / 0.5


def test_decide_size_blocks_when_position_full():
    limits = make_limits()
    state = RiskState()
    d = decide_size(
        side="BUY",
        fill_price_estimate=0.5,
        desired_usd=10.0,
        current_position_usd=50.0,  # at cap
        total_exposure_usd=50.0,
        limits=limits,
        state=state,
    )
    assert not d.allowed
    assert "headroom" in d.reason


def test_decide_size_blocks_when_halted():
    limits = make_limits()
    state = RiskState(halted=True, halt_reason="testing")
    d = decide_size(
        side="BUY",
        fill_price_estimate=0.5,
        desired_usd=10.0,
        current_position_usd=0.0,
        total_exposure_usd=0.0,
        limits=limits,
        state=state,
    )
    assert not d.allowed
    assert "halted" in d.reason


def test_decide_size_blocks_when_daily_loss_hit():
    limits = make_limits()
    state = RiskState(daily_loss_usd=20.0)
    d = decide_size(
        side="BUY",
        fill_price_estimate=0.5,
        desired_usd=10.0,
        current_position_usd=0.0,
        total_exposure_usd=0.0,
        limits=limits,
        state=state,
    )
    assert not d.allowed
    assert d.reason == "max_daily_loss_usd"


def test_decide_size_sell_ignores_position_cap():
    limits = make_limits()
    state = RiskState()
    d = decide_size(
        side="SELL",
        fill_price_estimate=0.5,
        desired_usd=10.0,
        current_position_usd=50.0,  # at cap, but selling is fine
        total_exposure_usd=50.0,
        limits=limits,
        state=state,
    )
    assert d.allowed


def test_decide_size_invalid_price():
    limits = make_limits()
    state = RiskState()
    for bad in (0.0, -0.5, 1.0, 1.5):
        d = decide_size(
            side="BUY",
            fill_price_estimate=bad,
            desired_usd=10.0,
            current_position_usd=0.0,
            total_exposure_usd=0.0,
            limits=limits,
            state=state,
        )
        assert not d.allowed
