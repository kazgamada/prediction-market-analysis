"""Replay backtest with delay sweep."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from copytrader.backtest.replay import replay_with_delays
from copytrader.db import session_scope
from copytrader.models import Wallet
from copytrader.web.logs import run_with_live_logs
from copytrader.web.nav import render_sidebar_menu_help

render_sidebar_menu_help()
st.title("Replay backtest")
st.caption(
    "選択したウォレットの過去シグナルを、コピー遅延 (秒) を変えて再現発注し PnL を比較します。"
    "実取引せず Phase 0 の検証用。"
)

with session_scope() as session:
    candidates = (
        session.execute(
            select(Wallet.address, Wallet.score)
            .order_by(Wallet.score.desc().nullslast())
            .limit(200)
        )
        .all()
    )

if not candidates:
    st.warning("no wallets in DB; run Rank first")
    st.stop()

addr_options = [a for a, _ in candidates]
score_by = {a: float(s) if s else 0.0 for a, s in candidates}

with st.form("replay_form"):
    c1, c2, c3, c4 = st.columns(4)
    window = c1.number_input(
        "Window (days)",
        value=30,
        min_value=1,
        max_value=365,
        help="再現する過去期間 (日数)。trade テーブルからこの期間のシグナルを抽出します。",
    )
    delays_raw = c2.text_input(
        "Delays (sec, csv)",
        value="30,60,120",
        help="検出からコピー発注までの遅延候補 (秒)。CSV で複数指定すると並列に比較されます。",
    )
    copy_usd = c3.number_input(
        "Copy size USD",
        value=50.0,
        min_value=1.0,
        help="各シグナルに対するコピー注文サイズ (USD)。固定額でシミュレーションします。",
    )
    slippage_bps = c4.number_input(
        "Slippage bps",
        value=50,
        min_value=0,
        max_value=500,
        help="想定スリッページ (1bps = 0.01%)。約定価格を保守的に悪化させて評価します。",
    )
    top_n = st.number_input(
        "Top N wallets to replay",
        value=20,
        min_value=1,
        max_value=200,
        help="スコア上位のウォレットを何件まで再現するか。下のマルチセレクトを使うとこの値は無視されます。",
    )
    explicit = st.multiselect(
        "Or pick wallets explicitly (overrides Top N)",
        options=addr_options,
        default=[],
        help="個別にウォレットを選びたい場合に指定。1つ以上選ぶと Top N より優先されます。",
    )
    run = st.form_submit_button(
        "Run replay",
        type="primary",
        help="バックテストを実行。ウォレット数 × 遅延数の組合せで集計します。少し時間がかかります。",
    )

if run:
    delays = [int(x.strip()) for x in delays_raw.split(",") if x.strip()]
    wallets = explicit if explicit else addr_options[: int(top_n)]
    if not wallets:
        st.warning("no wallets selected")
        st.stop()

    results = run_with_live_logs(
        f"replaying {len(wallets)} wallets × {len(delays)} delays",
        replay_with_delays,
        wallets,
        delays,
        window_days=int(window),
        copy_size_usd=float(copy_usd),
        slippage_bps=int(slippage_bps),
    )

    summary = []
    for d, rows in results.items():
        agg = sum(r.total_pnl_usd for r in rows)
        positive = sum(1 for r in rows if r.total_pnl_usd > 0)
        summary.append(
            {
                "delay_s": d,
                "total_pnl_usd": agg,
                "positive_wallets": positive,
                "n_wallets": len(rows),
                "win_share": (positive / len(rows)) if rows else 0,
            }
        )
    st.subheader("Aggregate by delay")
    st.dataframe(pd.DataFrame(summary), use_container_width=True)

    for d, rows in results.items():
        with st.expander(f"Delay {d}s — per wallet detail"):
            df = pd.DataFrame(
                [
                    {
                        "address": r.address,
                        "total_pnl_usd": r.total_pnl_usd,
                        "realized": r.realized_pnl_usd,
                        "unrealized": r.unrealized_pnl_usd,
                        "win_rate": r.win_rate,
                        "n_signals": r.n_signals,
                        "n_filled": r.n_filled,
                    }
                    for r in rows
                ]
            )
            st.dataframe(df, use_container_width=True)
