"""Strategy Lab (MOCKUP).

マーケット × ストラテジー × シミュレーション結果を 1 画面で俯瞰。

本実装では:
  * マーケット: Polymarket Gamma API + Trade テーブル集計
  * ストラテジー: settings テーブルのプリセット定義
  * シミュレーション: analysis.replay の grid 実行結果 (job_results)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from copytrader.web.auth import require_password

st.set_page_config(page_title="Strategy Lab (Mockup)", layout="wide")
require_password()

st.title("Strategy Lab")
st.warning(
    "MOCKUP — 全てダミーデータ。"
    "本実装では Gamma API + analysis.replay の grid 結果に置き換えます。"
)

rng = np.random.default_rng(2026)

MARKETS = [
    "米大統領 2028",
    "FRB 6月 利下げ",
    "BTC > $150k EOY",
    "AI バブル崩壊 2026",
    "G7 開催成功",
    "WC 優勝 — Brazil",
    "投票率 60%+",
    "OpenAI IPO 2027",
    "EU 関税合意",
    "為替 140円割れ",
]

STRATEGIES = [
    {"name": "Top10-Copy / 30s / $50",  "delay": 30,  "size": 50,  "top_n": 10},
    {"name": "Top10-Copy / 60s / $50",  "delay": 60,  "size": 50,  "top_n": 10},
    {"name": "Top5-Copy / 30s / $100",  "delay": 30,  "size": 100, "top_n": 5},
    {"name": "Top20-Copy / 120s / $25", "delay": 120, "size": 25,  "top_n": 20},
    {"name": "Top5-Copy / 15s / $200",  "delay": 15,  "size": 200, "top_n": 5},
    {"name": "Contrarian-Bottom5 / 60s / $50", "delay": 60, "size": 50,  "top_n": -5},
    {"name": "Whale-only (>$10k) / 30s",   "delay": 30,  "size": 100, "top_n": 99},
]

n_m = len(MARKETS)
n_s = len(STRATEGIES)

roi_matrix = rng.normal(loc=4.0, scale=8.0, size=(n_m, n_s))
roi_matrix[:, 0] += 3
roi_matrix[:, -2] -= 5
roi_matrix[2, :] += 6
roi_matrix[7, :] -= 4

sharpe_matrix = roi_matrix / (4 + rng.uniform(0, 3, size=roi_matrix.shape))
trades_matrix = rng.integers(20, 400, size=roi_matrix.shape)
dd_matrix = -np.abs(rng.normal(loc=8, scale=4, size=roi_matrix.shape))

best_idx = np.unravel_index(np.argmax(roi_matrix), roi_matrix.shape)
worst_idx = np.unravel_index(np.argmin(roi_matrix), roi_matrix.shape)
total_sims = n_m * n_s
pos_sims = int((roi_matrix > 0).sum())

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("シミュ総数", f"{total_sims}", f"市場 {n_m} × 戦略 {n_s}")
k2.metric("黒字シナリオ", f"{pos_sims}", f"{pos_sims / total_sims * 100:.0f}%")
k3.metric("ベスト ROI",
          f"{roi_matrix[best_idx]:+.1f}%",
          f"{MARKETS[best_idx[0]]} × {STRATEGIES[best_idx[1]]['name'].split(' /')[0]}")
k4.metric("ワースト ROI",
          f"{roi_matrix[worst_idx]:+.1f}%",
          f"{MARKETS[worst_idx[0]]}",
          delta_color="inverse")
k5.metric("中央値 ROI", f"{np.median(roi_matrix):+.1f}%", "median across sims")

st.divider()

market_col, strat_col = st.columns([1.2, 1])

with market_col:
    st.subheader("マーケット一覧")
    st.caption("Polymarket の対象市場。volume / 流動性 / 解決日が判断材料。")
    mkt_df = pd.DataFrame({
        "market": MARKETS,
        "volume_24h": rng.integers(10_000, 800_000, n_m).tolist(),
        "OI": rng.integers(50_000, 3_000_000, n_m).tolist(),
        "current_price": [round(float(rng.uniform(0.1, 0.9)), 3) for _ in range(n_m)],
        "days_to_resolve": rng.integers(3, 365, n_m).tolist(),
        "sparkline": [list(np.clip(0.5 + np.cumsum(rng.normal(0, 0.02, 30)), 0.05, 0.95))
                      for _ in range(n_m)],
        "best_strategy_ROI": [round(float(roi_matrix[i].max()), 2) for i in range(n_m)],
    })
    mkt_df = mkt_df.sort_values("volume_24h", ascending=False).reset_index(drop=True)
    st.dataframe(
        mkt_df,
        use_container_width=True,
        hide_index=True,
        height=380,
        column_config={
            "volume_24h": st.column_config.NumberColumn("24h vol", format="$%d"),
            "OI": st.column_config.NumberColumn("Open Interest", format="$%d"),
            "current_price": st.column_config.ProgressColumn(
                "price", min_value=0.0, max_value=1.0, format="%.3f",
            ),
            "days_to_resolve": st.column_config.NumberColumn("resolve まで", format="%d日"),
            "sparkline": st.column_config.LineChartColumn("30d price", y_min=0, y_max=1),
            "best_strategy_ROI": st.column_config.NumberColumn(
                "best ROI", format="%+.1f%%",
            ),
        },
    )

with strat_col:
    st.subheader("ストラテジー定義")
    st.caption("プリセット。各戦略は全マーケットに対して replay 済み。")
    for s in STRATEGIES:
        with st.container(border=True):
            row1 = st.columns([3, 1])
            row1[0].markdown(f"**{s['name']}**")
            n_winners = int((roi_matrix[:, STRATEGIES.index(s)] > 0).sum())
            row1[1].markdown(f"黒字: **{n_winners}/{n_m}**")
            row2 = st.columns(3)
            row2[0].caption(f"delay: {s['delay']}s")
            row2[1].caption(f"size: ${s['size']}")
            row2[2].caption(
                "top: " + (f"{s['top_n']}"
                           if s["top_n"] > 0 else f"bottom {abs(s['top_n'])}")
            )

st.divider()

st.subheader("シミュレーション一覧マトリクス")
metric_pick = st.radio(
    "色付け指標",
    ["ROI %", "Sharpe", "trades 数", "最大 DD %"],
    horizontal=True,
    label_visibility="collapsed",
)
if metric_pick == "ROI %":
    z, colorscale, zmid, fmt = roi_matrix, "RdYlGn", 0, "{:+.1f}%"
elif metric_pick == "Sharpe":
    z, colorscale, zmid, fmt = sharpe_matrix, "RdYlGn", 0, "{:+.2f}"
elif metric_pick == "trades 数":
    z, colorscale, zmid, fmt = trades_matrix, "Blues", None, "{:.0f}"
else:
    z, colorscale, zmid, fmt = dd_matrix, "Reds_r", None, "{:.1f}%"

strat_labels = [s["name"] for s in STRATEGIES]
heatmap = go.Figure(data=go.Heatmap(
    z=z,
    x=strat_labels,
    y=MARKETS,
    colorscale=colorscale,
    zmid=zmid,
    text=[[fmt.format(v) for v in row] for row in z],
    texttemplate="%{text}",
    hovertemplate=("market: %{y}<br>strategy: %{x}<br>" + metric_pick + ": %{z}<extra></extra>"),
))
heatmap.update_layout(
    height=430,
    margin=dict(t=10, b=10, l=10, r=10),
    xaxis=dict(tickangle=-25),
)
st.plotly_chart(heatmap, use_container_width=True)

st.subheader("ストラテジー比較 — ROI × Sharpe × 取引数")
scatter_rows = []
for mi, m in enumerate(MARKETS):
    for si, s in enumerate(STRATEGIES):
        scatter_rows.append({
            "market": m,
            "strategy": s["name"],
            "ROI %": roi_matrix[mi, si],
            "Sharpe": sharpe_matrix[mi, si],
            "trades": int(trades_matrix[mi, si]),
        })
scatter_df = pd.DataFrame(scatter_rows)
scatter = px.scatter(
    scatter_df,
    x="ROI %", y="Sharpe",
    size="trades", color="strategy",
    hover_data=["market", "trades"],
    size_max=28,
)
scatter.add_hline(y=0, line_dash="dot", line_color="gray")
scatter.add_vline(x=0, line_dash="dot", line_color="gray")
scatter.update_layout(height=420, margin=dict(t=20, b=20, l=10, r=10))
st.plotly_chart(scatter, use_container_width=True)

st.divider()

st.subheader("シミュレーション ドリルダウン")
st.caption("market × strategy を選ぶと equity curve と詳細統計を表示。")
d1, d2 = st.columns(2)
sel_market = d1.selectbox("市場", MARKETS, index=int(best_idx[0]))
sel_strat = d2.selectbox(
    "戦略", strat_labels, index=int(best_idx[1]),
)
mi = MARKETS.index(sel_market)
si = strat_labels.index(sel_strat)

dc1, dc2, dc3, dc4 = st.columns(4)
dc1.metric("ROI", f"{roi_matrix[mi, si]:+.2f}%")
dc2.metric("Sharpe", f"{sharpe_matrix[mi, si]:+.2f}")
dc3.metric("trades", f"{trades_matrix[mi, si]}")
dc4.metric("max DD", f"{dd_matrix[mi, si]:.2f}%")

eq_points = 60
seed = (mi * 1000 + si) % (2**31 - 1)
sub_rng = np.random.default_rng(seed)
drift = roi_matrix[mi, si] / 100 / eq_points * 1000
noise = sub_rng.normal(0, max(80, abs(roi_matrix[mi, si]) * 8), size=eq_points)
equity = np.cumsum(np.full(eq_points, drift * 10) + noise) + 1000
dates = pd.date_range(end=pd.Timestamp.utcnow(), periods=eq_points, freq="D")
eq_fig = go.Figure()
eq_fig.add_trace(go.Scatter(
    x=dates, y=equity, mode="lines",
    line=dict(color="#2c7fb8", width=2),
    fill="tozeroy", fillcolor="rgba(44,127,184,0.1)",
    name="equity",
))
eq_fig.add_hline(y=1000, line_dash="dot", line_color="gray",
                 annotation_text="initial $1,000")
eq_fig.update_layout(
    height=320, margin=dict(t=20, b=20, l=10, r=10),
    yaxis_title="USDC", xaxis_title="",
    title=f"{sel_market} × {sel_strat} — equity curve",
)
st.plotly_chart(eq_fig, use_container_width=True)

st.divider()
st.caption(
    "本実装の差し替えポイント: "
    "(1) MARKETS → Gamma API + Trade.token_id 集計 / "
    "(2) STRATEGIES → settings.strategy_presets テーブル / "
    "(3) roi_matrix → analysis.replay を market × strategy grid で実行し job_results に保存 / "
    "(4) drill-down equity → 該当 simulation の per-trade PnL 累積"
)
