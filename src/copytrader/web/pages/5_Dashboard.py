"""Decision Dashboard (MOCKUP).

意思決定をする人間に対する画面のモック。DB は触らず全てダミーデータ。
本実装では analysis.pnl / rank / replay の結果と Trade テーブルを使う。
"""
from __future__ import annotations

from datetime import UTC, datetime

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
    "MOCKUP — このページは全てダミーデータです。"
    "本実装では analysis モジュールと Trade テーブルからリアルタイムに描画します。"
)

rng = np.random.default_rng(42)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("シミュ累積 PnL (30d)", "+$12,847", "+$523 (24h)")
c2.metric("勝率", "58.3%", "+1.2pp")
c3.metric("アクティブ Watchlist", "12 / 50", "+2")
c4.metric("最大 DD (30d)", "-8.4%", "-1.1pp", delta_color="inverse")
c5.metric("Kill Switch", "Armed", "OK")

st.divider()

st.subheader("上位ウォレット equity curve (30d)")
st.caption("候補ウォレットの累積 PnL を重ね描き。水平化したら劣化のサイン。")
days = pd.date_range(end=datetime.now(UTC), periods=30, freq="D")
wallets = [f"0x{rng.integers(0, 16**8):08x}…" for _ in range(5)]
eq_df = pd.DataFrame({
    "date": np.tile(days, 5),
    "wallet": np.repeat(wallets, 30),
    "pnl": np.concatenate([
        np.cumsum(rng.normal(loc=base, scale=80, size=30))
        for base in [25, 18, 12, 8, -3]
    ]),
})
fig = px.line(
    eq_df, x="date", y="pnl", color="wallet",
    labels={"pnl": "Cumulative PnL (USDC)", "date": ""},
)
fig.update_layout(height=320, margin=dict(t=20, b=20, l=10, r=10))
st.plotly_chart(fig, use_container_width=True)

col_l, col_r = st.columns(2)

with col_l:
    st.subheader("Replay ROI ヒートマップ")
    st.caption("delay (秒) × copy size (USDC) の grid。緑が黒字スイートスポット。")
    delays = [15, 30, 60, 120, 300, 600]
    sizes = [10, 25, 50, 100, 250, 500]
    roi = rng.normal(loc=2.5, scale=4, size=(len(sizes), len(delays)))
    roi[:, 0] += 3
    roi[:, -2:] -= 4
    hm = go.Figure(data=go.Heatmap(
        z=roi,
        x=[f"{d}s" for d in delays],
        y=[f"${s}" for s in sizes],
        colorscale="RdYlGn",
        zmid=0,
        text=[[f"{v:+.1f}%" for v in row] for row in roi],
        texttemplate="%{text}",
        showscale=True,
    ))
    hm.update_layout(
        height=360, margin=dict(t=20, b=20, l=10, r=10),
        xaxis_title="delay", yaxis_title="copy size",
    )
    st.plotly_chart(hm, use_container_width=True)

with col_r:
    st.subheader("Drawdown (underwater)")
    st.caption("過去ピークからの落ち込み %。許容ラインを超えたら kill switch 候補。")
    pnl_series = np.cumsum(rng.normal(loc=15, scale=80, size=90))
    pnl_series += 200
    peak = np.maximum.accumulate(pnl_series)
    dd_pct = (pnl_series - peak) / np.maximum(peak, 1) * 100
    dd_df = pd.DataFrame({
        "date": pd.date_range(end=datetime.now(UTC), periods=90, freq="D"),
        "drawdown_pct": dd_pct,
    })
    dd_fig = go.Figure()
    dd_fig.add_trace(go.Scatter(
        x=dd_df["date"], y=dd_df["drawdown_pct"],
        fill="tozeroy", mode="lines", line=dict(color="#d9534f"),
        name="Drawdown %",
    ))
    dd_fig.add_hline(
        y=-15, line_dash="dash", line_color="orange",
        annotation_text="許容 DD: -15%",
    )
    dd_fig.update_layout(
        height=360, margin=dict(t=20, b=20, l=10, r=10),
        yaxis_title="%",
    )
    st.plotly_chart(dd_fig, use_container_width=True)

st.subheader("Watchlist leaderboard")
st.caption("trend カラムは直近 30 日の equity スパークライン。")
leaders = pd.DataFrame({
    "address": [
        f"0x{rng.integers(0, 16**8):08x}…{rng.integers(0, 16**4):04x}"
        for _ in range(10)
    ],
    "30d PnL": [int(rng.normal(2000, 1200)) for _ in range(10)],
    "win_rate": [round(float(rng.uniform(0.45, 0.72)), 3) for _ in range(10)],
    "trades": [int(rng.integers(30, 400)) for _ in range(10)],
    "volume": [int(rng.uniform(5000, 80000)) for _ in range(10)],
    "trend": [list(np.cumsum(rng.normal(0, 1, 30))) for _ in range(10)],
    "status": rng.choice(
        ["active", "cooling", "paused"], 10, p=[0.7, 0.2, 0.1],
    ).tolist(),
})
leaders = leaders.sort_values("30d PnL", ascending=False).reset_index(drop=True)
st.dataframe(
    leaders,
    use_container_width=True,
    column_config={
        "trend": st.column_config.LineChartColumn("30d trend", width="medium"),
        "30d PnL": st.column_config.NumberColumn(format="$%d"),
        "volume": st.column_config.NumberColumn(format="$%d"),
        "win_rate": st.column_config.NumberColumn("win rate", format="%.2f"),
    },
    hide_index=True,
)

st.subheader("シグナル時間帯ヒートマップ (UTC)")
st.caption("いつ smart money が動くか。執行ロボの稼働時間判断に。")
hours = list(range(24))
weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
heat = rng.poisson(lam=3, size=(7, 24)).astype(float)
heat[:, 13:22] *= 2.5
heat[5:7, :] *= 0.6
hm2 = go.Figure(data=go.Heatmap(
    z=heat, x=hours, y=weekdays, colorscale="Blues",
))
hm2.update_layout(
    height=260, margin=dict(t=20, b=20, l=10, r=10),
    xaxis_title="hour (UTC)",
)
st.plotly_chart(hm2, use_container_width=True)

st.divider()
st.caption(
    "本実装で差し替える箇所: "
    "equity → `compute_wallet_pnl` の時系列展開 / "
    "heatmap → `replay.run` を grid で / "
    "leaderboard → `rank_wallets` / "
    "時間帯 → Trade.ts の集計"
)
