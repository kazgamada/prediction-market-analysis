from decimal import Decimal

from copytrader.executor.poller import _parse_decimal


def test_parse_decimal_none_is_zero():
    assert _parse_decimal(None) == Decimal(0)


def test_parse_decimal_string():
    assert _parse_decimal("1.234") == Decimal("1.234")


def test_parse_decimal_int():
    assert _parse_decimal(5) == Decimal(5)


def test_parse_decimal_float():
    assert _parse_decimal(0.1) == Decimal("0.1")
