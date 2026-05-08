"""Reconcile bot positions with on-chain CTF balances.

If the on-chain balance for a token diverges from the DB position by more than
`tolerance_tokens`, log a risk_event. If `trip_on_mismatch`, also flip the
killswitch — caller decides whether to abort live trading.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select

from copytrader.chain.balances import get_ctf_balances
from copytrader.chain.client import PolygonClient
from copytrader.config import get_settings
from copytrader.db import session_scope
from copytrader.models import Position
from copytrader.risk.killswitch import record as risk_record
from copytrader.risk.killswitch import trip
from copytrader.risk.limits import RiskState

log = logging.getLogger(__name__)


@dataclass
class Mismatch:
    token_id: str
    expected: Decimal
    actual: Decimal
    diff: Decimal


def _holder() -> str:
    s = get_settings()
    if s.wallet_proxy_address:
        return s.wallet_proxy_address
    if not s.wallet_private_key:
        raise RuntimeError(
            "Reconciler needs WALLET_PROXY_ADDRESS or WALLET_PRIVATE_KEY to know "
            "which wallet to read on-chain balances for."
        )
    from eth_account import Account

    return Account.from_key(s.wallet_private_key).address


def reconcile_live(
    state: RiskState | None = None,
    tolerance_tokens: Decimal = Decimal("0.5"),
    trip_on_mismatch: bool = True,
) -> list[Mismatch]:
    """Compare DB live positions with on-chain CTF balances; return mismatches."""
    holder = _holder()

    with session_scope() as session:
        positions = (
            session.execute(
                select(Position).where(
                    Position.mode == "live", Position.closed_at.is_(None)
                )
            )
            .scalars()
            .all()
        )
        snapshot = [(p.token_id, Decimal(p.size or 0)) for p in positions]

    if not snapshot:
        log.info("reconcile: no live positions")
        return []

    client = PolygonClient()
    on_chain = get_ctf_balances(holder, [tid for tid, _ in snapshot], client)

    mismatches: list[Mismatch] = []
    for tid, expected in snapshot:
        actual = on_chain.get(tid, Decimal(0))
        diff = (actual - expected).copy_abs()
        if diff > tolerance_tokens:
            mismatches.append(Mismatch(tid, expected, actual, diff))
            log.error(
                "reconcile MISMATCH token=%s expected=%s actual=%s diff=%s",
                tid,
                expected,
                actual,
                diff,
            )

    if not mismatches:
        log.info("reconcile: %s positions OK (holder=%s)", len(snapshot), holder)
        return []

    detail = "; ".join(
        f"{m.token_id[:12]}…: db={m.expected} chain={m.actual}" for m in mismatches
    )
    if trip_on_mismatch and state is not None:
        trip(state, "reconcile_mismatch", detail)
    else:
        risk_record("reconcile_mismatch", detail)
    return mismatches
