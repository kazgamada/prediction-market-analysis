from decimal import Decimal

from copytrader.backtest.replay import _Position


def test_position_buy_then_full_sell_realizes_pnl():
    p = _Position()
    p.buy(Decimal("100"), Decimal("0.30"))
    assert p.size == Decimal("100")
    assert p.avg_entry == Decimal("0.30")
    p.sell(Decimal("100"), Decimal("0.50"))
    assert p.size == Decimal("0")
    assert p.realized == Decimal("20.00")
    assert p.n_winning == 1


def test_position_partial_sell():
    p = _Position()
    p.buy(Decimal("100"), Decimal("0.40"))
    p.sell(Decimal("40"), Decimal("0.50"))
    assert p.size == Decimal("60")
    assert p.realized == Decimal("4.00")


def test_position_loss_records_losing_close():
    p = _Position()
    p.buy(Decimal("50"), Decimal("0.60"))
    p.sell(Decimal("50"), Decimal("0.40"))
    assert p.realized == Decimal("-10.00")
    assert p.n_losing == 1


def test_avg_entry_weighted_across_buys():
    p = _Position()
    p.buy(Decimal("100"), Decimal("0.30"))
    p.buy(Decimal("100"), Decimal("0.50"))
    # weighted avg = (100*0.3 + 100*0.5) / 200 = 0.40
    assert p.avg_entry == Decimal("0.40")
