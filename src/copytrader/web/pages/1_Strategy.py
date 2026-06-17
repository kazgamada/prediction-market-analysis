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
from copytrader.web.theme import (
    ACCENT_CYAN, ACCENT_GREEN, ACCENT_RED, ACCENT_YELLOW,
    LIVE_LAYOUT, LIVE_PALETTE, STATIC_LAYOUT, STATIC_PALETTE,
    TILE_BG, inject_theme,
)
from copytrader.web.format import fmt_ago

st.set_page_config(page_title="Strategy", layout="wide",
                   initial_sidebar_state="collapsed")
require_password()

inject_theme()


def help_icon(html_text: str) -> str:
    """Inline ⓘ icon with browser-native title tooltip (hover-only)."""
    text = html_text
    text = text.replace("<hr>", "&#10;────────&#10;")
    text = text.replace("<br>", "&#10;")
    text = text.replace("<b>", "").replace("</b>", "")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&amp;", "&").replace("&quot;", "'")
    text = text.replace('"', "'")
    return (
        '<span class="help-tip-icon" title="' + text + '">ⓘ</span>'
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

# Real data accessor — pulls the latest completed phase0 job's result.
@st.cache_data(ttl=10)
def _latest_phase0() -> dict:
    try:
        with get_session() as s:
            row = s.execute(
                select(Job).where(Job.kind == "phase0")
                .where(Job.status == "SUCCEEDED")
                .order_by(desc(Job.finished_at)).limit(1)
            ).scalar_one_or_none()
            if not row or not row.result:
                return {"ok": False}
            return {
                "ok": True,
                "result": dict(row.result),
                "params": dict(row.params or {}),
                "finished_at": row.finished_at,
            }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


_P = _latest_phase0()
_RESULT = _P.get("result") or {}
_AGG = _RESULT.get("aggregate") or {}
_REPLAY = (_RESULT.get("replay") or {}).get("per_delay") or []
_WALLETS = (_RESULT.get("rank") or {}).get("wallets") or []
_CURVES = _RESULT.get("wallet_curves") or []

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
sim_count = int(_AGG.get("sim_count", 0))
pos_count = int(_AGG.get("positive_count", 0))
best_v = _AGG.get("best_roi")
worst_v = _AGG.get("worst_roi")
median_v = _AGG.get("median_roi")
top_row[1].metric(
    "sim 総数", f"{sim_count}" if sim_count else "—",
    f"{len(_REPLAY)} delays" if _REPLAY else "no run yet",
    help="直近 Phase 0 run の replay 試行回数 (= delays の数)。"
         "70〜200 件が現実的だが Phase 0 は delay 数 = 試行数。",
)
top_row[2].metric(
    "黒字", f"{pos_count}/{sim_count}" if sim_count else "—",
    f"{pos_count / sim_count * 100:.0f}%" if sim_count else "—",
    help="ROI > 0 だった delay 設定の比率。50% 未満は edge が薄い。"
         "本物の edge があれば 60〜70% で黒字。",
)
if best_v is not None:
    top_row[3].metric(
        "ベスト", f"{float(best_v):+.1f}%",
        help="全 replay 中の最高 ROI。",
    )
else:
    top_row[3].metric("ベスト", "—", help="Phase 0 未実行")
if worst_v is not None:
    top_row[4].metric(
        "ワースト", f"{float(worst_v):+.1f}%",
        delta_color="inverse",
        help="全 replay 中の最悪 ROI。-20% 超があれば戦略を絞り込み必要。",
    )
else:
    top_row[4].metric("ワースト", "—")
if median_v is not None:
    top_row[5].metric(
        "中央値", f"{float(median_v):+.1f}%",
        help="全シナリオ ROI の中央値。「典型的なシナリオで儲かるか」。",
    )
else:
    top_row[5].metric("中央値", "—")

r1 = st.columns([1, 1.2])

with r1[0], st.container(border=True):
    st.markdown(f"##### 上位ウォレット一覧 {help_icon(HELP['market_list'])}",
                unsafe_allow_html=True)
    if not _WALLETS:
        st.caption("(no Phase 0 result — フォームで Run)")
    else:
        # Map address -> equity curve
        curves_by_addr = {c["address"]: c.get("series", []) for c in _CURVES}
        mkt_rows = []
        for w in _WALLETS:
            try:
                pnl_val = float(w.get("realized_pnl_usdc") or 0)
                vol_val = float(w.get("volume_usdc") or 0)
                wr_val = float(w.get("win_rate") or 0) if w.get("win_rate") else 0.0
            except (TypeError, ValueError):
                pnl_val, vol_val, wr_val = 0.0, 0.0, 0.0
            mkt_rows.append({
                "wallet": w.get("address", "")[:14] + "…",
                "trades": int(w.get("trades", 0)),
                "volume": vol_val,
                "PnL": pnl_val,
                "win_rate": wr_val,
                "30d": curves_by_addr.get(w.get("address", ""), []),
            })
        mkt_rows.sort(key=lambda r: r["PnL"], reverse=True)
        st.dataframe(
            mkt_rows, use_container_width=True, hide_index=True, height=240,
            column_config={
                "trades": st.column_config.NumberColumn(format="%d"),
                "volume": st.column_config.NumberColumn(format="$%d"),
                "PnL": st.column_config.NumberColumn(format="$%+.0f"),
                "win_rate": st.column_config.NumberColumn(format="%.2f"),
                "30d": st.column_config.LineChartColumn(),
            },
        )

with r1[1], st.container(border=True):
    hc1, hc2 = st.columns([5, 1])
    with hc1:
        st.markdown("##### delay 別 ROI / signals")
    with hc2:
        st.markdown(help_icon(HELP["heatmap"]), unsafe_allow_html=True)
    if not _REPLAY:
        st.caption("(no Phase 0 replay results)")
    else:
        delays = [str(r.get("delay_seconds")) + "s" for r in _REPLAY]
        rois = [float(r.get("roi_pct") or 0) for r in _REPLAY]
        execs = [int(r.get("signals_executed") or 0) for r in _REPLAY]
        totals = [int(r.get("signals_total") or 0) for r in _REPLAY]
        # Build a 2-row heatmap: [ROI%], [fill rate %]
        fill_rates = [
            (e / t * 100) if t else 0 for e, t in zip(execs, totals, strict=False)
        ]
        z = [rois, fill_rates]
        text = [
            [f"{v:+.1f}%" for v in rois],
            [f"{v:.0f}%" for v in fill_rates],
        ]
        hm = go.Figure(data=go.Heatmap(
            z=z, x=delays, y=["ROI%", "fill%"],
            colorscale="RdYlGn", zmid=0, showscale=False,
            text=text, texttemplate="%{text}",
            hovertemplate="%{y} @ %{x}: %{z}<extra></extra>",
        ))
        hm.update_layout(
            **{**STATIC_LAYOUT, "height": 220,
               "xaxis": {**STATIC_LAYOUT["xaxis"],
                         "tickfont": dict(size=10, color="#1a1a1a")},
               "yaxis": {**STATIC_LAYOUT["yaxis"],
                         "tickfont": dict(size=10, color="#1a1a1a")}},
        )
        st.plotly_chart(hm, use_container_width=True, key="t_hm")

r2 = st.columns([1, 1, 1])

with r2[0], st.container(border=True):
    st.markdown(f"##### wallet PnL × 勝率 × volume {help_icon(HELP['scatter'])}",
                unsafe_allow_html=True)
    if not _WALLETS:
        st.caption("(no Phase 0 result)")
    else:
        rows = []
        for w in _WALLETS:
            try:
                pnl = float(w.get("realized_pnl_usdc") or 0)
                vol = float(w.get("volume_usdc") or 0)
                wr = float(w.get("win_rate") or 0) if w.get("win_rate") else 0.0
                trades_n = int(w.get("trades", 0))
            except (TypeError, ValueError):
                continue
            rows.append({
                "wallet": w.get("address", "")[:10] + "…",
                "PnL": pnl, "win_rate": wr,
                "trades": trades_n, "volume": vol,
            })
        sdf = pd.DataFrame(rows)
        sc = px.scatter(
            sdf, x="PnL", y="win_rate", size="trades", color="wallet",
            hover_data=["volume"], size_max=18,
            color_discrete_sequence=STATIC_PALETTE * 3,
        )
        sc.add_hline(y=0.5, line_dash="dot", line_color="#999")
        sc.add_vline(x=0, line_dash="dot", line_color="#999")
        sc.update_layout(
            **{**STATIC_LAYOUT, "height": 220, "showlegend": False},
        )
        st.plotly_chart(sc, use_container_width=True, key="t_sc")

with r2[1], st.container(border=True):
    hc1, hc2 = st.columns([5, 1])
    with hc1:
        st.markdown("##### Top 10 wallet equity (30d)")
    with hc2:
        st.markdown(help_icon(HELP["top10"]), unsafe_allow_html=True)
    if not _CURVES:
        st.caption("(no wallet curves — Phase 0 を Run)")
    else:
        palette = STATIC_PALETTE * 2
        eq = go.Figure()
        for i, c in enumerate(_CURVES[:10]):
            series = c.get("series") or []
            if not series:
                continue
            eq.add_trace(go.Scatter(
                y=series, mode="lines",
                line=dict(color=palette[i % len(palette)], width=1.5),
                name=f"#{i + 1} {c.get('address', '')[:8]}…",
                hovertemplate="$%{y:+.0f}<extra></extra>",
            ))
        eq.add_hline(y=0, line_dash="dot", line_color="#999")
        eq.update_layout(
            **{**STATIC_LAYOUT, "height": 180,
               "showlegend": True,
               "legend": dict(font=dict(size=7, color="#1a1a1a"), x=1.01, y=1)},
        )
        st.plotly_chart(eq, use_container_width=True, key="t_eq")

with r2[2], st.container(border=True):
    st.markdown(f"##### Recent Phase 0 runs {help_icon(HELP['recent_runs'])}",
                unsafe_allow_html=True)
    try:
        with get_session() as s:
            rows = (
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
                for r in rows
            ]
    except Exception as e:  # noqa: BLE001
        data = []
        st.caption(f"db: {e}")
    st.dataframe(data, use_container_width=True, hide_index=True, height=220)
