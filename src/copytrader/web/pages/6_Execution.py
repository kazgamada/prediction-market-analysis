"""Execution Console (MOCKUP) — single viewport layout."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from copytrader.web.auth import require_password

st.set_page_config(page_title="Execution", layout="wide",
                   initial_sidebar_state="collapsed")
require_password()

st.markdown("""
<style>
.block-container { padding-top: 0.6rem !important; padding-bottom: 0.4rem !important; max-width: 100% !important; }
[data-testid="stMetric"] { padding: 0.1rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.7rem !important; }
[data-testid="stMetricValue"] { font-size: 1.0rem !important; }
[data-testid="stMetricDelta"] { font-size: 0.65rem !important; }
h1, h2, h3, h4 { padding: 0 !important; margin: 0.2rem 0 !important; }
h1 { font-size: 1.2rem !important; }
h3 { font-size: 0.85rem !important; }
hr { margin: 0.3rem 0 !important; }
.stDataFrame { font-size: 0.72rem !important; }
[data-testid="stVerticalBlockBorderWrapper"] { padding: 0.3rem 0.5rem !important; }
.stProgress > div > div > div { height: 6px !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("# Execution Console　<small style='font-size:0.7rem;color:#888;'>MOCKUP</small>",
            unsafe_allow_html=True)

rng = np.random.default_rng(7)

sb = st.columns([1, 1, 1, 1, 1, 1.2])
sb[0].metric("USDC", "$8,432", "-$120")
sb[1].metric("MATIC", "12.4", "OK")
sb[2].metric("オープン", "7", "$3,210")
sb[3].metric("今日 PnL", "+$184", "+2.2%")
sb[4].metric("Sharpe (30d)", "1.42", "+0.08")
with sb[5]:
    kill = st.toggle("Kill Switch", value=False, key="kill_mock")
    if kill:
        st.error("🛑 HALTED", icon="🛑")
    else:
        st.success("🟢 LIVE", icon="🟢")

r1 = st.columns([1, 1.3, 1.3])

with r1[0], st.container(border=True):
    st.markdown("##### リスク")
    g = go.Figure(go.Indicator(
        mode="gauge+number", value=3.2,
        number={"suffix": "%", "valueformat": ".1f", "font": {"size": 22}},
        title={"text": "今日 DD", "font": {"size": 10}},
        gauge={"axis": {"range": [0, 8], "tickfont": {"size": 8}},
               "bar": {"color": "#d9534f"},
               "steps": [{"range": [0, 4], "color": "#e7f6e7"},
                         {"range": [4, 6.4], "color": "#fff3cd"},
                         {"range": [6.4, 8], "color": "#f8d7da"}],
               "threshold": {"line": {"color": "red", "width": 3},
                             "thickness": 0.75, "value": 8}}))
    g.update_layout(height=160, margin=dict(t=20, b=0, l=10, r=10))
    st.plotly_chart(g, use_container_width=True)
    st.progress(0.43, text="exposure 43/70%")
    st.progress(1.0, text="単一 token 27/25% ⚠")
    st.progress(0.62, text="trades 62/100")

with r1[1], st.container(border=True):
    st.markdown("##### オープンポジション")
    pos = pd.DataFrame({
        "market": ["米大統領 — Dem", "FRB 6月 — Yes", "BTC>$150k — Yes",
                   "AI バブル — No", "G7 — Yes", "WC — Brazil", "投票率 — Yes"],
        "side": ["B", "B", "B", "S", "B", "B", "B"],
        "size": [320, 250, 480, 410, 200, 180, 1370],
        "PnL": [22.8, 13.6, 80.0, 12.0, -2.8, -30.0, 90.2],
    })
    st.dataframe(pos, use_container_width=True, hide_index=True, height=270,
                 column_config={
                     "size": st.column_config.NumberColumn(format="$%d"),
                     "PnL": st.column_config.NumberColumn(format="$%+.1f"),
                 })

with r1[2], st.container(border=True):
    st.markdown("##### 受信シグナル")
    now = datetime.now(UTC)
    sig = pd.DataFrame({
        "時刻": [(now - timedelta(seconds=int(s))).strftime("%H:%M:%S")
                 for s in sorted(rng.integers(5, 900, 7))],
        "wallet": [f"0x{rng.integers(0, 16**8):08x}" for _ in range(7)],
        "market": rng.choice(["米大統領", "FRB", "BTC", "AI"], 7),
        "side": rng.choice(["B", "S"], 7).tolist(),
        "price": [round(float(rng.uniform(0.1, 0.9)), 3) for _ in range(7)],
        "状態": rng.choice(["✅", "⏳", "❌", "⏭"], 7, p=[0.5, 0.2, 0.1, 0.2]).tolist(),
    })
    st.dataframe(sig, use_container_width=True, hide_index=True, height=270)

r2 = st.columns([1.5, 1.5, 1])

with r2[0], st.container(border=True):
    st.markdown("##### 直近 fills (latency)")
    fills = pd.DataFrame({
        "時刻": [(datetime.now(UTC) - timedelta(seconds=int(s))).strftime("%H:%M:%S")
                 for s in sorted(rng.integers(30, 7200, 7))],
        "market": rng.choice(["米大統領", "FRB", "BTC", "AI", "WC"], 7),
        "side": rng.choice(["B", "S"], 7).tolist(),
        "size": [int(rng.choice([50, 100, 150, 200])) for _ in range(7)],
        "ms": [int(rng.normal(850, 280)) for _ in range(7)],
        "slip%": [round(float(rng.normal(0.4, 0.6)), 2) for _ in range(7)],
        "PnL": [round(float(rng.normal(2, 12)), 2) for _ in range(7)],
    })
    st.dataframe(fills, use_container_width=True, hide_index=True, height=270,
                 column_config={
                     "size": st.column_config.NumberColumn(format="$%d"),
                     "ms": st.column_config.NumberColumn(format="%d"),
                     "slip%": st.column_config.NumberColumn(format="%+.2f"),
                     "PnL": st.column_config.NumberColumn(format="$%+.1f"),
                 })

with r2[1], st.container(border=True):
    st.markdown("##### 執行パラメータ")
    p1, p2 = st.columns(2)
    with p1:
        st.number_input("1 trade $", value=250, min_value=10, max_value=2000,
                        key="ex_trade", label_visibility="visible")
        st.number_input("1 market $", value=500, min_value=50, max_value=5000,
                        key="ex_market")
        st.number_input("日次 DD %", value=8.0, min_value=1.0, max_value=30.0,
                        step=0.5, key="ex_dd")
    with p2:
        st.number_input("連敗で半減", value=3, min_value=1, max_value=10,
                        key="ex_lose")
        st.number_input("delay 秒", value=30, min_value=0, max_value=300,
                        key="ex_delay")
        st.selectbox("order type",
                     ["limit best", "limit mid", "market"], key="ex_type")

with r2[2], st.container(border=True):
    st.markdown("##### 手動 override")
    with st.form("manual"):
        st.text_input("token_id", "0x1234ab…", disabled=True,
                      label_visibility="collapsed")
        st.selectbox("side", ["BUY", "SELL"], label_visibility="collapsed")
        st.number_input("size $", min_value=10, max_value=1000, value=50,
                        step=10, label_visibility="collapsed")
        st.number_input("price", min_value=0.01, max_value=0.99, value=0.50,
                        step=0.01, format="%.2f", label_visibility="collapsed")
        ok = st.checkbox("リスク無視")
        st.form_submit_button("発注", type="primary",
                              use_container_width=True, disabled=not ok)
