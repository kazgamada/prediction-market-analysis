"""Run wallet ranking with adjustable parameters."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from copytrader.ranking.pnl import persist_ranking, rank_wallets

st.title("Rank")

with st.form("rank_form"):
    c1, c2, c3, c4 = st.columns(4)
    window = c1.number_input("Window (days)", value=30, min_value=1, max_value=365)
    min_trades = c2.number_input("Min trades", value=30, min_value=1)
    min_volume = c3.number_input("Min volume USD", value=5000.0, min_value=0.0, step=100.0)
    limit = c4.number_input("Limit", value=50, min_value=1, max_value=500)
    cols = st.columns([1, 1, 4])
    persist = cols[0].checkbox("Persist", value=True)
    top_n_watch = cols[1].number_input("Watchlist top N", value=0, min_value=0, max_value=200)
    run = cols[2].form_submit_button("Run", type="primary")

if run:
    with st.spinner("aggregating per-wallet PnL…"):
        stats = rank_wallets(
            window_days=int(window),
            min_trades=int(min_trades),
            min_volume_usd=float(min_volume),
            limit=int(limit),
        )
    if not stats:
        st.warning("no rows; check that backfill has populated trades")
    else:
        df = pd.DataFrame(
            [
                {
                    "address": s.address,
                    "pnl_usd": s.pnl_usd,
                    "volume_usd": s.volume_usd,
                    "n_trades": s.n_trades,
                    "n_tokens": s.n_tokens,
                    "score": s.score,
                }
                for s in stats
            ]
        )
        st.success(f"{len(df)} wallets")
        st.dataframe(df, use_container_width=True)

        if persist:
            persist_ranking(stats, top_n_watchlist=int(top_n_watch))
            st.info(
                f"persisted; top {int(top_n_watch)} marked watchlisted"
                if top_n_watch
                else "persisted"
            )
