"""Inspect a single wallet."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from copytrader.analysis.wallets import stats
from copytrader.web import state
from copytrader.web.logs import (
    render_live_action,
    render_running_jobs_banner,
    run_with_live_logs,
)
from copytrader.web.nav import render_sidebar_menu_help

render_sidebar_menu_help()
_any_running = render_running_jobs_banner()
st.title("Inspect wallet")
st.caption(
    "1 つのウォレットを深掘り。トークン別の取引数・PnL・ネット保有量・最新取引時刻を一覧化します。Rank で気になったアドレスをここで確認。"
)

state.hydrate("inspect.addr", "")
state.hydrate("inspect.window", 30)

_any_running |= render_live_action("inspect.last_run")

with st.form("inspect_form"):
    addr = st.text_input(
        "Wallet address (0x…)", key="inspect.addr",
        help="調査対象ウォレットのアドレス。0x で始まる 42 文字 hex。",
    )
    window = st.number_input(
        "Window (days)", min_value=1, max_value=365, key="inspect.window",
        help="集計期間 (日数)。例: 30 なら過去 30 日の trade のみで PnL を算出。",
    )
    run = st.form_submit_button(
        "Inspect", type="primary",
        help="このアドレスのトークン別 PnL を計算・表示します。",
    )

if run and addr:
    state.remember("inspect.addr")
    state.remember("inspect.window")

    rows = run_with_live_logs(
        f"aggregating per-token stats for {addr[:10]}…",
        stats,
        addr,
        window_days=int(window),
        persist_key="inspect.last_run",
    )
    if not rows:
        st.warning("no trades for that wallet in the window")
        state.set("inspect.last_result", None)
    else:
        serialized = [
            {
                "token_id": r.token_id,
                "n_trades": int(r.n_trades),
                "pnl_usd": float(r.pnl_usd),
                "net_usdc": float(r.net_usdc),
                "net_tokens": float(r.net_tokens),
                "mark_price": float(r.mark_price) if r.mark_price is not None else None,
                "last_trade_at": (
                    r.last_trade_at.isoformat() if r.last_trade_at else None
                ),
            }
            for r in rows
        ]
        state.set("inspect.last_result", {
            "addr": addr,
            "rows": serialized,
            "ran_at": datetime.now(timezone.utc).isoformat(),
        })

# Re-render last result on revisit.
saved = state.hydrate("inspect.last_result")
if isinstance(saved, dict) and saved.get("rows"):
    df = pd.DataFrame(saved["rows"])
    total = df["pnl_usd"].sum() if "pnl_usd" in df.columns else 0.0
    st.metric(
        "Total PnL",
        f"${total:,.2f}",
        help=f"Σ per-token — last run @ {saved.get('ran_at', '?')}",
    )
    st.dataframe(df, use_container_width=True)

if _any_running:
    import time as _time

    _time.sleep(3)
    st.rerun()
