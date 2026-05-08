"""Compute per-wallet PnL aggregates from the trade table."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from copytrader.db import session_scope
from copytrader.models import Wallet

log = logging.getLogger(__name__)


@dataclass
class WalletStats:
    address: str
    pnl_usd: float
    n_trades: int
    volume_usd: float
    n_tokens: int
    score: float


_RANKING_SQL = text(
    """
    WITH wallet_flows AS (
        SELECT
            maker AS wallet,
            token_id,
            block_number,
            block_timestamp,
            CASE WHEN maker_asset_id = '0'
                 THEN -CAST(maker_amount AS NUMERIC) / 1000000
                 ELSE  CAST(taker_amount AS NUMERIC) / 1000000
            END AS usdc_flow,
            CASE WHEN maker_asset_id = '0'
                 THEN  CAST(taker_amount AS NUMERIC) / 1000000
                 ELSE -CAST(maker_amount AS NUMERIC) / 1000000
            END AS token_flow,
            notional_usd AS gross_volume
        FROM trade
        UNION ALL
        SELECT
            taker AS wallet,
            token_id,
            block_number,
            block_timestamp,
            CASE WHEN maker_asset_id = '0'
                 THEN  CAST(maker_amount AS NUMERIC) / 1000000
                 ELSE -CAST(taker_amount AS NUMERIC) / 1000000
            END AS usdc_flow,
            CASE WHEN maker_asset_id = '0'
                 THEN -CAST(taker_amount AS NUMERIC) / 1000000
                 ELSE  CAST(maker_amount AS NUMERIC) / 1000000
            END AS token_flow,
            notional_usd AS gross_volume
        FROM trade
    ),
    filtered AS (
        SELECT * FROM wallet_flows
        WHERE block_timestamp IS NULL
           OR block_timestamp >= :since
    ),
    marks AS (
        SELECT DISTINCT ON (token_id)
            token_id, price AS mark_price
        FROM trade
        ORDER BY token_id, block_number DESC, log_index DESC
    ),
    wallet_token AS (
        SELECT
            f.wallet,
            f.token_id,
            SUM(f.usdc_flow) AS net_usdc,
            SUM(f.token_flow) AS net_tokens,
            SUM(f.gross_volume) AS volume,
            COUNT(*) AS n_trades,
            COALESCE(m.mark_price, 0) AS mark_price
        FROM filtered f
        LEFT JOIN marks m ON m.token_id = f.token_id
        GROUP BY f.wallet, f.token_id, m.mark_price
    ),
    aggregated AS (
        SELECT
            wallet,
            SUM(net_usdc + net_tokens * mark_price) AS pnl_usd,
            SUM(n_trades) AS n_trades,
            SUM(volume) AS volume_usd,
            COUNT(DISTINCT token_id) AS n_tokens
        FROM wallet_token
        GROUP BY wallet
    )
    SELECT
        wallet,
        pnl_usd,
        n_trades,
        volume_usd,
        n_tokens
    FROM aggregated
    WHERE n_trades >= :min_trades
      AND volume_usd >= :min_volume
    ORDER BY pnl_usd DESC
    LIMIT :limit
    """
)


def rank_wallets(
    window_days: int = 30,
    min_trades: int = 30,
    min_volume_usd: float = 5000.0,
    limit: int = 200,
) -> list[WalletStats]:
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    with session_scope() as session:
        rows = session.execute(
            _RANKING_SQL,
            {
                "since": since,
                "min_trades": min_trades,
                "min_volume": min_volume_usd,
                "limit": limit,
            },
        ).all()

    out = []
    for r in rows:
        addr, pnl, n_trades, volume, n_tokens = r
        n_trades = int(n_trades)
        score = float(pnl) / max(math.sqrt(n_trades), 1.0)
        out.append(
            WalletStats(
                address=str(addr).lower(),
                pnl_usd=float(pnl),
                n_trades=n_trades,
                volume_usd=float(volume),
                n_tokens=int(n_tokens),
                score=score,
            )
        )
    return out


def persist_ranking(stats: list[WalletStats], top_n_watchlist: int = 0) -> None:
    """Upsert wallet stats; optionally mark the top N as watchlisted."""
    if not stats:
        return
    rows = []
    for i, s in enumerate(stats):
        rows.append(
            dict(
                address=s.address,
                n_trades=s.n_trades,
                total_volume_usd=Decimal(str(s.volume_usd)),
                realized_pnl_usd=Decimal(str(s.pnl_usd)),
                score=Decimal(str(s.score)),
                watchlisted=i < top_n_watchlist,
                last_seen_at=datetime.now(timezone.utc),
            )
        )
    with session_scope() as session:
        stmt = insert(Wallet).values(rows)
        upd = {
            "n_trades": stmt.excluded.n_trades,
            "total_volume_usd": stmt.excluded.total_volume_usd,
            "realized_pnl_usd": stmt.excluded.realized_pnl_usd,
            "score": stmt.excluded.score,
            "last_seen_at": stmt.excluded.last_seen_at,
        }
        if top_n_watchlist > 0:
            upd["watchlisted"] = stmt.excluded.watchlisted
        stmt = stmt.on_conflict_do_update(index_elements=["address"], set_=upd)
        session.execute(stmt)
