"""Killswitch: trip the bot on hard failures. Persists to risk_event."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from copytrader.db import session_scope
from copytrader.models import RiskEvent
from copytrader.risk.limits import RiskState

log = logging.getLogger(__name__)


def trip(state: RiskState, kind: str, detail: str) -> None:
    state.halted = True
    state.halt_reason = f"{kind}: {detail}"
    log.error("KILLSWITCH TRIPPED: %s — %s", kind, detail)
    with session_scope() as session:
        session.add(
            RiskEvent(
                occurred_at=datetime.now(timezone.utc),
                kind=kind,
                detail=detail,
                halted=True,
            )
        )


def record(kind: str, detail: str) -> None:
    """Log a non-halting risk event."""
    log.warning("risk event: %s — %s", kind, detail)
    with session_scope() as session:
        session.add(
            RiskEvent(
                occurred_at=datetime.now(timezone.utc),
                kind=kind,
                detail=detail,
                halted=False,
            )
        )
