"""Executor crash-recovery + halt=pause semantics (E-6)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from copytrader.db.engine import get_session
from copytrader.db.models import Execution, Signal
from copytrader.execution.executor import _claim_pending, _recover_stale_executing
from copytrader.execution.order_state import (
    EXEC_PLACED,
    SIGNAL_EXECUTING,
    SIGNAL_PENDING,
)


def _mk_signal(status: str, *, execute_after_min_ago: int) -> int:
    now = datetime.now(UTC)
    with get_session() as s:
        sig = Signal(
            address=b"\x42" * 20,
            token_id=Decimal(1),
            side=0,
            price=Decimal("0.4"),
            size_usdc=Decimal("10"),
            ts=now,
            source="test",
            detected_at=now - timedelta(minutes=execute_after_min_ago + 1),
            execute_after=now - timedelta(minutes=execute_after_min_ago),
            status=status,
        )
        s.add(sig)
        s.flush()
        return sig.id


def test_stale_executing_without_execution_is_reset(fresh_db) -> None:
    sid = _mk_signal(SIGNAL_EXECUTING, execute_after_min_ago=5)
    n = _recover_stale_executing(stale_seconds=60)
    assert n == 1
    with get_session() as s:
        assert s.get(Signal, sid).status == SIGNAL_PENDING


def test_executing_with_execution_row_is_left_alone(fresh_db) -> None:
    sid = _mk_signal(SIGNAL_EXECUTING, execute_after_min_ago=5)
    with get_session() as s:
        s.add(Execution(
            signal_id=sid, token_id=Decimal(1), side=0,
            size_usdc=Decimal("10"), limit_price=Decimal("0.4"),
            placed_at=datetime.now(UTC), status=EXEC_PLACED,
            idempotency_key=f"test-{sid}",
        ))
    n = _recover_stale_executing(stale_seconds=60)
    assert n == 0
    with get_session() as s:
        assert s.get(Signal, sid).status == SIGNAL_EXECUTING


def test_fresh_executing_not_reset(fresh_db) -> None:
    # execute_after just now → within the stale window → not reset.
    sid = _mk_signal(SIGNAL_EXECUTING, execute_after_min_ago=0)
    n = _recover_stale_executing(stale_seconds=60)
    assert n == 0
    with get_session() as s:
        assert s.get(Signal, sid).status == SIGNAL_EXECUTING


def test_claim_only_takes_pending(fresh_db) -> None:
    # Pause semantics rely on PENDING signals being left intact while halted;
    # this pins that claim only ever consumes PENDING rows.
    pend = _mk_signal(SIGNAL_PENDING, execute_after_min_ago=1)
    _mk_signal(SIGNAL_EXECUTING, execute_after_min_ago=1)
    claimed = _claim_pending()
    assert [c.id for c in claimed] == [pend]
    with get_session() as s:
        rows = s.execute(select(Signal.status)).scalars().all()
    assert sorted(rows) == [SIGNAL_EXECUTING, SIGNAL_EXECUTING]  # pend now EXECUTING
