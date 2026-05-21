"""Decision Dashboard (MOCKUP) — overview grid.

全グラフをタイル状に並べて一目で状況把握。各タイルのヘッダーをクリックで詳細ページに遷移。
本実装では analysis.pnl / rank / replay の結果と Trade テーブルを使う。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from copytrader.web.auth import require_password

st.set_page_config(page_title="Dashboard (Mockup)", layout="wide")
require_password()

st.title("Decision Dashboard")
st.warning(
    "MOCKUP — 全てダミーデータ。各タイルのタイトル（🔗）をクリックで詳細ページに遷移。"
)

rng = np.random.default_rng(42)

TILE_HEIGHT = 220
COMMON_LAYOUT = dict(
    height=TILE_HEIGHT,
    margin=dict(t=10, b=10, l=10, r=10),
    showlegend=False,
    font=dict(size=10),
)


def tile_header(title: str, page_path: str, icon: str = "🔗") -> None:
    """Tile タイトル = 詳細ページへのリンク。"""
    st.page_link(page_path, label=f"**{title}**", icon=icon)


k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("累積 PnL (30d)", "+$12,847", "+$523")
k2.metric("勝率", "58.3%", "+1.2pp")
k3.metric("Watchlist", "12 / 50", "+2")
k4.metric("最大 DD", "-8.4%", "-1.1pp", delta_color="inverse")
k5.metric("USDC 残高", "$8,432", "-$120")
k6.metric("今日 PnL", "+$184", "+2.2%")

st.divider()

row1 = st.columns(3)

with row1[0]:
    with st.container(border=True):
        tile_header("上位ウォレット equity (30d)", "pages/3_Watchlist.py", "👛")
        days = pd.date_range(end=datetime.now(UTC), periods=30, freq="D")
        wallets = [f"0x{rng.integers(0, 16**8):08x}" for _ in range(5)]
        eq_df = pd.DataFrame({
            "date": np.tile(days, 5),
            "wallet": np.repeat(wallets, 30),
            "pnl": np.concatenate([
                np.cumsum(rng.normal(loc=base, scale=80, size=30))
                for base in [25, 18, 12, 8, -3]
            ]),
        })
        fig = px.line(eq_df, x="date", y="pnl", color="wallet")
        fig.update_layout(**COMMON_LAYOUT, xaxis_title="", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True, key="t_equity")

with row1[1]:
    with st.container(border=True):
        tile_header("Drawdown (underwater)", "pages/7_Strategy.py", "📉")
        pnl_series = np.cumsum(rng.normal(loc=15, scale=80, size=90)) + 200
        peak = np.maximum.accumulate(pnl_series)
        dd_pct = (pnl_series - peak) / np.maximum(peak, 1) * 100
        dd_dates = pd.date_range(end=datetime.now(UTC), periods=90, freq="D")
        dd = go.Figure()
        dd.add_trace(go.Scatter(
            x=dd_dates, y=dd_pct,
            fill="tozeroy", mode="lines",
            line=dict(color="#d9534f", width=1.5),
        ))
        dd.add_hline(y=-15, line_dash="dash", line_color="orange")
        dd.update_layout(**COMMON_LAYOUT, xaxis_title="", yaxis_title="%")
        st.plotly_chart(dd, use_container_width=True, key="t_dd")

with row1[2]:
    with st.container(border=True):
        tile_header("Replay ROI heatmap", "pages/7_Strategy.py", "🔥")
        delays = [15, 30, 60, 120, 300, 600]
        sizes = [10, 25, 50, 100, 250, 500]
        roi = rng.normal(loc=2.5, scale=4, size=(len(sizes), len(delays)))
        roi[:, 0] += 3
        roi[:, -2:] -= 4
        hm = go.Figure(data=go.Heatmap(
            z=roi,
            x=[f"{d}s" for d in delays],
            y=[f"${s}" for s in sizes],
            colorscale="RdYlGn", zmid=0, showscale=False,
        ))
        hm.update_layout(**COMMON_LAYOUT)
        st.plotly_chart(hm, use_container_width=True, key="t_replay")

row2 = st.columns(3)

with row2[0]:
    with st.container(border=True):
        tile_header("Top 10 戦略 equity", "pages/7_Strategy.py", "🏆")
        top_n = 6
        dates60 = pd.date_range(end=datetime.now(UTC), periods=60, freq="D")
        palette = px.colors.qualitative.Bold
        top_fig = go.Figure()
        for i in range(top_n):
            base = (top_n - i) * 6
            seed = 100 + i
            sub = np.random.default_rng(seed)
            eq = np.cumsum(sub.normal(loc=base / 60 * 10, scale=40, size=60)) + 1000
            top_fig.add_trace(go.Scatter(
                x=dates60, y=eq, mode="lines",
                line=dict(color=palette[i % len(palette)], width=1.5),
                name=f"#{i + 1}",
            ))
        top_fig.add_hline(y=1000, line_dash="dot", line_color="gray")
        top_fig.update_layout(**COMMON_LAYOUT, xaxis_title="", yaxis_title="")
        st.plotly_chart(top_fig, use_container_width=True, key="t_top10")

with row2[1]:
    with st.container(border=True):
        tile_header("市場 × 戦略 ROI matrix", "pages/7_Strategy.py", "🧪")
        n_m, n_s = 8, 6
        roi_mat = rng.normal(loc=3, scale=7, size=(n_m, n_s))
        roi_mat[2, :] += 5
        roi_mat[:, 0] += 2
        mm = go.Figure(data=go.Heatmap(
            z=roi_mat, colorscale="RdYlGn", zmid=0, showscale=False,
        ))
        mm.update_layout(
            **COMMON_LAYOUT,
            xaxis=dict(showticklabels=False),
            yaxis=dict(showticklabels=False),
        )
        st.plotly_chart(mm, use_container_width=True, key="t_matrix")

with row2[2]:
    with st.container(border=True):
        tile_header("シグナル時間帯ヒートマップ", "pages/0_Status.py", "⏰")
        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        heat = rng.poisson(lam=3, size=(7, 24)).astype(float)
        heat[:, 13:22] *= 2.5
        heat[5:7, :] *= 0.6
        ht = go.Figure(data=go.Heatmap(
            z=heat, x=list(range(24)), y=weekdays,
            colorscale="Blues", showscale=False,
        ))
        ht.update_layout(**COMMON_LAYOUT, xaxis_title="hour (UTC)", yaxis_title="")
        st.plotly_chart(ht, use_container_width=True, key="t_time")

row3 = st.columns(3)

with row3[0]:
    with st.container(border=True):
        tile_header("執行: 今日のドローダウン", "pages/6_Execution.py", "🛑")
        today_dd = 3.2
        max_dd = 8.0
        g = go.Figure(go.Indicator(
            mode="gauge+number",
            value=today_dd,
            number={"suffix": "%", "valueformat": ".1f", "font": {"size": 28}},
            gauge={
                "axis": {"range": [0, max_dd], "tickfont": {"size": 9}},
                "bar": {"color": "#d9534f"},
                "steps": [
                    {"range": [0, max_dd * 0.5], "color": "#e7f6e7"},
                    {"range": [max_dd * 0.5, max_dd * 0.8], "color": "#fff3cd"},
                    {"range": [max_dd * 0.8, max_dd], "color": "#f8d7da"},
                ],
                "threshold": {
                    "line": {"color": "red", "width": 3},
                    "thickness": 0.75, "value": max_dd,
                },
            },
        ))
        g.update_layout(**COMMON_LAYOUT)
        st.plotly_chart(g, use_container_width=True, key="t_gauge")

with row3[1]:
    with st.container(border=True):
        tile_header("Latency 分布 (signal→fill)", "pages/6_Execution.py", "⚡")
        latencies = rng.normal(loc=850, scale=280, size=200).clip(min=100)
        lt = go.Figure(data=go.Histogram(
            x=latencies, nbinsx=25, marker_color="#2c7fb8",
        ))
        lt.add_vline(x=np.median(latencies), line_dash="dash",
                     line_color="orange",
                     annotation_text=f"p50: {int(np.median(latencies))}ms",
                     annotation_position="top right",
                     annotation_font_size=9)
        lt.update_layout(**COMMON_LAYOUT, xaxis_title="ms", yaxis_title="")
        st.plotly_chart(lt, use_container_width=True, key="t_latency")

with row3[2]:
    with st.container(border=True):
        tile_header("オープンポジション exposure", "pages/6_Execution.py", "💰")
        pos_labels = ["米大統領", "FRB", "BTC>$150k", "AI", "G7", "WC", "投票率"]
        pos_sizes = [320, 250, 480, 410, 200, 180, 1370]
        pos_pnl = [22.8, 13.6, 80.0, 12.0, -2.8, -30.0, 90.2]
        colors = ["#2ca02c" if p >= 0 else "#d62728" for p in pos_pnl]
        bb = go.Figure(go.Bar(
            x=pos_sizes, y=pos_labels, orientation="h",
            marker_color=colors,
            text=[f"${s} ({p:+.0f})" for s, p in zip(pos_sizes, pos_pnl, strict=False)],
            textposition="outside", textfont=dict(size=9),
        ))
        bb.update_layout(**COMMON_LAYOUT,
                         xaxis=dict(visible=False),
                         yaxis=dict(tickfont=dict(size=9)))
        st.plotly_chart(bb, use_container_width=True, key="t_pos")

row4 = st.columns(3)

with row4[0]:
    with st.container(border=True):
        tile_header("Watchlist Top5 (30d PnL)", "pages/3_Watchlist.py", "📋")
        leaders = pd.DataFrame({
            "wallet": [f"0x{rng.integers(0, 16**8):08x}" for _ in range(5)],
            "PnL": sorted([int(rng.normal(2000, 1200)) for _ in range(5)],
                          reverse=True),
            "trend": [list(np.cumsum(rng.normal(0, 1, 20))) for _ in range(5)],
        })
        st.dataframe(
            leaders,
            use_container_width=True, hide_index=True,
            column_config={
                "PnL": st.column_config.NumberColumn(format="$%d", width="small"),
                "trend": st.column_config.LineChartColumn(width="medium"),
            },
            height=220,
        )

with row4[1]:
    with st.container(border=True):
        tile_header("受信シグナル直近 5 件", "pages/6_Execution.py", "📨")
        now = datetime.now(UTC)
        sig = pd.DataFrame({
            "時刻": [(now - timedelta(seconds=int(s))).strftime("%H:%M:%S")
                     for s in sorted(rng.integers(5, 900, 5))],
            "wallet": [f"0x{rng.integers(0, 16**8):08x}" for _ in range(5)],
            "side": rng.choice(["BUY", "SELL"], 5).tolist(),
            "状態": rng.choice(["✅", "⏳", "❌", "⏭"], 5,
                               p=[0.5, 0.2, 0.1, 0.2]).tolist(),
        })
        st.dataframe(sig, use_container_width=True, hide_index=True, height=220)

with row4[2]:
    with st.container(border=True):
        tile_header("Indexer ステータス", "pages/0_Status.py", "📡")
        cursor_dates = pd.date_range(end=datetime.now(UTC), periods=24, freq="h")
        cursor_lag = rng.uniform(5, 60, 24)
        cursor_lag[-3:] *= 2.5
        cl = go.Figure()
        cl.add_trace(go.Scatter(
            x=cursor_dates, y=cursor_lag, mode="lines+markers",
            line=dict(color="#5b9bd5", width=1.5),
            marker=dict(size=4),
        ))
        cl.add_hline(y=120, line_dash="dash", line_color="red",
                     annotation_text="alert: 120s",
                     annotation_font_size=9)
        cl.update_layout(**COMMON_LAYOUT, xaxis_title="", yaxis_title="lag (s)")
        st.plotly_chart(cl, use_container_width=True, key="t_indexer")

st.divider()
st.caption(
    "本実装の差し替えポイント: 各タイルは現在ダミーデータ。"
    "詳細ページ側で実データ表示を実装済み（または実装予定）、"
    "Dashboard 側は同じデータソースの mini view として薄く描画する。"
)
