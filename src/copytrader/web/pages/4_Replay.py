"""Replay backtest with delay sweep."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from sqlalchemy import select

from copytrader.backtest.replay import replay_with_delays
from copytrader.db import session_scope
from copytrader.models import Wallet
from copytrader.web import state
from copytrader.web.logs import render_last_action, run_with_live_logs
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

state.hydrate("replay.window", 30)
state.hydrate("replay.delays", "30,60,120")
state.hydrate("replay.copy_usd", 50.0)
state.hydrate("replay.slippage_bps", 50)
state.hydrate("replay.top_n", 20)
state.hydrate("replay.explicit", [])

render_last_action("replay.last_run")

with st.form("replay_form"):
    c1, c2, c3, c4 = st.columns(4)
    window = c1.number_input(
        "Window (days)", min_value=1, max_value=365, key="replay.window",
        help="再現する過去期間 (日数)。trade テーブルからこの期間のシグナルを抽出します。",
    )
    delays_raw = c2.text_input(
        "Delays (sec, csv)", key="replay.delays",
        help="検出からコピー発注までの遅延候補 (秒)。CSV で複数指定すると並列に比較されます。",
    )
    copy_usd = c3.number_input(
        "Copy size USD", min_value=1.0, key="replay.copy_usd",
        help="各シグナルに対するコピー注文サイズ (USD)。固定額でシミュレーションします。",
    )
    slippage_bps = c4.number_input(
        "Slippage bps", min_value=0, max_value=500, key="replay.slippage_bps",
        help="想定スリッページ (1bps = 0.01%)。約定価格を保守的に悪化させて評価します。",
    )
    top_n = st.number_input(
        "Top N wallets to replay", min_value=1, max_value=200, key="replay.top_n",
        help="スコア上位のウォレットを何件まで再現するか。下のマルチセレクトを使うとこの値は無視されます。",
    )
    # filter previously-saved selections to current valid options
    saved_explicit = [a for a in state.hydrate("replay.explicit", []) if a in addr_options]
    if saved_explicit != st.session_state.get("replay.explicit"):
        st.session_state["replay.explicit"] = saved_explicit
    explicit = st.multiselect(
        "Or pick wallets explicitly (overrides Top N)",
        options=addr_options, key="replay.explicit",
        help="個別にウォレットを選びたい場合に指定。1つ以上選ぶと Top N より優先されます。",
    )
    run = st.form_submit_button(
        "Run replay", type="primary",
        help="バックテストを実行。ウォレット数 × 遅延数の組合せで集計します。少し時間がかかります。",
    )

if run:
    for k in ("replay.window", "replay.delays", "replay.copy_usd",
              "replay.slippage_bps", "replay.top_n", "replay.explicit"):
        state.remember(k)

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
        persist_key="replay.last_run",
    )

    summary_rows = []
    detail = {}
    for d, rows in results.items():
        agg = sum(r.total_pnl_usd for r in rows)
        positive = sum(1 for r in rows if r.total_pnl_usd > 0)
        summary_rows.append({
            "delay_s": int(d),
            "total_pnl_usd": float(agg),
            "positive_wallets": int(positive),
            "n_wallets": int(len(rows)),
            "win_share": (positive / len(rows)) if rows else 0,
        })
        detail[str(d)] = [
            {
                "address": r.address,
                "total_pnl_usd": float(r.total_pnl_usd),
                "realized": float(r.realized_pnl_usd),
                "unrealized": float(r.unrealized_pnl_usd),
                "win_rate": float(r.win_rate),
                "n_signals": int(r.n_signals),
                "n_filled": int(r.n_filled),
            }
            for r in rows
        ]
    state.set("replay.last_result", {
        "summary": summary_rows,
        "detail": detail,
        "ran_at": datetime.now(timezone.utc).isoformat(),
    })

# Re-render last result on revisit (or after a fresh run).
saved = state.hydrate("replay.last_result")
if isinstance(saved, dict) and saved.get("summary"):
    st.subheader(f"Aggregate by delay — last run @ {saved.get('ran_at', '?')}")
    st.dataframe(pd.DataFrame(saved["summary"]), use_container_width=True)
    for d_str, rows in (saved.get("detail") or {}).items():
        with st.expander(f"Delay {d_str}s — per wallet detail"):
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
