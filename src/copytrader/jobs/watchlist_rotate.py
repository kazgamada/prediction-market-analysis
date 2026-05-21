"""Auto-rotate watchlist based on recent rank + 7d PnL.

Nightly job:
1. Take latest phase0 result's ranked wallets → promote top N to Watchlist.
2. For each existing active wallet, check 7d realized PnL. If below
   demote_pnl_7d threshold → set active=false.
3. Log all changes to audit_log.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from copytrader.analysis.rank import rank_wallets
from copytrader.db import settings_table
from copytrader.db.engine import get_session
from copytrader.db.models import AuditLog, Trade, Watchlist

log = logging.getLogger("jobs.watchlist_rotate")


def _audit(action: str, details: dict) -> None:
    with get_session() as s:
        s.add(AuditLog(actor="system", action=action, details=details))


def _wallet_7d_pnl(address: bytes) -> tuple[Decimal, int]:
    """Compute 7-day realized PnL for one wallet using simple closed-trade
    PnL via existing compute_wallet_pnl pathway. Returns (pnl, trade_count).
    """
    from copytrader.analysis.pnl import (
        TradeRow,
        compute_wallet_pnl,
    )
    since = datetime.now(UTC) - timedelta(days=7)
    with get_session() as s:
        rows = s.execute(
            select(
                Trade.ts, Trade.taker, Trade.token_id, Trade.side,
                Trade.price, Trade.size_shares, Trade.size_usdc,
            )
            .where(Trade.taker == address)
            .where(Trade.ts >= since)
            .order_by(Trade.ts)
        ).all()
    if not rows:
        return Decimal(0), 0
    trades = [TradeRow(*r) for r in rows]
    wallets = compute_wallet_pnl(trades)
    wp = wallets.get(address)
    if not wp:
        return Decimal(0), 0
    return wp.realized_pnl_usdc, wp.trades


def run_watchlist_rotate_job(params: dict) -> dict:
    """Entry point invoked by job_runner for kind='watchlist_rotate'."""
    if not bool(settings_table.get("auto_rotate_enabled") or False):
        log.info("watchlist_rotate: disabled via settings")
        return {"skipped": "auto_rotate_disabled"}

    top_n = int(params.get("top_n") or settings_table.get("auto_rotate_top_n") or 15)
    window_days = int(params.get("window_days") or 30)
    min_trades = int(
        params.get("min_trades") or settings_table.get("rank_min_trades") or 30
    )
    min_volume = float(
        params.get("min_volume_usdc")
        or settings_table.get("rank_min_volume_usdc") or 5000.0
    )
    demote_pnl_7d = float(
        params.get("demote_pnl_7d")
        or settings_table.get("auto_rotate_demote_pnl_7d") or -200.0
    )
    min_trades_7d = int(
        params.get("min_trades_7d")
        or settings_table.get("auto_rotate_min_trades_7d") or 5
    )

    promoted: list[str] = []
    demoted: list[dict] = []
    kept: list[str] = []

    ranked = rank_wallets(
        window_days=window_days,
        min_trades=min_trades,
        min_volume_usdc=min_volume,
        top_n=top_n,
    )
    log.info("watchlist_rotate: top %d ranked wallets", len(ranked))

    # PROMOTE: top N wallets, upsert active=true
    with get_session() as s:
        for r in ranked:
            addr_bytes = bytes.fromhex(r.address[2:])
            stmt = pg_insert(Watchlist).values(
                address=addr_bytes,
                note=f"auto: {r.realized_pnl_usdc:+.0f} usdc, "
                     f"wr={float(r.win_rate or 0):.2f}",
                active=True,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[Watchlist.address],
                set_={"active": True, "note": stmt.excluded.note},
            )
            s.execute(stmt)
            promoted.append(r.address)

    # DEMOTE: existing active wallets not in ranked, with poor 7d PnL
    ranked_set = {bytes.fromhex(r.address[2:]) for r in ranked}
    with get_session() as s:
        active_rows = s.execute(
            select(Watchlist).where(Watchlist.active.is_(True))
        ).scalars().all()
        for w in active_rows:
            if w.address in ranked_set:
                kept.append("0x" + w.address.hex())
                continue
            pnl_7d, trades_7d = _wallet_7d_pnl(w.address)
            if (
                float(pnl_7d) < demote_pnl_7d
                or trades_7d < min_trades_7d
            ):
                s.get(Watchlist, w.address).active = False
                demoted.append({
                    "address": "0x" + w.address.hex(),
                    "pnl_7d": float(pnl_7d),
                    "trades_7d": trades_7d,
                })
            else:
                kept.append("0x" + w.address.hex())

    summary = {
        "promoted": len(promoted),
        "demoted": len(demoted),
        "kept": len(kept),
        "promoted_addresses": promoted[:5],
        "demoted_details": demoted[:5],
    }
    _audit("watchlist_rotate", summary)
    log.info("watchlist_rotate: %s", summary)
    return summary
