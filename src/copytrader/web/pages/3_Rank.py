"""Run wallet ranking with adjustable parameters."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from copytrader.ranking.pnl import persist_ranking, rank_wallets

st.title("Rank")
st.caption(
    "過去の trade からウォレット別の PnL・勝率・スコアを集計し、ランキング化します。Top N を選んで watchlist に自動投入も可能。"
)

with st.form("rank_form"):
    c1, c2, c3, c4 = st.columns(4)
    window = c1.number_input(
        "Window (days)",
        value=30,
        min_value=1,
        max_value=365,
        help="集計対象期間 (日数)。例: 30 なら過去 30 日の trade のみで集計。",
    )
    min_trades = c2.number_input(
        "Min trades",
        value=30,
        min_value=1,
        help="このしきい値未満の取引数しかないウォレットは除外。少ない試行をノイズとして弾く目的。",
    )
    min_volume = c3.number_input(
        "Min volume USD",
        value=5000.0,
        min_value=0.0,
        step=100.0,
        help="期間内の合計取引額がこの USD 未満のウォレットを除外。額が小さいウォレットを除く目的。",
    )
    limit = c4.number_input(
        "Limit",
        value=50,
        min_value=1,
        max_value=500,
        help="ランキング上位から何件まで返すか。表示と persist の対象件数。",
    )
    cols = st.columns([1, 1, 4])
    persist = cols[0].checkbox(
        "Persist",
        value=True,
        help="ON にすると wallets テーブルにスコアを保存。OFF だとプレビュー表示のみ。",
    )
    top_n_watch = cols[1].number_input(
        "Watchlist top N",
        value=0,
        min_value=0,
        max_value=200,
        help="0 以外を指定すると、上位 N 件を自動的に watchlist 入りさせます。0 なら何もしない。",
    )
    run = cols[2].form_submit_button(
        "Run",
        type="primary",
        help="集計を実行。trades テーブルが空なら結果は出ません (先に Backfill が必要)。",
    )

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
