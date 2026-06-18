"""Position reopen after going flat (E-8).

A single position row per token is the correct net-directional model (selling
YES shares you hold closes the long). The bug was that once a position went
flat, `side` was never reset, so reopening — especially on the opposite side —
silently failed to open. These tests pin the fresh-open behaviour.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from copytrader.db.engine import get_session
from copytrader.db.models import Execution, Position, Signal
from copytrader.execution.order_state import EXEC_PLACED
from copytrader.execution.position_tracker import _apply_fill


def _exec(side: int) -> Execution:
    now = datetime.now(UTC)
    with get_session() as s:
        sig = Signal(
            address=b"\x42" * 20, token_id=Decimal(1), side=side,
            price=Decimal("0.5"), size_usdc=Decimal("10"), ts=now, source="test",
        )
        s.add(sig)
        s.flush()
        ex = Execution(
            signal_id=sig.id,
            token_id=Decimal(1),
            side=side,
            size_usdc=Decimal("10"),
            limit_price=Decimal("0.5"),
            placed_at=now,
            status=EXEC_PLACED,
            idempotency_key=f"test-{sig.id}",
        )
        s.add(ex)
        s.flush()
        s.expunge(ex)
        return ex


def test_reopen_opposite_side_after_flat(fresh_db) -> None:
    # Open a BUY of 100 @ 0.40
    _apply_fill(_exec(0), Decimal("100"), Decimal("0.40"))
    # Close it fully with a SELL of 100 @ 0.60 → flat
    _apply_fill(_exec(1), Decimal("100"), Decimal("0.60"))
    with get_session() as s:
        pos = s.get(Position, Decimal(1))
        assert pos.open_size_shares == 0

    # Reopen on the opposite side (SELL 50 @ 0.55) — must actually open.
    _apply_fill(_exec(1), Decimal("50"), Decimal("0.55"))
    with get_session() as s:
        pos = s.get(Position, Decimal(1))
        assert pos.open_size_shares == Decimal("50")
        assert int(pos.side) == 1
        assert pos.avg_price == Decimal("0.55")


def test_reopen_same_side_after_flat(fresh_db) -> None:
    _apply_fill(_exec(0), Decimal("100"), Decimal("0.40"))
    _apply_fill(_exec(1), Decimal("100"), Decimal("0.60"))
    _apply_fill(_exec(0), Decimal("30"), Decimal("0.45"))
    with get_session() as s:
        pos = s.get(Position, Decimal(1))
        assert pos.open_size_shares == Decimal("30")
        assert int(pos.side) == 0
        assert pos.avg_price == Decimal("0.45")
