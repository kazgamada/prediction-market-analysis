"""Inspect a single wallet's trades and per-token PnL from the indexed data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text

from copytrader.db import session_scope


@dataclass
class WalletTokenStat:
    token_id: str
    n_trades: int
    net_usdc: float
    net_tokens: float
    mark_price: float
    pnl_usd: float
    last_trade_at: datetime | None


_STATS_SQL = text(
    """
    WITH flows AS (
        SELECT
            token_id,
            block_timestamp,
            CASE WHEN maker_asset_id = '0'
                 THEN CASE WHEN lower(maker) = :addr
                           THEN -CAST(maker_amount AS NUMERIC) / 1000000
                           ELSE  CAST(maker_amount AS NUMERIC) / 1000000 END
                 ELSE CASE WHEN lower(maker) = :addr
                           THEN  CAST(taker_amount AS NUMERIC) / 1000000
                           ELSE -CAST(taker_amount AS NUMERIC) / 1000000 END
            END AS usdc_flow,
            CASE WHEN maker_asset_id = '0'
                 THEN CASE WHEN lower(maker) = :addr
                           THEN  CAST(taker_amount AS NUMERIC) / 1000000
                           ELSE -CAST(taker_amount AS NUMERIC) / 1000000 END
                 ELSE CASE WHEN lower(maker) = :addr
                           THEN -CAST(maker_amount AS NUMERIC) / 1000000
                           ELSE  CAST(maker_amount AS NUMERIC) / 1000000 END
            END AS token_flow
        FROM trade
        WHERE (lower(maker) = :addr OR lower(taker) = :addr)
          AND (block_timestamp IS NULL OR block_timestamp >= :since)
    ),
    marks AS (
        SELECT DISTINCT ON (token_id)
            token_id, price AS mark_price
        FROM trade
        ORDER BY token_id, block_number DESC, log_index DESC
    )
    SELECT
        f.token_id,
        COUNT(*) AS n,
        SUM(f.usdc_flow) AS net_usdc,
        SUM(f.token_flow) AS net_tokens,
        COALESCE(m.mark_price, 0) AS mark,
        MAX(f.block_timestamp) AS last_ts
    FROM flows f
    LEFT JOIN marks m ON m.token_id = f.token_id
    GROUP BY f.token_id, m.mark_price
    ORDER BY (SUM(f.usdc_flow) + SUM(f.token_flow) * COALESCE(m.mark_price, 0)) DESC
    """
)


def stats(address: str, window_days: int = 30) -> list[WalletTokenStat]:
    addr = address.lower()
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    with session_scope() as session:
        rows = session.execute(_STATS_SQL, {"addr": addr, "since": since}).all()
    out: list[WalletTokenStat] = []
    for tid, n, net_usdc, net_tokens, mark, last_ts in rows:
        net_usdc = Decimal(net_usdc or 0)
        net_tokens = Decimal(net_tokens or 0)
        mark = Decimal(mark or 0)
        out.append(
            WalletTokenStat(
                token_id=tid,
                n_trades=int(n),
                net_usdc=float(net_usdc),
                net_tokens=float(net_tokens),
                mark_price=float(mark),
                pnl_usd=float(net_usdc + net_tokens * mark),
                last_trade_at=last_ts,
            )
        )
    return out
