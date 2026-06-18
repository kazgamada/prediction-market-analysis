"""Unit tests for the auth gate comparison and ERC-20 calldata (A-1, D-1)."""
from __future__ import annotations

from copytrader.execution.balance_client import _balance_of_calldata
from copytrader.web.auth import password_matches


def test_password_gate_open_when_unset() -> None:
    # Empty expected => gate disabled (dev), anything matches.
    assert password_matches("", "") is True
    assert password_matches("whatever", "") is True


def test_password_gate_enforced_when_set() -> None:
    assert password_matches("hunter2", "hunter2") is True
    assert password_matches("wrong", "hunter2") is False
    assert password_matches("", "hunter2") is False


def test_balance_of_calldata_encoding() -> None:
    addr = "0x" + "11" * 20
    data = _balance_of_calldata(addr)
    # selector + 32-byte left-padded address
    assert data.startswith("0x70a08231")
    assert len(data) == 10 + 64
    assert data.endswith("11" * 20)
    assert data[10:10 + 24] == "0" * 24  # left padding
    # case/0x-prefix insensitive
    assert _balance_of_calldata("11" * 20) == data
