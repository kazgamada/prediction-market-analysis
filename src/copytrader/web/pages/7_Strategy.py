"""Strategy Lab (MOCKUP) — single viewport layout."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from copytrader.web.auth import require_password

st.set_page_config(page_title="Strategy", layout="wide",
                   initial_sidebar_state="collapsed")
require_password()

st.markdown("""
<style>
.block-container { padding-top: 0.6rem !important; padding-bottom: 0.4rem !important; max-width: 100% !important; }
[data-testid="stMetric"] { padding: 0.1rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.7rem !important; }
[data-testid="stMetricValue"] { font-size: 1.0rem !important; }
[data-testid="stMetricDelta"] { font-size: 0.65rem !important; }
h1, h3, h4, h5 { padding: 0 !important; margin: 0.2rem 0 !important; }
h1 { font-size: 1.2rem !important; }
h5 { font-size: 0.85rem !important; }
hr { margin: 0.3rem 0 !important; }
.stDataFrame { font-size: 0.72rem !important; }
[data-testid="stVerticalBlockBorderWrapper"] { padding: 0.3rem 0.5rem !important; }
.stRadio > div { gap: 0.5rem !important; }
.stRadio label { font-size: 0.75rem !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("# Strategy Lab　<small style='font-size:0.7rem;color:#888;'>MOCKUP — market × strategy × simulation</small>",
            unsafe_allow_html=True)

rng = np.random.default_rng(2026)

MARKETS = ["米大統領 2028", "FRB 6月 利下げ", "BTC>$150k EOY", "AI バブル崩壊",
           "G7 開催", "WC — Brazil", "投票率 60%+", "OpenAI IPO", "EU 関税",
           "為替 140 割れ"]
STRATEGIES = [
    {"name": "Top10/30s/$50", "delay": 30, "size": 50, "top_n": 10},
    {"name": "Top10/60s/$50", "delay": 60, "size": 50, "top_n": 10},
    {"name": "Top5/30s/$100", "delay": 30, "size": 100, "top_n": 5},
    {"name": "Top20/120s/$25", "delay": 120, "size": 25, "top_n": 20},
    {"name": "Top5/15s/$200", "delay": 15, "size": 200, "top_n": 5},
    {"name": "Contra-B5/60s", "delay": 60, "size": 50, "top_n": -5},
    {"name": "Whale>$10k/30s", "delay": 30, "size": 100, "top_n": 99},
]
n_m, n_s = len(MARKETS), len(STRATEGIES)
roi = rng.normal(4, 8, (n_m, n_s))
roi[:, 0] += 3; roi[:, -2] -= 5; roi[2, :] += 6; roi[7, :] -= 4
sharpe = roi / (4 + rng.uniform(0, 3, (n_m, n_s)))
trades = rng.integers(20, 400, (n_m, n_s))
strat_labels = [s["name"] for s in STRATEGIES]

best = np.unravel_index(np.argmax(roi), roi.shape)
worst = np.unravel_index(np.argmin(roi), roi.shape)
pos_sims = int((roi > 0).sum())

k = st.columns(5)
k[0].metric("sim 総数", f"{n_m * n_s}", f"{n_m}×{n_s}")
k[1].metric("黒字", f"{pos_sims}", f"{pos_sims / (n_m * n_s) * 100:.0f}%")
k[2].metric("ベスト", f"{roi[best]:+.1f}%", MARKETS[best[0]][:10])
k[3].metric("ワースト", f"{roi[worst]:+.1f}%", MARKETS[worst[0]][:10],
            delta_color="inverse")
k[4].metric("中央値", f"{np.median(roi):+.1f}%")

r1 = st.columns([1, 1.2])

with r1[0], st.container(border=True):
    st.markdown("##### マーケット一覧")
    mkt = pd.DataFrame({
        "market": MARKETS,
        "24h vol": rng.integers(10_000, 800_000, n_m).tolist(),
        "price": [round(float(rng.uniform(0.1, 0.9)), 3) for _ in range(n_m)],
        "resolve": rng.integers(3, 365, n_m).tolist(),
        "best ROI": [round(float(roi[i].max()), 1) for i in range(n_m)],
        "trend": [list(np.clip(0.5 + np.cumsum(rng.normal(0, 0.02, 20)), 0.05, 0.95))
                  for _ in range(n_m)],
    })
    mkt = mkt.sort_values("24h vol", ascending=False).reset_index(drop=True)
    st.dataframe(mkt, use_container_width=True, hide_index=True, height=300,
                 column_config={
                     "24h vol": st.column_config.NumberColumn(format="$%d"),
                     "price": st.column_config.ProgressColumn(
                         min_value=0.0, max_value=1.0, format="%.2f"),
                     "resolve": st.column_config.NumberColumn(format="%d日"),
                     "best ROI": st.column_config.NumberColumn(format="%+.1f%%"),
                     "trend": st.column_config.LineChartColumn(y_min=0, y_max=1),
                 })

with r1[1], st.container(border=True):
    metric_pick = st.radio("色付け",
                           ["ROI %", "Sharpe", "trades"],
                           horizontal=True, label_visibility="collapsed",
                           key="metric_pick")
    if metric_pick == "ROI %":
        z, cs, zm, fmt = roi, "RdYlGn", 0, "{:+.1f}"
    elif metric_pick == "Sharpe":
        z, cs, zm, fmt = sharpe, "RdYlGn", 0, "{:+.2f}"
    else:
        z, cs, zm, fmt = trades, "Blues", None, "{:.0f}"
    hm = go.Figure(data=go.Heatmap(
        z=z, x=strat_labels, y=MARKETS,
        colorscale=cs, zmid=zm, showscale=False,
        text=[[fmt.format(v) for v in r] for r in z], texttemplate="%{text}",
        hovertemplate="%{y} × %{x}<br>%{z}<extra></extra>",
    ))
    hm.update_layout(height=280, margin=dict(t=5, b=5, l=5, r=5),
                     xaxis=dict(tickangle=-30, tickfont=dict(size=9)),
                     yaxis=dict(tickfont=dict(size=9)),
                     font=dict(size=8))
    st.plotly_chart(hm, use_container_width=True, key="t_hm")

r2 = st.columns([1, 1])

with r2[0], st.container(border=True):
    st.markdown("##### ROI × Sharpe × trades")
    rows = []
    for mi, m in enumerate(MARKETS):
        for si, s in enumerate(STRATEGIES):
            rows.append({"market": m, "strategy": s["name"],
                         "ROI %": roi[mi, si], "Sharpe": sharpe[mi, si],
                         "trades": int(trades[mi, si])})
    sdf = pd.DataFrame(rows)
    sc = px.scatter(sdf, x="ROI %", y="Sharpe", size="trades", color="strategy",
                    hover_data=["market"], size_max=18)
    sc.add_hline(y=0, line_dash="dot", line_color="gray")
    sc.add_vline(x=0, line_dash="dot", line_color="gray")
    sc.update_layout(height=240, margin=dict(t=5, b=5, l=5, r=5),
                     showlegend=False, font=dict(size=9))
    st.plotly_chart(sc, use_container_width=True, key="t_sc")

with r2[1], st.container(border=True):
    sort_pick = st.radio("並び替え",
                         ["ROI %", "Sharpe", "ROI×Sharpe"],
                         horizontal=True, label_visibility="collapsed",
                         key="sort_pick")
    combos = []
    for mi, m in enumerate(MARKETS):
        for si, s in enumerate(STRATEGIES):
            combos.append({"market_idx": mi, "strat_idx": si,
                           "market": m, "strategy": strat_labels[si],
                           "ROI %": float(roi[mi, si]),
                           "Sharpe": float(sharpe[mi, si])})
    cdf = pd.DataFrame(combos)
    if sort_pick == "ROI %":
        cdf["_s"] = cdf["ROI %"]
    elif sort_pick == "Sharpe":
        cdf["_s"] = cdf["Sharpe"]
    else:
        cdf["_s"] = cdf["ROI %"] * cdf["Sharpe"].clip(lower=0)
    top10 = cdf.sort_values("_s", ascending=False).head(10).reset_index(drop=True)
    dates60 = pd.date_range(end=pd.Timestamp.utcnow(), periods=60, freq="D")
    palette = px.colors.qualitative.Bold + px.colors.qualitative.Set2
    eq = go.Figure()
    for i, row in top10.iterrows():
        mi_, si_ = int(row["market_idx"]), int(row["strat_idx"])
        sub = np.random.default_rng((mi_ * 1000 + si_) % (2**31 - 1))
        drift = row["ROI %"] / 100 / 60 * 1000
        noise = sub.normal(0, max(60, abs(row["ROI %"]) * 6), size=60)
        equity = np.cumsum(np.full(60, drift * 10) + noise) + 1000
        eq.add_trace(go.Scatter(x=dates60, y=equity, mode="lines",
                                line=dict(color=palette[i % len(palette)], width=1.5),
                                name=f"#{int(i + 1)} {row['market'][:6]}",
                                hovertemplate=f"{row['market']}<br>{row['strategy']}<br>$%{{y:.0f}}<extra></extra>"))
    eq.add_hline(y=1000, line_dash="dot", line_color="gray")
    eq.update_layout(height=240, margin=dict(t=5, b=5, l=5, r=5),
                     font=dict(size=8),
                     legend=dict(font=dict(size=7), x=1.01, y=1))
    st.plotly_chart(eq, use_container_width=True, key="t_eq")
