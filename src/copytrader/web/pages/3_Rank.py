"""Run wallet ranking with adjustable parameters."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from copytrader.ranking.pnl import persist_ranking, rank_wallets
from copytrader.web import state
from copytrader.web.logs import (
    render_live_action,
    render_running_jobs_banner,
    run_with_live_logs,
)
from copytrader.web.nav import render_sidebar_menu_help

render_sidebar_menu_help()
_any_running = render_running_jobs_banner()
st.title("Rank")
st.caption(
    "過去の trade からウォレット別の PnL・勝率・スコアを集計し、ランキング化します。Top N を選んで watchlist に自動投入も可能。"
)

state.hydrate("rank.window", 30)
state.hydrate("rank.min_trades", 30)
state.hydrate("rank.min_volume", 5000.0)
state.hydrate("rank.limit", 50)
state.hydrate("rank.persist", True)
state.hydrate("rank.top_n_watch", 0)

_any_running |= render_live_action("rank.last_run")

with st.form("rank_form"):
    c1, c2, c3, c4 = st.columns(4)
    window = c1.number_input(
        "Window (days)", min_value=1, max_value=365, key="rank.window",
        help="集計対象期間 (日数)。例: 30 なら過去 30 日の trade のみで集計。",
    )
    min_trades = c2.number_input(
        "Min trades", min_value=1, key="rank.min_trades",
        help="このしきい値未満の取引数しかないウォレットは除外。少ない試行をノイズとして弾く目的。",
    )
    min_volume = c3.number_input(
        "Min volume USD", min_value=0.0, step=100.0, key="rank.min_volume",
        help="期間内の合計取引額がこの USD 未満のウォレットを除外。額が小さいウォレットを除く目的。",
    )
    limit = c4.number_input(
        "Limit", min_value=1, max_value=500, key="rank.limit",
        help="ランキング上位から何件まで返すか。表示と persist の対象件数。",
    )
    cols = st.columns([1, 1, 4])
    persist = cols[0].checkbox(
        "Persist", key="rank.persist",
        help="ON にすると wallets テーブルにスコアを保存。OFF だとプレビュー表示のみ。",
    )
    top_n_watch = cols[1].number_input(
        "Watchlist top N", min_value=0, max_value=200, key="rank.top_n_watch",
        help="0 以外を指定すると、上位 N 件を自動的に watchlist 入りさせます。0 なら何もしない。",
    )
    run = cols[2].form_submit_button(
        "Run", type="primary",
        help="集計を実行。trades テーブルが空なら結果は出ません (先に Backfill が必要)。",
    )

if run:
    for k in ("rank.window", "rank.min_trades", "rank.min_volume", "rank.limit",
              "rank.persist", "rank.top_n_watch"):
        state.remember(k)

    stats = run_with_live_logs(
        "aggregating per-wallet PnL",
        rank_wallets,
        window_days=int(window),
        min_trades=int(min_trades),
        min_volume_usd=float(min_volume),
        limit=int(limit),
        persist_key="rank.last_run",
    )
    if not stats:
        st.warning("no rows; check that backfill has populated trades")
        state.set("rank.last_result", None)
    else:
        rows = [
            {
                "address": s.address,
                "pnl_usd": float(s.pnl_usd),
                "volume_usd": float(s.volume_usd),
                "n_trades": int(s.n_trades),
                "n_tokens": int(s.n_tokens),
                "score": float(s.score),
            }
            for s in stats
        ]
        state.set(
            "rank.last_result",
            {
                "rows": rows,
                "params": {
                    "window": int(window),
                    "min_trades": int(min_trades),
                    "min_volume": float(min_volume),
                    "limit": int(limit),
                },
                "ran_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        if persist:
            run_with_live_logs(
                "persisting wallet ranking to DB",
                persist_ranking,
                stats,
                top_n_watchlist=int(top_n_watch),
                persist_key="rank.last_persist",
            )

# Re-render last result on revisit (or after a fresh run).
saved = state.hydrate("rank.last_result")
if isinstance(saved, dict) and saved.get("rows"):
    df = pd.DataFrame(saved["rows"])
    st.success(f"{len(df)} wallets — last run @ {saved.get('ran_at', '?')}")
    st.dataframe(df, use_container_width=True)

if _any_running:
    import time as _time

    _time.sleep(3)
    st.rerun()
