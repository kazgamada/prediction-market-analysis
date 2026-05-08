"""Poll the CLOB for live order status and reconcile our DB state.

Live orders are placed with status='placed' and an optimistic position update.
This poller queries the CLOB API for actual fills and:
  - sets status to 'filled' / 'cancelled' / 'partial'
  - corrects filled_size and avg_fill_price to the real values
  - adjusts the position with the *delta* between optimistic and actual
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from copytrader.clob.client import ClobClient
from copytrader.db import session_scope
from copytrader.executor.state import upsert_position
from copytrader.models import Order

log = logging.getLogger(__name__)

OPEN_STATUSES = ("placed", "partial")


def _parse_decimal(v) -> Decimal:
    if v is None:
        return Decimal(0)
    return Decimal(str(v))


def poll_open_orders(clob: ClobClient | None = None) -> int:
    """Refresh status for every open live order. Returns number updated."""
    clob = clob or ClobClient(signed=True)

    with session_scope() as session:
        orders = (
            session.execute(
                select(Order).where(
                    Order.mode == "live",
                    Order.status.in_(OPEN_STATUSES),
                    Order.clob_order_id.isnot(None),
                )
            )
            .scalars()
            .all()
        )
        snapshot = [
            (
                o.id,
                o.clob_order_id,
                o.token_id,
                o.side,
                Decimal(o.size or 0),
                Decimal(o.filled_size or 0),
                Decimal(o.limit_price or 0),
            )
            for o in orders
        ]

    updated = 0
    now = datetime.now(timezone.utc)
    for oid, cid, token_id, side, size, prev_filled, limit_price in snapshot:
        info = clob.get_order(cid) or {}
        new_status_raw = (info.get("status") or "").lower()
        size_matched = _parse_decimal(info.get("size_matched") or info.get("sizeMatched"))
        # CLOB returns partial / matched / cancelled / live; map to our statuses
        if new_status_raw in ("matched", "filled"):
            new_status = "filled"
        elif new_status_raw in ("cancelled", "canceled"):
            new_status = "cancelled"
        elif size_matched > 0 and size_matched < size:
            new_status = "partial"
        else:
            new_status = "placed"

        if new_status == "placed" and size_matched == prev_filled:
            continue  # nothing changed

        # Determine fill delta and price
        fill_delta = size_matched - prev_filled
        fill_price = limit_price  # CLOB API may not return per-trade VWAP cheaply
        trades = clob.get_trades(cid)
        if trades:
            total_size = Decimal(0)
            total_notional = Decimal(0)
            for t in trades:
                tsz = _parse_decimal(t.get("size") or t.get("size_matched"))
                tpx = _parse_decimal(t.get("price"))
                total_size += tsz
                total_notional += tsz * tpx
            if total_size > 0:
                fill_price = total_notional / total_size

        with session_scope() as session:
            order = session.get(Order, oid)
            if order is None:
                continue
            order.status = new_status
            order.filled_size = size_matched
            if size_matched > 0:
                order.avg_fill_price = fill_price
            if new_status in ("filled", "cancelled"):
                order.closed_at = now

        # Position delta: live insertion was optimistic at limit_price for the
        # full size. Apply correction = (real fill - optimistic at limit).
        if fill_delta != 0:
            upsert_position(
                token_id=token_id,
                mode="live",
                side=side,
                size_tokens=fill_delta,
                fill_price=fill_price,
            )

        updated += 1
        log.info(
            "poll: order=%s status=%s filled=%s avg_px=%s",
            oid,
            new_status,
            size_matched,
            fill_price,
        )

    return updated
