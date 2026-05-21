"""Execution Console (MOCKUP).

金を動かす執行レイヤの UI モック。全てダミーデータ。本実装では:
  * 残高: py-clob-client + Polygon RPC (USDC.balanceOf, MATIC)
  * シグナルキュー: signals テーブル（watchlist 約定検知から流入）
  * オープン: positions テーブル + CLOB の orders/fills 集計
  * kill switch: settings テーブルの halt_trading フラグ（worker が毎ループ参照）
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from copytrader.web.auth import require_password

st.set_page_config(page_title="Execution (Mockup)", layout="wide")
require_password()

st.title("Execution Console")
st.warning(
    "MOCKUP — 全てダミーデータ。本物の発注は一切しません。"
    "本実装では py-clob-client + signals/positions テーブルに接続します。"
)

rng = np.random.default_rng(7)

sb1, sb2, sb3, sb4, sb5 = st.columns([1.2, 1, 1, 1, 1.2])
sb1.metric("USDC 残高", "$8,432.10", "-$120 (24h)")
sb2.metric("MATIC ガス", "12.4", "OK")
sb3.metric("オープン", "7 positions", "$3,210 exposure")
sb4.metric("今日 PnL", "+$184.20", "+2.2%")
with sb5:
    st.write("**Kill Switch**")
    kill = st.toggle("発注停止", value=False, key="kill_switch_mock")
    if kill:
        st.error("HALTED — 自動発注を停止中")
    else:
        st.success("LIVE — 自動発注 ON")

st.divider()

risk_col, sig_col = st.columns([1, 1])

with risk_col:
    st.subheader("リスク状況")
    today_dd = 3.2
    max_dd_limit = 8.0
    g = go.Figure(go.Indicator(
        mode="gauge+number",
        value=today_dd,
        number={"suffix": "%", "valueformat": ".1f"},
        title={"text": "今日のドローダウン"},
        gauge={
            "axis": {"range": [0, max_dd_limit]},
            "bar": {"color": "#d9534f"},
            "steps": [
                {"range": [0, max_dd_limit * 0.5], "color": "#e7f6e7"},
                {"range": [max_dd_limit * 0.5, max_dd_limit * 0.8], "color": "#fff3cd"},
                {"range": [max_dd_limit * 0.8, max_dd_limit], "color": "#f8d7da"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 4},
                "thickness": 0.75, "value": max_dd_limit,
            },
        },
    ))
    g.update_layout(height=240, margin=dict(t=40, b=10, l=10, r=10))
    st.plotly_chart(g, use_container_width=True)

    st.markdown("**ポジション上限**")
    st.progress(0.43, text="総 market exposure  43% / max 70%")
    st.progress(1.0, text="単一 token (米大統領 2028)  27% / max 25%  ⚠ 上限超過")
    st.progress(0.62, text="日次取引数  62 / max 100")
    st.progress(0.38, text="連敗カウント  2 / max 5 で size 半減")

with sig_col:
    st.subheader("受信シグナル（直近 10 件）")
    st.caption("watchlist 約定 → signals テーブル → このリストで可視化。")
    now = datetime.now(UTC)
    sig = pd.DataFrame({
        "受信": [
            (now - timedelta(seconds=int(s))).strftime("%H:%M:%S")
            for s in sorted(rng.integers(5, 900, 10))
        ],
        "wallet": [f"0x{rng.integers(0, 16**8):08x}…" for _ in range(10)],
        "market": rng.choice(
            ["米大統領 2028", "FRB 6月 利下げ", "BTC>$150k EOY", "AI バブル崩壊"], 10,
        ),
        "side": rng.choice(["BUY", "SELL"], 10),
        "price": [round(float(rng.uniform(0.1, 0.9)), 3) for _ in range(10)],
        "状態": rng.choice(
            ["約定", "待機", "rejected", "skipped (上限)"], 10,
            p=[0.5, 0.2, 0.1, 0.2],
        ),
    })
    st.dataframe(sig, use_container_width=True, hide_index=True, height=320)

st.divider()

st.subheader("オープンポジション")
st.caption("含み損益はリアルタイムの best bid/ask で再評価。")
pos = pd.DataFrame({
    "market": [
        "米大統領 2028 — Dem", "FRB 6月 利下げ — Yes", "BTC>$150k — Yes",
        "AI バブル — No", "G7 開催 — Yes", "WC 優勝 — Brazil",
        "選挙投票率 60%+ — Yes",
    ],
    "side": ["BUY", "BUY", "BUY", "SELL", "BUY", "BUY", "BUY"],
    "size_usdc": [320, 250, 480, 410, 200, 180, 1370],
    "entry": [0.42, 0.55, 0.18, 0.31, 0.72, 0.24, 0.61],
    "現在価格": [0.45, 0.58, 0.21, 0.28, 0.71, 0.20, 0.65],
    "含み損益": [22.8, 13.6, 80.0, 12.0, -2.8, -30.0, 90.2],
    "保有時間": ["2h", "5h", "1d", "3d", "12h", "8h", "30m"],
    "follow": ["0xa3f…", "0xa3f…", "0x47b…", "0x91c…", "0xa3f…", "0x47b…", "0xd02…"],
})
st.dataframe(
    pos, use_container_width=True, hide_index=True,
    column_config={
        "size_usdc": st.column_config.NumberColumn("size", format="$%d"),
        "含み損益": st.column_config.NumberColumn(format="$%+.1f"),
        "entry": st.column_config.NumberColumn(format="%.3f"),
        "現在価格": st.column_config.NumberColumn(format="%.3f"),
    },
)

fill_col, manual_col = st.columns([2, 1])

with fill_col:
    st.subheader("直近 fills（signal→fill レイテンシ付き）")
    st.caption("コピートレードでは latency と slippage が命。p50/p95 を常時監視。")
    fills = pd.DataFrame({
        "時刻": [
            (datetime.now(UTC) - timedelta(seconds=int(s))).strftime("%H:%M:%S")
            for s in sorted(rng.integers(30, 7200, 12))
        ],
        "market": rng.choice(["米大統領", "FRB", "BTC", "AI", "WC"], 12),
        "side": rng.choice(["BUY", "SELL"], 12),
        "size": [int(rng.choice([50, 100, 150, 200, 250])) for _ in range(12)],
        "signal→fill": [int(rng.normal(850, 280)) for _ in range(12)],
        "slippage": [round(float(rng.normal(0.4, 0.6)), 2) for _ in range(12)],
        "確定 PnL": [round(float(rng.normal(2, 12)), 2) for _ in range(12)],
    })
    st.dataframe(
        fills, use_container_width=True, hide_index=True,
        column_config={
            "size": st.column_config.NumberColumn(format="$%d"),
            "signal→fill": st.column_config.NumberColumn(format="%d ms"),
            "slippage": st.column_config.NumberColumn(format="%+.2f%%"),
            "確定 PnL": st.column_config.NumberColumn(format="$%+.2f"),
        },
    )

with manual_col:
    st.subheader("手動オーバーライド")
    st.caption("緊急時のみ。通常は自動執行に任せる。")
    with st.form("manual_order"):
        st.text_input("token_id", "0x1234abcd…", disabled=True)
        st.selectbox("side", ["BUY", "SELL"])
        st.number_input("size (USDC)", min_value=10, max_value=1000, value=50, step=10)
        st.number_input(
            "limit price", min_value=0.01, max_value=0.99, value=0.50, step=0.01,
            format="%.2f",
        )
        st.selectbox("TIF", ["GTC", "IOC", "FOK"])
        confirm = st.checkbox("リスク上限を無視（!!!）")
        st.form_submit_button(
            "発注", type="primary", use_container_width=True, disabled=not confirm,
        )

st.divider()

st.subheader("執行レイヤ設定")
st.caption("ここの値は settings テーブルに保存され、worker が毎ループ参照。")
s1, s2, s3 = st.columns(3)
with s1:
    st.number_input("1 トレード最大 (USDC)", value=250, min_value=10, max_value=2000)
    st.number_input("1 market 最大 (USDC)", value=500, min_value=50, max_value=5000)
with s2:
    st.number_input(
        "日次最大 DD (%)", value=8.0, min_value=1.0, max_value=30.0, step=0.5,
    )
    st.number_input("連敗で size 半減 (連敗数)", value=3, min_value=1, max_value=10)
with s3:
    st.number_input("コピー遅延 (秒)", value=30, min_value=0, max_value=300)
    st.selectbox("発注タイプ", ["limit (best bid/ask)", "limit (mid)", "market"])

st.divider()
st.caption(
    "本実装の作業順: "
    "(1) settings テーブルに執行パラメータ追加 → "
    "(2) signals テーブル + watchlist 監視 worker → "
    "(3) py-clob-client write 側を別 module (`execution/clob.py`) で実装 → "
    "(4) kill switch flag を worker メインループに組み込み → "
    "(5) Telegram 通知 (`telegram_bot_token` は config に既に有り)"
)
