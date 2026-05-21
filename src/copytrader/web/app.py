"""Home (Dashboard) — single viewport, click-through tiles."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from copytrader.web.auth import require_password

st.set_page_config(page_title="Home", layout="wide",
                   initial_sidebar_state="collapsed")
require_password()

st.markdown("""
<style>
.block-container { padding-top: 0.6rem !important; padding-bottom: 0.4rem !important; max-width: 100% !important; }
[data-testid="stMetric"] { padding: 0.1rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.7rem !important; }
[data-testid="stMetricValue"] { font-size: 1.0rem !important; }
[data-testid="stMetricDelta"] { font-size: 0.65rem !important; }
[data-testid="stMetricDelta"] svg { width: 0.6rem !important; }
h1 { font-size: 1.2rem !important; padding: 0 !important; margin: 0 0 0.3rem 0 !important; }
hr { margin: 0.3rem 0 !important; }
[data-testid="stVerticalBlockBorderWrapper"] { padding: 0.3rem 0.5rem !important; border-radius: 6px !important; }
.stPageLink a { padding: 0 !important; font-size: 0.78rem !important; }
.stDataFrame { font-size: 0.72rem !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("# Home　<small style='font-size:0.7rem;color:#888;'>tile をクリックで詳細</small>",
            unsafe_allow_html=True)

rng = np.random.default_rng(42)

TILE_H = 130
LAY = dict(height=TILE_H, margin=dict(t=4, b=4, l=4, r=4),
           showlegend=False, font=dict(size=9))


def tile_header(title: str, page_path: str, icon: str = "🔗") -> None:
    st.page_link(page_path, label=f"**{title}**", icon=icon)


k = st.columns(6)
k[0].metric("累積 PnL", "+$12,847", "+$523")
k[1].metric("勝率", "58.3%", "+1.2pp")
k[2].metric("Watchlist", "12 / 50", "+2")
k[3].metric("最大 DD", "-8.4%", "-1.1pp", delta_color="inverse")
k[4].metric("USDC", "$8,432", "-$120")
k[5].metric("今日 PnL", "+$184", "+2.2%")

r1 = st.columns(4)

with r1[0], st.container(border=True):
    tile_header("Wallet equity (30d)", "pages/2_Execute.py", "👛")
    days = pd.date_range(end=datetime.now(UTC), periods=30, freq="D")
    eq_df = pd.DataFrame({
        "date": np.tile(days, 5),
        "wallet": np.repeat([f"w{i}" for i in range(5)], 30),
        "pnl": np.concatenate([
            np.cumsum(rng.normal(loc=b, scale=80, size=30)) for b in [25, 18, 12, 8, -3]
        ]),
    })
    fig = px.line(eq_df, x="date", y="pnl", color="wallet")
    fig.update_layout(**LAY, xaxis_title="", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True, key="t1")

with r1[1], st.container(border=True):
    tile_header("Drawdown", "pages/1_Strategy.py", "📉")
    pnl = np.cumsum(rng.normal(15, 80, 90)) + 200
    peak = np.maximum.accumulate(pnl)
    dd = (pnl - peak) / np.maximum(peak, 1) * 100
    f = go.Figure()
    f.add_trace(go.Scatter(x=pd.date_range(end=datetime.now(UTC), periods=90, freq="D"),
                           y=dd, fill="tozeroy", mode="lines",
                           line=dict(color="#d9534f", width=1)))
    f.add_hline(y=-15, line_dash="dash", line_color="orange")
    f.update_layout(**LAY, xaxis_title="", yaxis_title="")
    st.plotly_chart(f, use_container_width=True, key="t2")

with r1[2], st.container(border=True):
    tile_header("Replay ROI heatmap", "pages/1_Strategy.py", "🔥")
    delays = [15, 30, 60, 120, 300, 600]
    sizes = [10, 25, 50, 100, 250, 500]
    roi = rng.normal(2.5, 4, (len(sizes), len(delays)))
    roi[:, 0] += 3
    roi[:, -2:] -= 4
    f = go.Figure(data=go.Heatmap(z=roi, colorscale="RdYlGn", zmid=0, showscale=False))
    f.update_layout(**LAY, xaxis=dict(visible=False), yaxis=dict(visible=False))
    st.plotly_chart(f, use_container_width=True, key="t3")

with r1[3], st.container(border=True):
    tile_header("Top 10 戦略 equity", "pages/1_Strategy.py", "🏆")
    dates60 = pd.date_range(end=datetime.now(UTC), periods=60, freq="D")
    palette = px.colors.qualitative.Bold
    f = go.Figure()
    for i in range(6):
        sub = np.random.default_rng(100 + i)
        eq = np.cumsum(sub.normal(loc=(6 - i) * 6 / 60 * 10, scale=40, size=60)) + 1000
        f.add_trace(go.Scatter(x=dates60, y=eq, mode="lines",
                               line=dict(color=palette[i], width=1)))
    f.add_hline(y=1000, line_dash="dot", line_color="gray")
    f.update_layout(**LAY, xaxis_title="", yaxis_title="")
    st.plotly_chart(f, use_container_width=True, key="t4")

r2 = st.columns(4)

with r2[0], st.container(border=True):
    tile_header("市場×戦略 matrix", "pages/1_Strategy.py", "🧪")
    rm = rng.normal(3, 7, (8, 6))
    rm[2, :] += 5
    f = go.Figure(data=go.Heatmap(z=rm, colorscale="RdYlGn", zmid=0, showscale=False))
    f.update_layout(**LAY, xaxis=dict(visible=False), yaxis=dict(visible=False))
    st.plotly_chart(f, use_container_width=True, key="t5")

with r2[1], st.container(border=True):
    tile_header("シグナル時間帯", "pages/3_Ops.py", "⏰")
    heat = rng.poisson(3, (7, 24)).astype(float)
    heat[:, 13:22] *= 2.5
    heat[5:7, :] *= 0.6
    f = go.Figure(data=go.Heatmap(z=heat, colorscale="Blues", showscale=False))
    f.update_layout(**LAY, xaxis=dict(visible=False), yaxis=dict(visible=False))
    st.plotly_chart(f, use_container_width=True, key="t6")

with r2[2], st.container(border=True):
    tile_header("DD gauge (今日)", "pages/2_Execute.py", "🛑")
    g = go.Figure(go.Indicator(
        mode="gauge+number", value=3.2,
        number={"suffix": "%", "valueformat": ".1f", "font": {"size": 18}},
        gauge={"axis": {"range": [0, 8], "tickfont": {"size": 7}},
               "bar": {"color": "#d9534f"},
               "steps": [{"range": [0, 4], "color": "#e7f6e7"},
                         {"range": [4, 6.4], "color": "#fff3cd"},
                         {"range": [6.4, 8], "color": "#f8d7da"}],
               "threshold": {"line": {"color": "red", "width": 2},
                             "thickness": 0.75, "value": 8}}))
    g.update_layout(**LAY)
    st.plotly_chart(g, use_container_width=True, key="t7")

with r2[3], st.container(border=True):
    tile_header("Latency (signal→fill)", "pages/2_Execute.py", "⚡")
    lat = rng.normal(850, 280, 200).clip(min=100)
    f = go.Figure(data=go.Histogram(x=lat, nbinsx=20, marker_color="#2c7fb8"))
    f.add_vline(x=np.median(lat), line_dash="dash", line_color="orange")
    f.update_layout(**LAY, xaxis_title="", yaxis_title="")
    st.plotly_chart(f, use_container_width=True, key="t8")

r3 = st.columns(4)

with r3[0], st.container(border=True):
    tile_header("Position exposure", "pages/2_Execute.py", "💰")
    labels = ["米大統領", "FRB", "BTC", "AI", "G7", "WC", "投票率"]
    sizes_ = [320, 250, 480, 410, 200, 180, 1370]
    pnls = [22.8, 13.6, 80, 12, -2.8, -30, 90.2]
    colors = ["#2ca02c" if p >= 0 else "#d62728" for p in pnls]
    f = go.Figure(go.Bar(x=sizes_, y=labels, orientation="h", marker_color=colors))
    f.update_layout(**LAY, xaxis=dict(visible=False),
                    yaxis=dict(tickfont=dict(size=8)))
    st.plotly_chart(f, use_container_width=True, key="t9")

with r3[1], st.container(border=True):
    tile_header("Watchlist Top 5", "pages/2_Execute.py", "📋")
    df = pd.DataFrame({
        "wallet": [f"0x{rng.integers(0, 16**8):08x}" for _ in range(5)],
        "PnL": sorted([int(rng.normal(2000, 1200)) for _ in range(5)], reverse=True),
        "30d": [list(np.cumsum(rng.normal(0, 1, 20))) for _ in range(5)],
    })
    st.dataframe(df, use_container_width=True, hide_index=True, height=TILE_H,
                 column_config={
                     "PnL": st.column_config.NumberColumn(format="$%d", width="small"),
                     "30d": st.column_config.LineChartColumn(width="small"),
                 })

with r3[2], st.container(border=True):
    tile_header("受信シグナル", "pages/2_Execute.py", "📨")
    now = datetime.now(UTC)
    df = pd.DataFrame({
        "時刻": [(now - timedelta(seconds=int(s))).strftime("%H:%M:%S")
                 for s in sorted(rng.integers(5, 900, 5))],
        "side": rng.choice(["BUY", "SELL"], 5).tolist(),
        "状態": rng.choice(["✅", "⏳", "❌", "⏭"], 5, p=[0.5, 0.2, 0.1, 0.2]).tolist(),
    })
    st.dataframe(df, use_container_width=True, hide_index=True, height=TILE_H)

with r3[3], st.container(border=True):
    tile_header("Indexer lag", "pages/3_Ops.py", "📡")
    lag = rng.uniform(5, 60, 24)
    lag[-3:] *= 2.5
    f = go.Figure()
    f.add_trace(go.Scatter(
        x=pd.date_range(end=datetime.now(UTC), periods=24, freq="h"),
        y=lag, mode="lines+markers",
        line=dict(color="#5b9bd5", width=1), marker=dict(size=3)))
    f.add_hline(y=120, line_dash="dash", line_color="red")
    f.update_layout(**LAY, xaxis_title="", yaxis_title="")
    st.plotly_chart(f, use_container_width=True, key="t12")
