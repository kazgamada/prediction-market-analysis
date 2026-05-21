"""Strategy — Phase0 (real) + Strategy Lab (mockup) with hover help."""
from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import desc, select

from copytrader.db.engine import get_session
from copytrader.db.models import Job
from copytrader.jobs.queue import enqueue
from copytrader.web.auth import require_password
from copytrader.web.format import fmt_ago

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
.stButton button { padding: 0.2rem 0.5rem !important; font-size: 0.78rem !important; }
input, select, .stNumberInput input { font-size: 0.78rem !important; }
</style>
""", unsafe_allow_html=True)


def help_icon(html_text: str) -> str:
    """Inline ⓘ icon with browser-native title tooltip (hover-only).

    Uses &#10; (HTML numeric char ref for LF) instead of real newlines so the
    markdown parser doesn't split the attribute across lines.
    """
    text = html_text
    text = text.replace("<hr>", "&#10;────────&#10;")
    text = text.replace("<br>", "&#10;")
    text = text.replace("<b>", "").replace("</b>", "")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&amp;", "&").replace("&quot;", "'")
    text = text.replace('"', "'")
    return (
        '<span title="' + text + '" '
        'style="cursor:help;color:#2c7fb8;font-weight:bold;font-size:0.85rem">'
        'ⓘ</span>'
    )


HELP = {
    "page": (
        "<b>このページの目的</b><hr>"
        "edge があるかを backtest で検証する画面。"
        "Phase 0 (上部) でバックテストを回し、結果を市場×戦略マトリクスで俯瞰、"
        "上位 10 戦略の equity を比較。週次レビューで「今月もこの戦略で稼げるか」を判断。"
    ),
    "phase0_form": (
        "<b>このフォーム</b><hr>"
        "ウォレットランキング + 遅延コピー replay を grid 実行する backend job を投入。"
        "結果はマトリクス・heatmap・Top10 equity に反映される。"
        "<hr><b>パラメータ</b><br>"
        "・<b>window 日</b>: 何日分の trade を対象にするか (30 推奨、少ないと過学習)<br>"
        "・<b>top N</b>: 上位ウォレットを何件採用するか<br>"
        "・<b>copy $</b>: 1 trade あたりのシミュ金額<br>"
        "・<b>delays 秒</b>: シミュレートする遅延秒 (カンマ区切り)"
        "<hr><b>運用</b><br>"
        "週次で 1 回実行し edge の継続性を確認。結果は右下「Recent runs」に蓄積。"
    ),
    "market_list": (
        "<b>マーケット一覧</b><hr>"
        "対象市場の流動性スナップショット。24h vol 降順。"
        "<hr><b>列の見方</b><br>"
        "・<b>24h vol</b>: 過去 24h の出来高。$50k 未満は流動性低 (copy 不可)<br>"
        "・<b>price</b>: 現在のミッド価格 (0〜1)<br>"
        "・<b>resolve</b>: 解決まで残り日数。&lt; 7日は急変リスク<br>"
        "・<b>best ROI</b>: その市場での最良戦略 ROI%<br>"
        "・<b>trend</b>: 過去 30 日の価格 sparkline"
        "<hr><b>判断</b><br>"
        "vol が大きく、resolve が遠く、trend が安定してる市場が copy trade 向き。"
    ),
    "heatmap": (
        "<b>マトリクス: 市場 × 戦略</b><hr>"
        "各セル = その組合せの backtest 結果。"
        "<hr><b>色付け指標</b><br>"
        "・<b>ROI %</b>: 単純な収益率 (緑+ 赤−)。楽観的<br>"
        "・<b>Sharpe</b>: リスク調整後リターン。推奨指標<br>"
        "・<b>trades</b>: サンプル数。少ないと信頼性低"
        "<hr><b>判断</b><br>"
        "横一列が全部緑な市場は「どんな戦略でも勝てる」= 良市場。"
        "縦一列が全部緑な戦略は「どの市場でも効く」万能戦略 (滅多にない)。"
    ),
    "scatter": (
        "<b>ROI × Sharpe × trades</b><hr>"
        "全シナリオを 3 次元バブルプロット: x=ROI%、y=Sharpe、バブル size=trades 数。"
        "色はストラテジー別。"
        "<hr><b>象限の見方</b><br>"
        "・<b>右上 (ROI+ Sharpe+)</b>: 理想ゾーン、採用候補<br>"
        "・<b>右下 (ROI+ Sharpe−)</b>: 高 ROI だがばらつき大 = 偶然の可能性<br>"
        "・<b>左上 (ROI− Sharpe+)</b>: 安定して負け = 戦略が逆<br>"
        "・<b>左下</b>: 戦略破綻"
        "<hr><b>判断</b><br>大きいバブル ほどデータ信頼性高。"
        "小さいバブルの右上は採用前に再検証。"
    ),
    "top10": (
        "<b>Top 10 equity overlay</b><hr>"
        "並び替え指標の上位 10 シナリオの equity curve を重ね描き。"
        "<hr><b>並び替え指標</b><br>"
        "・<b>ROI %</b>: 最終収益率順<br>"
        "・<b>Sharpe</b>: リスク調整後リターン順 (推奨)<br>"
        "・<b>ROI×Sharpe</b>: 両方を満たす複合指標"
        "<hr><b>判断</b><br>"
        "・全 10 本がジリ上げ → 本物の edge<br>"
        "・1〜2 本だけ突出 → 過学習リスク<br>"
        "・全体的に水平 → edge 喪失、戦略見直し<br>"
        "・終盤で全部下げ → 直近で劣化、緊急アラート"
    ),
    "recent_runs": (
        "<b>Recent Phase 0 runs</b><hr>"
        "直近 8 件の Phase 0 job 履歴。"
        "<hr><b>列の見方</b><br>"
        "・<b>id</b>: job 番号<br>"
        "・<b>status</b>: QUEUED 待機 / RUNNING 実行中 / COMPLETED 完了 / FAILED 失敗<br>"
        "・<b>created</b>: enqueue されてからの経過<br>"
        "・<b>window</b>: 当時のパラメータ"
        "<hr><b>判断</b><br>"
        "FAILED 連発 → Ops で DB/RPC エラー確認。"
        "週次で COMPLETED が安定 → 正常運用。"
    ),
}

st.markdown(
    f"# Strategy {help_icon(HELP['page'])}　"
    "<small style='font-size:0.7rem;color:#888;'>backtest + market×strategy 一覧</small>",
    unsafe_allow_html=True,
)

rng = np.random.default_rng(2026)

MARKETS = ["米大統領 2028", "FRB 6月 利下げ", "BTC>$150k EOY", "AI バブル崩壊",
           "G7 開催", "WC — Brazil", "投票率 60%+", "OpenAI IPO", "EU 関税",
           "為替 140 割れ"]
STRATEGIES = [
    {"name": "Top10/30s/$50", "delay": 30, "size": 50},
    {"name": "Top10/60s/$50", "delay": 60, "size": 50},
    {"name": "Top5/30s/$100", "delay": 30, "size": 100},
    {"name": "Top20/120s/$25", "delay": 120, "size": 25},
    {"name": "Top5/15s/$200", "delay": 15, "size": 200},
    {"name": "Contra-B5/60s", "delay": 60, "size": 50},
    {"name": "Whale>$10k/30s", "delay": 30, "size": 100},
]
n_m, n_s = len(MARKETS), len(STRATEGIES)
roi = rng.normal(4, 8, (n_m, n_s))
roi[:, 0] += 3
roi[:, -2] -= 5
roi[2, :] += 6
roi[7, :] -= 4
sharpe = roi / (4 + rng.uniform(0, 3, (n_m, n_s)))
trades = rng.integers(20, 400, (n_m, n_s))
strat_labels = [s["name"] for s in STRATEGIES]

best = np.unravel_index(np.argmax(roi), roi.shape)
worst = np.unravel_index(np.argmin(roi), roi.shape)
pos_sims = int((roi > 0).sum())

top_row = st.columns([2.4, 1, 1, 1, 1, 1])
with top_row[0], st.container(border=True):
    st.markdown(f"##### Phase 0 を実行 {help_icon(HELP['phase0_form'])}",
                unsafe_allow_html=True)
    with st.form("phase0"):
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1.4, 0.8])
        w = c1.number_input("window 日", min_value=1, max_value=90, value=30)
        tn = c2.number_input("top N", min_value=1, max_value=200, value=10)
        cu = c3.number_input("copy $", min_value=1, max_value=10000, value=50)
        ds = c4.text_input("delays 秒", "30,60,120")
        sub = c5.form_submit_button("Run", type="primary",
                                    use_container_width=True)
        if sub:
            try:
                delays = [int(x.strip()) for x in ds.split(",") if x.strip()]
                idem = f"phase0:{datetime.now(UTC).strftime('%Y%m%d%H%M')}:{w}:{tn}"
                jid = enqueue("phase0", {
                    "window": int(w), "watchlist_top": int(tn),
                    "delays": delays, "copy_usd_per_trade": float(cu),
                }, idempotency_key=idem)
                st.success(f"enqueued #{jid}")
            except Exception as e:  # noqa: BLE001
                st.error(f"enqueue failed: {e}")
top_row[1].metric(
    "sim 総数", f"{n_m * n_s}", f"{n_m}×{n_s}",
    help="マーケット数 × ストラテジー数 = 全 backtest 件数。"
         "多いほど信頼性高いが計算時間も増える。70〜200 件が現実的。",
)
top_row[2].metric(
    "黒字", f"{pos_sims}", f"{pos_sims / (n_m * n_s) * 100:.0f}%",
    help="ROI > 0 のシナリオ数 / 全シナリオの比率。50% 未満は edge が薄い。"
         "本物の edge があれば 60〜70% の市場で黒字。",
)
top_row[3].metric(
    "ベスト", f"{roi[best]:+.1f}%", MARKETS[best[0]][:8],
    help="全シナリオ中の最高 ROI とそのマーケット。"
         "1 件だけ突出して他が赤なら過学習 / 偶然のリスクあり。",
)
top_row[4].metric(
    "ワースト", f"{roi[worst]:+.1f}%", MARKETS[worst[0]][:8],
    delta_color="inverse",
    help="全シナリオ中の最悪 ROI。-20% 超があれば戦略を絞り込み必要。",
)
top_row[5].metric(
    "中央値", f"{np.median(roi):+.1f}%",
    help="全シナリオ ROI の中央値。「典型的なシナリオで儲かるか」の指標。"
         "ベスト/ワーストより信頼できる。+3% 以上で edge ありと判断。",
)

r1 = st.columns([1, 1.2])

with r1[0], st.container(border=True):
    st.markdown(f"##### マーケット一覧 {help_icon(HELP['market_list'])}",
                unsafe_allow_html=True)
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
    st.dataframe(mkt, use_container_width=True, hide_index=True, height=240,
                 column_config={
                     "24h vol": st.column_config.NumberColumn(format="$%d"),
                     "price": st.column_config.ProgressColumn(
                         min_value=0.0, max_value=1.0, format="%.2f"),
                     "resolve": st.column_config.NumberColumn(format="%d日"),
                     "best ROI": st.column_config.NumberColumn(format="%+.1f%%"),
                     "trend": st.column_config.LineChartColumn(y_min=0, y_max=1),
                 })

with r1[1], st.container(border=True):
    hc1, hc2 = st.columns([5, 1])
    with hc1:
        metric_pick = st.radio(
            "色付け", ["ROI %", "Sharpe", "trades"],
            horizontal=True, label_visibility="collapsed", key="metric_pick",
        )
    with hc2:
        st.markdown(help_icon(HELP["heatmap"]), unsafe_allow_html=True)
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
    hm.update_layout(height=220, margin=dict(t=5, b=5, l=5, r=5),
                     xaxis=dict(tickangle=-30, tickfont=dict(size=9)),
                     yaxis=dict(tickfont=dict(size=9)),
                     font=dict(size=8))
    st.plotly_chart(hm, use_container_width=True, key="t_hm")

r2 = st.columns([1, 1, 1])

with r2[0], st.container(border=True):
    st.markdown(f"##### ROI × Sharpe × trades {help_icon(HELP['scatter'])}",
                unsafe_allow_html=True)
    rows = []
    for mi, m in enumerate(MARKETS):
        for si, s in enumerate(STRATEGIES):
            rows.append({"market": m, "strategy": s["name"],
                         "ROI %": roi[mi, si], "Sharpe": sharpe[mi, si],
                         "trades": int(trades[mi, si])})
    sdf = pd.DataFrame(rows)
    sc = px.scatter(sdf, x="ROI %", y="Sharpe", size="trades", color="strategy",
                    hover_data=["market"], size_max=16)
    sc.add_hline(y=0, line_dash="dot", line_color="gray")
    sc.add_vline(x=0, line_dash="dot", line_color="gray")
    sc.update_layout(height=220, margin=dict(t=5, b=5, l=5, r=5),
                     showlegend=False, font=dict(size=8))
    st.plotly_chart(sc, use_container_width=True, key="t_sc")

with r2[1], st.container(border=True):
    hc1, hc2 = st.columns([5, 1])
    with hc1:
        sort_pick = st.radio(
            "Top10 並び替え", ["ROI %", "Sharpe", "ROI×Sharpe"],
            horizontal=True, label_visibility="collapsed", key="sort_pick",
        )
    with hc2:
        st.markdown(help_icon(HELP["top10"]), unsafe_allow_html=True)
    combos = []
    for mi, m in enumerate(MARKETS):
        for si, _s in enumerate(STRATEGIES):
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
                                name=f"#{int(i + 1)}",
                                hovertemplate=f"{row['market']}<br>{row['strategy']}<br>$%{{y:.0f}}<extra></extra>"))
    eq.add_hline(y=1000, line_dash="dot", line_color="gray")
    eq.update_layout(height=180, margin=dict(t=5, b=5, l=5, r=5),
                     font=dict(size=8),
                     legend=dict(font=dict(size=7), x=1.01, y=1))
    st.plotly_chart(eq, use_container_width=True, key="t_eq")

with r2[2], st.container(border=True):
    st.markdown(f"##### Recent Phase 0 runs {help_icon(HELP['recent_runs'])}",
                unsafe_allow_html=True)
    try:
        with get_session() as s:
            phase0_rows = (
                s.execute(
                    select(Job).where(Job.kind == "phase0")
                    .order_by(desc(Job.created_at)).limit(8)
                ).scalars().all()
            )
            data = [
                {
                    "id": r.id,
                    "status": r.status,
                    "created": fmt_ago(r.created_at),
                    "window": (r.params or {}).get("window"),
                }
                for r in phase0_rows
            ]
            # 最新の完了 job の結果を保持
            last_done = next(
                (r for r in phase0_rows if r.status == "SUCCEEDED" and r.result), None
            )
    except Exception as e:  # noqa: BLE001
        data = []
        phase0_rows = []
        last_done = None
        st.caption(f"db: {e}")
    st.dataframe(data, use_container_width=True, hide_index=True, height=130)

    # 最新の完了した Phase 0 の Replay 結果を表示
    if last_done and last_done.result:
        st.markdown("**最新 Phase 0 結果**")
        replay_res = (last_done.result or {}).get("replay", {})
        per_delay = (replay_res or {}).get("per_delay", [])
        if per_delay:
            import pandas as pd
            df_replay = pd.DataFrame([
                {
                    "delay (s)": r.get("delay_seconds"),
                    "signals": f"{r.get('signals_executed',0)}/{r.get('signals_total',0)}",
                    "PnL (USDC)": r.get("realized_pnl_usdc", "—"),
                    "ROI %": r.get("roi_pct", "—"),
                }
                for r in per_delay
            ])
            st.dataframe(df_replay, use_container_width=True, hide_index=True, height=90)
        wallets = (last_done.result or {}).get("top_wallets", [])
        if wallets:
            st.caption(f"上位 {len(wallets)} wallets")
    elif data:
        st.caption("完了した Phase 0 がありません")
