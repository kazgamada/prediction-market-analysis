"""Rollout Console (MOCKUP).

段階的ロールアウト (A: Paper → B: Micro → C: Small → D: Scale) を 1 ページで管理。
各フェーズの昇格条件 / 停止条件 / 現在値を可視化し、人間が「進める / 止める / 戻す」を即決できる。

本実装では:
  * 現在 phase: settings.rollout_phase
  * 各メトリクス: 直近 N 日の trade / position 集計
  * アクションボタン: settings.rollout_phase を書き換え + Telegram 通知
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from copytrader.web.auth import require_password

st.set_page_config(page_title="Rollout (Mockup)", layout="wide")
require_password()

st.title("Rollout Console")
st.warning("MOCKUP — 全てダミーデータ。本実装では settings.rollout_phase を書き換えます。")

PHASES = [
    {
        "id": "A", "name": "Paper Trading",
        "duration_days": 28, "size_per_trade": 0, "daily_cap": 0,
        "desc": "実発注なし。シグナル受信 → 仮想発注のみで slippage/latency を測る。",
        "color": "#9aa0a6",
    },
    {
        "id": "B", "name": "Micro Live",
        "duration_days": 28, "size_per_trade": 10, "daily_cap": 100,
        "desc": "$10/trade、1 日上限 $100。実発注で小さく検証。",
        "color": "#5b9bd5",
    },
    {
        "id": "C", "name": "Small Live",
        "duration_days": 56, "size_per_trade": 50, "daily_cap": 500,
        "desc": "$50/trade、1 日上限 $500。本格運用への準備段階。",
        "color": "#2c7fb8",
    },
    {
        "id": "D", "name": "Scale",
        "duration_days": 9999, "size_per_trade": 250, "daily_cap": 2500,
        "desc": "継続運用。1 トレード資金 5% 上限。月次レビュー必須。",
        "color": "#1a5490",
    },
]

CURRENT_PHASE_IDX = 1
DAY_IN_PHASE = 18

current = PHASES[CURRENT_PHASE_IDX]

h1, h2, h3, h4, h5 = st.columns([1.4, 1, 1, 1, 1.2])
h1.markdown(
    f"### Phase **{current['id']}** — {current['name']}\n"
    f"<small>{current['desc']}</small>",
    unsafe_allow_html=True,
)
h2.metric("経過日数",
          f"{DAY_IN_PHASE} / {current['duration_days']}",
          f"残り {current['duration_days'] - DAY_IN_PHASE}日")
h3.metric("1 trade size", f"${current['size_per_trade']}")
h4.metric("日次上限", f"${current['daily_cap']}")
h5.metric("累計 PnL (phase 内)", "+$72.40", "+$8.20 today")

st.divider()

st.subheader("フェーズ進行")

stepper = go.Figure()
n = len(PHASES)
for i, p in enumerate(PHASES):
    if i < CURRENT_PHASE_IDX:
        color, opacity = "#2ca02c", 1.0
        label_suffix = " ✓"
    elif i == CURRENT_PHASE_IDX:
        color, opacity = p["color"], 1.0
        label_suffix = " ●"
    else:
        color, opacity = "#cccccc", 0.5
        label_suffix = ""
    stepper.add_shape(
        type="rect",
        x0=i + 0.05, x1=i + 0.95, y0=0.3, y1=0.7,
        fillcolor=color, opacity=opacity, line=dict(width=0),
    )
    stepper.add_annotation(
        x=i + 0.5, y=0.5, showarrow=False,
        text=f"<b>{p['id']}{label_suffix}</b><br>{p['name']}<br>"
             f"<span style='font-size:10px;color:#555'>"
             f"{p['duration_days']}d / ${p['size_per_trade']}</span>",
        font=dict(size=12, color="white" if opacity > 0.7 else "#666"),
    )
    if i < n - 1:
        stepper.add_annotation(
            x=i + 1, y=0.5, showarrow=False, text="→",
            font=dict(size=20, color="#888"),
        )

if CURRENT_PHASE_IDX < n:
    progress = DAY_IN_PHASE / max(1, PHASES[CURRENT_PHASE_IDX]["duration_days"])
    stepper.add_shape(
        type="rect",
        x0=CURRENT_PHASE_IDX + 0.05,
        x1=CURRENT_PHASE_IDX + 0.05 + 0.9 * min(progress, 1.0),
        y0=0.26, y1=0.30,
        fillcolor="#ff8c00", line=dict(width=0),
    )

stepper.update_layout(
    height=140, margin=dict(t=10, b=10, l=10, r=10),
    xaxis=dict(visible=False, range=[0, n]),
    yaxis=dict(visible=False, range=[0, 1]),
    plot_bgcolor="white",
)
st.plotly_chart(stepper, use_container_width=True)

st.divider()

st.subheader(f"Phase {current['id']} — 状況モニタ")

promo_col, halt_col = st.columns(2)

with promo_col:
    st.markdown("#### 昇格条件（全て ✅ で次フェーズへ）")
    promo_checks = [
        {"label": "経過日数 ≥ 28 日", "ok": False,
         "now": f"{DAY_IN_PHASE} 日", "target": "28 日"},
        {"label": "累積 ROI ≥ +3%", "ok": True,
         "now": "+4.2%", "target": "+3.0%"},
        {"label": "最大 DD ≤ 8%", "ok": True,
         "now": "-5.1%", "target": "-8.0%"},
        {"label": "勝率 ≥ 52%", "ok": True,
         "now": "56.8%", "target": "52.0%"},
        {"label": "backtest 乖離 ≤ 20%", "ok": True,
         "now": "12%", "target": "20%"},
        {"label": "Latency p95 ≤ 3000ms", "ok": False,
         "now": "3,420ms", "target": "3,000ms"},
        {"label": "kill switch テスト合格", "ok": True,
         "now": "passed (3 日前)", "target": "passed"},
    ]
    promo_df = pd.DataFrame([
        {
            "条件": p["label"],
            "現在値": p["now"],
            "目標": p["target"],
            "状態": "✅" if p["ok"] else "⏳",
        }
        for p in promo_checks
    ])
    st.dataframe(promo_df, use_container_width=True, hide_index=True, height=290)
    passed = sum(1 for p in promo_checks if p["ok"])
    st.progress(passed / len(promo_checks),
                text=f"{passed} / {len(promo_checks)} 条件クリア")

with halt_col:
    st.markdown("#### 停止条件（いずれか ⚠️ で即停止）")
    halt_checks = [
        {"label": "日次 PnL < -5%", "trip": False,
         "now": "+0.9%", "limit": "-5%"},
        {"label": "rolling 7d PnL < -8%", "trip": False,
         "now": "+2.1%", "limit": "-8%"},
        {"label": "連敗数 ≥ 5", "trip": False,
         "now": "2 連敗", "limit": "5 連敗"},
        {"label": "単一 market exposure > 25%", "trip": True,
         "now": "27% (米大統領)", "limit": "25%"},
        {"label": "indexer lag > 120s", "trip": False,
         "now": "18s", "limit": "120s"},
        {"label": "USDC 残高 < $500", "trip": False,
         "now": "$8,432", "limit": "$500"},
        {"label": "MATIC ガス < 1.0", "trip": False,
         "now": "12.4", "limit": "1.0"},
    ]
    halt_df = pd.DataFrame([
        {
            "条件": h["label"],
            "現在値": h["now"],
            "限界": h["limit"],
            "状態": "🛑" if h["trip"] else "🟢",
        }
        for h in halt_checks
    ])
    st.dataframe(halt_df, use_container_width=True, hide_index=True, height=290)
    tripped = sum(1 for h in halt_checks if h["trip"])
    if tripped > 0:
        st.error(f"{tripped} 件の停止条件にヒット — 要対処")
    else:
        st.success("全停止条件クリア")

st.divider()

st.subheader("Phase 内 daily metrics")

rng = np.random.default_rng(33)
days = pd.date_range(end=pd.Timestamp.utcnow(), periods=DAY_IN_PHASE, freq="D")
daily_pnl = rng.normal(loc=4, scale=12, size=DAY_IN_PHASE)
daily_pnl[7:10] = -np.abs(rng.normal(15, 5, 3))
cum_pnl = np.cumsum(daily_pnl)

mcol1, mcol2, mcol3 = st.columns(3)

with mcol1:
    st.markdown("**日次 PnL**")
    bar = go.Figure(go.Bar(
        x=days, y=daily_pnl,
        marker_color=["#2ca02c" if v >= 0 else "#d62728" for v in daily_pnl],
    ))
    bar.add_hline(y=0, line_color="#888", line_width=1)
    bar.update_layout(height=240, margin=dict(t=10, b=10, l=10, r=10),
                      showlegend=False, yaxis_title="USDC")
    st.plotly_chart(bar, use_container_width=True)

with mcol2:
    st.markdown("**累積 equity**")
    eq = go.Figure()
    eq.add_trace(go.Scatter(
        x=days, y=cum_pnl, mode="lines",
        line=dict(color="#2c7fb8", width=2),
        fill="tozeroy", fillcolor="rgba(44,127,184,0.15)",
    ))
    eq.add_hline(y=0, line_dash="dot", line_color="gray")
    eq.update_layout(height=240, margin=dict(t=10, b=10, l=10, r=10),
                     showlegend=False, yaxis_title="USDC")
    st.plotly_chart(eq, use_container_width=True)

with mcol3:
    st.markdown("**backtest vs 実績 乖離**")
    bt_predicted = rng.normal(loc=5, scale=8, size=DAY_IN_PHASE)
    bt_cum = np.cumsum(bt_predicted)
    cmp_fig = go.Figure()
    cmp_fig.add_trace(go.Scatter(
        x=days, y=bt_cum, mode="lines", name="backtest 予測",
        line=dict(color="#888", width=2, dash="dash"),
    ))
    cmp_fig.add_trace(go.Scatter(
        x=days, y=cum_pnl, mode="lines", name="実績",
        line=dict(color="#2c7fb8", width=2),
    ))
    cmp_fig.update_layout(height=240, margin=dict(t=10, b=10, l=10, r=10),
                          legend=dict(font=dict(size=10), x=0.02, y=0.98),
                          yaxis_title="USDC")
    st.plotly_chart(cmp_fig, use_container_width=True)

st.divider()

st.subheader("アクション")
st.caption(
    "意思決定はここから。実行は Telegram 確認 + 2FA を本実装で要求する想定。"
)

a1, a2, a3, a4 = st.columns(4)

with a1:
    can_promote = passed == len(promo_checks) and tripped == 0
    if can_promote:
        st.success("昇格可能")
    else:
        st.info("条件未達")
    st.button(
        f"→ Phase {PHASES[CURRENT_PHASE_IDX + 1]['id']} へ昇格",
        type="primary", use_container_width=True,
        disabled=not can_promote,
    )

with a2:
    st.info("継続")
    st.button("現フェーズを継続", use_container_width=True)

with a3:
    if CURRENT_PHASE_IDX > 0:
        st.warning("1 つ戻す")
        st.button(
            f"← Phase {PHASES[CURRENT_PHASE_IDX - 1]['id']} へ降格",
            use_container_width=True,
        )
    else:
        st.write("")

with a4:
    st.error("緊急停止")
    confirm_halt = st.checkbox("HALT 確認", key="halt_confirm")
    st.button(
        "🛑 全自動発注を停止", use_container_width=True,
        disabled=not confirm_halt,
    )

st.divider()

st.subheader("ロールアウト履歴")
history = pd.DataFrame([
    {"日付": "2026-04-23", "phase": "A → B", "判断": "promote",
     "理由": "Paper 28d 完了, ROI +5.2%, 全条件クリア"},
    {"日付": "2026-04-21", "phase": "A", "判断": "kill switch test",
     "理由": "停止条件テスト合格"},
    {"日付": "2026-04-15", "phase": "A", "判断": "戦略調整",
     "理由": "delay 30s → 60s に変更（slippage 大）"},
    {"日付": "2026-03-26", "phase": "— → A",  "判断": "promote",
     "理由": "Phase 0 backtest で edge 確認（ROI +6.8%）"},
    {"日付": "2026-03-15", "phase": "—", "判断": "edge validation",
     "理由": "Gamma API 連携 + resolve PnL で再評価"},
])
st.dataframe(history, use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "本実装の差し替えポイント: "
    "(1) PHASES → settings.rollout_phases / "
    "(2) CURRENT_PHASE_IDX, DAY_IN_PHASE → settings.rollout_phase + rollout_started_at / "
    "(3) promo/halt checks → 実データから動的判定 / "
    "(4) 昇格/降格ボタン → settings.rollout_phase update + Telegram 通知 + audit log"
)
