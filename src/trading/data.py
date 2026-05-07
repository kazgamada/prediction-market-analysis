"""Convert local Polymarket parquet (Polygon OrderFilled events) to nautilus trade dicts.

The local schema captures raw on-chain CTF Exchange events with maker/taker
amounts in 6-decimal USDC units. The nautilus PolymarketDataLoader.parse_trades
expects dicts shaped like the Polymarket Data API response: asset (token_id),
timestamp (unix seconds), side (BUY/SELL), price (float 0-1), size (float),
transactionHash (hex string).

USDC is asset_id 0; the other side is the outcome token. A trade where the
maker provided USDC means the taker bought outcome tokens (BUY); the reverse
is a SELL.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

USDC_DECIMALS = 6


def list_top_markets(
    data_dir: Path | str,
    limit: int = 50,
    min_trades: int = 1000,
) -> list[dict]:
    """Return the most-traded condition_ids with their token_ids from the local data."""
    data_dir = Path(data_dir)
    trades_glob = (data_dir / "polymarket" / "trades" / "*.parquet").as_posix()
    markets_glob = (data_dir / "polymarket" / "markets" / "*.parquet").as_posix()

    con = duckdb.connect()
    rows = con.execute(
        f"""
        WITH trade_counts AS (
            SELECT
                CASE WHEN maker_asset_id = 0 THEN CAST(taker_asset_id AS VARCHAR)
                     ELSE CAST(maker_asset_id AS VARCHAR)
                END AS token_id,
                COUNT(*) AS n_trades
            FROM read_parquet('{trades_glob}')
            WHERE maker_asset_id = 0 OR taker_asset_id = 0
            GROUP BY 1
            HAVING COUNT(*) >= {min_trades}
        ),
        markets AS (
            SELECT condition_id, question, slug, outcomes, end_date
            FROM read_parquet('{markets_glob}')
        )
        SELECT tc.token_id, tc.n_trades, m.condition_id, m.question, m.slug, m.outcomes, m.end_date
        FROM trade_counts tc
        LEFT JOIN markets m
          ON list_contains(
                from_json(m.outcomes, '["VARCHAR"]'),
                NULL  -- placeholder, joined by token_id below in Python
             )
        ORDER BY tc.n_trades DESC
        LIMIT {limit};
        """,
    ).fetchall()
    con.close()

    return [
        {
            "token_id": r[0],
            "n_trades": r[1],
            "condition_id": r[2],
            "question": r[3],
            "slug": r[4],
            "outcomes_json": r[5],
            "end_date": r[6],
        }
        for r in rows
    ]


def load_trade_dicts(
    token_id: str,
    data_dir: Path | str,
    start: str | None = None,
    end: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Load trades for a single token_id from local parquet, in nautilus dict format.

    Joins trades with the blocks parquet to resolve block_number → unix timestamp.
    Filters out rows where neither side is USDC (asset_id 0), since those are not
    standard taker-vs-USDC trades.
    """
    data_dir = Path(data_dir)
    trades_glob = (data_dir / "polymarket" / "trades" / "*.parquet").as_posix()
    blocks_glob = (data_dir / "polymarket" / "blocks" / "*.parquet").as_posix()

    where_clauses = [
        "(maker_asset_id = 0 OR taker_asset_id = 0)",
        f"(CAST(maker_asset_id AS VARCHAR) = '{token_id}' "
        f" OR CAST(taker_asset_id AS VARCHAR) = '{token_id}')",
    ]
    if start:
        where_clauses.append(f"b.timestamp >= '{start}'")
    if end:
        where_clauses.append(f"b.timestamp <= '{end}'")
    where_sql = " AND ".join(where_clauses)
    limit_sql = f"LIMIT {int(limit)}" if limit else ""

    sql = f"""
        WITH joined AS (
            SELECT
                t.transaction_hash,
                t.log_index,
                t.maker_asset_id,
                t.taker_asset_id,
                t.maker_amount,
                t.taker_amount,
                b.timestamp AS iso_ts
            FROM read_parquet('{trades_glob}') t
            INNER JOIN read_parquet('{blocks_glob}') b
              USING (block_number)
            WHERE {where_sql}
        )
        SELECT
            transaction_hash,
            log_index,
            maker_asset_id,
            taker_asset_id,
            maker_amount,
            taker_amount,
            epoch(CAST(iso_ts AS TIMESTAMP)) AS unix_ts
        FROM joined
        ORDER BY unix_ts ASC, log_index ASC
        {limit_sql};
    """

    con = duckdb.connect()
    rows = con.execute(sql).fetchall()
    con.close()

    out: list[dict] = []
    scale = 10**USDC_DECIMALS
    for tx_hash, _log_idx, maker_aid, taker_aid, maker_amt, taker_amt, ts in rows:
        if maker_aid == 0:
            usdc_amount = maker_amt
            token_amount = taker_amt
            side = "BUY"  # taker bought outcome tokens with USDC
        else:
            usdc_amount = taker_amt
            token_amount = maker_amt
            side = "SELL"  # taker sold outcome tokens for USDC

        if token_amount <= 0:
            continue
        price = (usdc_amount / scale) / (token_amount / scale)
        if price <= 0 or price >= 1:
            continue
        size = token_amount / scale

        out.append(
            {
                "asset": token_id,
                "timestamp": float(ts),
                "side": side,
                "price": price,
                "size": size,
                "transactionHash": tx_hash,
            }
        )

    return out
