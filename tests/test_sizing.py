from copytrader.executor.sizing import CopyConfig, desired_usd


def test_fixed_usd_sizing():
    cfg = CopyConfig(fixed_usd=5.0, max_usd=50.0)
    assert desired_usd(100.0, 0.5, cfg) == 5.0
    assert desired_usd(1.0, 0.99, cfg) == 5.0


def test_follow_pct_sizing():
    cfg = CopyConfig(fixed_usd=0.0, follow_pct=0.01, max_usd=50.0)
    # source notional = 1000 * 0.5 = 500; 1% = 5
    assert desired_usd(1000.0, 0.5, cfg) == 5.0


def test_follow_pct_capped_by_max():
    cfg = CopyConfig(fixed_usd=0.0, follow_pct=0.5, max_usd=20.0)
    # source notional = 100 * 0.5 = 50; 50% = 25 -> capped at 20
    assert desired_usd(100.0, 0.5, cfg) == 20.0
