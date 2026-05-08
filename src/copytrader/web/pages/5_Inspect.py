"""Inspect a single wallet."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from copytrader.analysis.wallets import stats

st.title("Inspect wallet")

with st.form("inspect_form"):
    addr = st.text_input("Wallet address (0x…)")
    window = st.number_input("Window (days)", value=30, min_value=1, max_value=365)
    run = st.form_submit_button("Inspect", type="primary")

if run and addr:
    with st.spinner("aggregating…"):
        rows = stats(addr, window_days=int(window))
    if not rows:
        st.warning("no trades for that wallet in the window")
    else:
        df = pd.DataFrame(
            [
                {
                    "token_id": r.token_id,
                    "n_trades": r.n_trades,
                    "pnl_usd": r.pnl_usd,
                    "net_usdc": r.net_usdc,
                    "net_tokens": r.net_tokens,
                    "mark_price": r.mark_price,
                    "last_trade_at": r.last_trade_at,
                }
                for r in rows
            ]
        )
        total = df["pnl_usd"].sum()
        st.metric("Total PnL", f"${total:,.2f}", help="Σ per-token (net USDC + net tokens × mark)")
        st.dataframe(df, use_container_width=True)
