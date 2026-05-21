"""Rollout Console (MOCKUP) — single viewport layout."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from copytrader.web.auth import require_password

st.set_page_config(page_title="Rollout", layout="wide",
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
.stButton button { padding: 0.2rem 0.5rem !important; font-size: 0.78rem !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("# Rollout Console　<small style='font-size:0.7rem;color:#888;'>MOCKUP — 段階的ロールアウト</small>",
            unsafe_allow_html=True)

PHASES = [
    {"id": "A", "name": "Paper", "duration": 28, "size": 0, "cap": 0,
     "color": "#9aa0a6"},
    {"id": "B", "name": "Micro", "duration": 28, "size": 10, "cap": 100,
     "color": "#5b9bd5"},
    {"id": "C", "name": "Small", "duration": 56, "size": 50, "cap": 500,
     "color": "#2c7fb8"},
    {"id": "D", "name": "Scale", "duration": 9999, "size": 250, "cap": 2500,
     "color": "#1a5490"},
]
CUR = 1
DAY = 18

cur = PHASES[CUR]

h = st.columns([1.5, 1, 1, 1, 1, 1.2])
h[0].markdown(
    f"### Phase **{cur['id']}** — {cur['name']}",
    unsafe_allow_html=True,
)
h[1].metric("経過", f"{DAY}/{cur['duration']}日")
h[2].metric("1 trade", f"${cur['size']}")
h[3].metric("日次上限", f"${cur['cap']}")
h[4].metric("phase 累計", "+$72.40", "+$8.20")
h[5].metric("backtest 乖離", "12%", "+2pp", delta_color="inverse")

stepper = go.Figure()
n = len(PHASES)
for i, p in enumerate(PHASES):
    if i < CUR:
        color, opacity = "#2ca02c", 1.0
        suf = " ✓"
    elif i == CUR:
        color, opacity = p["color"], 1.0
        suf = " ●"
    else:
        color, opacity = "#cccccc", 0.5
        suf = ""
    stepper.add_shape(type="rect", x0=i + 0.05, x1=i + 0.95, y0=0.35, y1=0.85,
                      fillcolor=color, opacity=opacity, line=dict(width=0))
    stepper.add_annotation(
        x=i + 0.5, y=0.6, showarrow=False,
        text=f"<b>{p['id']}{suf}</b> {p['name']}　"
             f"<span style='font-size:9px;color:#eee'>{p['duration']}d / ${p['size']}</span>",
        font=dict(size=11, color="white" if opacity > 0.7 else "#666"))
    if i < n - 1:
        stepper.add_annotation(x=i + 1, y=0.6, showarrow=False, text="→",
                               font=dict(size=16, color="#888"))
prog = DAY / max(1, PHASES[CUR]["duration"])
stepper.add_shape(type="rect",
                  x0=CUR + 0.05, x1=CUR + 0.05 + 0.9 * min(prog, 1.0),
                  y0=0.27, y1=0.32,
                  fillcolor="#ff8c00", line=dict(width=0))
stepper.update_layout(height=80, margin=dict(t=0, b=0, l=5, r=5),
                      xaxis=dict(visible=False, range=[0, n]),
                      yaxis=dict(visible=False, range=[0, 1]),
                      plot_bgcolor="white")
st.plotly_chart(stepper, use_container_width=True, key="stepper")

r1 = st.columns([1, 1, 1])

with r1[0], st.container(border=True):
    st.markdown("##### 昇格条件")
    promo = [
        {"c": "経過 ≥ 28d", "ok": False, "now": f"{DAY}日"},
        {"c": "累積 ROI ≥ +3%", "ok": True, "now": "+4.2%"},
        {"c": "最大 DD ≤ 8%", "ok": True, "now": "-5.1%"},
        {"c": "勝率 ≥ 52%", "ok": True, "now": "56.8%"},
        {"c": "backtest 乖離 ≤ 20%", "ok": True, "now": "12%"},
        {"c": "Latency p95 ≤ 3000ms", "ok": False, "now": "3,420ms"},
        {"c": "kill switch test 合格", "ok": True, "now": "3 日前"},
    ]
    pdf = pd.DataFrame([
        {"条件": x["c"], "現在": x["now"], " ": "✅" if x["ok"] else "⏳"}
        for x in promo
    ])
    st.dataframe(pdf, use_container_width=True, hide_index=True, height=240)
    passed = sum(1 for x in promo if x["ok"])
    st.progress(passed / len(promo),
                text=f"{passed} / {len(promo)} クリア")

with r1[1], st.container(border=True):
    st.markdown("##### 停止条件")
    halt = [
        {"c": "日次 PnL < -5%", "t": False, "now": "+0.9%"},
        {"c": "7d PnL < -8%", "t": False, "now": "+2.1%"},
        {"c": "連敗 ≥ 5", "t": False, "now": "2"},
        {"c": "単一 market > 25%", "t": True, "now": "27%"},
        {"c": "indexer lag > 120s", "t": False, "now": "18s"},
        {"c": "USDC < $500", "t": False, "now": "$8,432"},
        {"c": "MATIC < 1.0", "t": False, "now": "12.4"},
    ]
    hdf = pd.DataFrame([
        {"条件": x["c"], "現在": x["now"], " ": "🛑" if x["t"] else "🟢"}
        for x in halt
    ])
    st.dataframe(hdf, use_container_width=True, hide_index=True, height=240)
    tripped = sum(1 for x in halt if x["t"])
    if tripped > 0:
        st.error(f"{tripped} 件ヒット — 要対処")
    else:
        st.success("全クリア")

with r1[2], st.container(border=True):
    st.markdown("##### Phase 内 daily")
    rng = np.random.default_rng(33)
    days = pd.date_range(end=pd.Timestamp.utcnow(), periods=DAY, freq="D")
    daily = rng.normal(4, 12, DAY)
    daily[7:10] = -np.abs(rng.normal(15, 5, 3))
    cum = np.cumsum(daily)
    bt_pred = rng.normal(5, 8, DAY)
    bt_cum = np.cumsum(bt_pred)
    f = go.Figure()
    f.add_trace(go.Bar(x=days, y=daily,
                       marker_color=["#2ca02c" if v >= 0 else "#d62728" for v in daily],
                       name="日次", opacity=0.5, yaxis="y2"))
    f.add_trace(go.Scatter(x=days, y=bt_cum, mode="lines",
                           line=dict(color="#888", width=1.5, dash="dash"),
                           name="backtest"))
    f.add_trace(go.Scatter(x=days, y=cum, mode="lines",
                           line=dict(color="#2c7fb8", width=2),
                           name="実績"))
    f.update_layout(
        height=260, margin=dict(t=5, b=5, l=5, r=5),
        font=dict(size=8),
        legend=dict(font=dict(size=8), x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.7)"),
        yaxis=dict(title="累積", titlefont=dict(size=8)),
        yaxis2=dict(overlaying="y", side="right", showgrid=False,
                    title="日次", titlefont=dict(size=8)),
    )
    st.plotly_chart(f, use_container_width=True, key="daily")

a = st.columns(4)
can_promote = passed == len(promo) and tripped == 0
with a[0]:
    if can_promote:
        st.success("昇格可能")
    else:
        st.info("条件未達")
    st.button(f"→ Phase {PHASES[CUR + 1]['id']} 昇格",
              type="primary", use_container_width=True, disabled=not can_promote)
with a[1]:
    st.info("継続")
    st.button("現フェーズ継続", use_container_width=True)
with a[2]:
    st.warning("降格")
    st.button(f"← Phase {PHASES[CUR - 1]['id']} 降格",
              use_container_width=True)
with a[3]:
    st.error("緊急停止")
    confirm = st.checkbox("HALT 確認", key="halt_confirm")
    st.button("🛑 全自動発注を停止", use_container_width=True,
              disabled=not confirm)
