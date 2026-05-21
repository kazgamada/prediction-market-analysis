"""Home (Dashboard) — single viewport, tiles with hover help."""
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


_home_help = (
    "<b>このページの目的</b><hr>"
    "12 タイルで運用状況を一目で把握する画面。"
    "毎朝開いて: (1) 緑のままか赤に転じてないか、(2) リスク指標が許容内か、"
    "(3) 異常な数値が無いか を 30 秒でチェック。"
    "タイルのタイトルクリックで詳細ページへ遷移。"
)
st.markdown(
    f"# Home {help_icon(_home_help)}　"
    "<small style='font-size:0.7rem;color:#888;'>tile タイトルクリックで詳細</small>",
    unsafe_allow_html=True,
)

rng = np.random.default_rng(42)

TILE_H = 130
LAY = dict(height=TILE_H, margin=dict(t=4, b=4, l=4, r=4),
           showlegend=False, font=dict(size=9))


def tile_header(title: str, page_path: str, icon: str, help_text: str) -> None:
    c = st.columns([10, 1])
    with c[0]:
        st.page_link(page_path, label=f"**{title}**", icon=icon)
    with c[1]:
        st.markdown(help_icon(help_text), unsafe_allow_html=True)


k = st.columns(6)
k[0].metric("累積 PnL", "+$12,847", "+$523",
            help="シミュレーションでの 30 日累積 PnL (USDC)。実発注ではなく Phase 0 の replay 値。"
                 "目安: +10%/月 以上で edge あり、横ばいは劣化、マイナスは戦略破綻。")
k[1].metric("勝率", "58.3%", "+1.2pp",
            help="クローズした全 trade の勝率。Polymarket では 55% 以上が目安。"
                 "ただし勝率高くても 1 件あたり PnL が小さければ最終損益はマイナスになるので "
                 "Sharpe や ROI と併読する。")
k[2].metric("Watchlist", "12 / 50", "+2",
            help="active=true の watch wallet 数 / 上限。多すぎるとシグナル過多、少なすぎると edge 細る。"
                 "5〜15 件が運用しやすい範囲。Execute ページの Watchlist タブで管理。")
k[3].metric("最大 DD", "-8.4%", "-1.1pp", delta_color="inverse",
            help="30 日内の最大ドローダウン (過去ピークからの落ち込み)。"
                 "許容ライン -15% を超えたら kill switch 候補。実運用では -10% で警戒モード推奨。")
k[4].metric("USDC", "$8,432", "-$120",
            help="Polygon 上の USDC 残高。発注の燃料。$500 を切ると自動発注停止 (Execute の停止条件参照)。"
                 "毎朝確認し、必要なら入金。")
k[5].metric("今日 PnL", "+$184", "+2.2%",
            help="本日 0:00 UTC からの実現 PnL。括弧は資金比 %。"
                 "-5% を切ると日次停止条件にヒット。Execute の DD gauge と連動。")

r1 = st.columns(4)

with r1[0], st.container(border=True):
    tile_header(
        "Wallet equity (30d)", "pages/2_Execute.py", "👛",
        "<b>何を表示</b><hr>上位ウォレット 5 件の 30 日累積 PnL を重ね描き。"
        "<hr><b>なぜ重要</b><br>copy 対象の wallet が今も儲けているかをまず確認する場所。"
        "ライン が水平化 / 下降したウォレットは edge を失っており、copy 継続は損失要因。"
        "<hr><b>アクション</b><br>下降トレンドが 2 週間続く wallet は Execute → Watchlist で active=false に。"
    )
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
    tile_header(
        "Drawdown", "pages/1_Strategy.py", "📉",
        "<b>何を表示</b><hr>過去ピークからの落ち込み % (underwater plot)。0 = 最高値、"
        "深い谷ほど資金毀損が大きい。<hr><b>なぜ重要</b><br>絶対 PnL より「どこまで落ちたか」が "
        "破産リスクの本質的な指標。連続赤字で資金が回らなくなる前に止めるための見張り。"
        "<hr><b>アクション</b><br>オレンジ線 (-15%) を超えたら kill switch 検討。"
        "-10% で size 半減、-15% で全停止が目安。"
    )
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
    tile_header(
        "Replay ROI heatmap", "pages/1_Strategy.py", "🔥",
        "<b>何を表示</b><hr>delay (横軸: 15〜600 秒) × copy size (縦軸: $10〜$500) の全組み合わせの ROI%。"
        "<hr><b>なぜ重要</b><br>「いくらで何秒後に copy するのが最も儲かるか」のスイートスポット探索。"
        "短すぎる delay は signal 検知ミス、長すぎは機会損失で、両端で赤くなりやすい。"
        "<hr><b>アクション</b><br>濃い緑のセル位置を Execute → 執行パラメータに反映。"
        "週次で再計算して sweet spot のドリフトを追跡。"
    )
    delays = [15, 30, 60, 120, 300, 600]
    sizes = [10, 25, 50, 100, 250, 500]
    roi = rng.normal(2.5, 4, (len(sizes), len(delays)))
    roi[:, 0] += 3
    roi[:, -2:] -= 4
    f = go.Figure(data=go.Heatmap(z=roi, colorscale="RdYlGn", zmid=0, showscale=False))
    f.update_layout(**LAY, xaxis=dict(visible=False), yaxis=dict(visible=False))
    st.plotly_chart(f, use_container_width=True, key="t3")

with r1[3], st.container(border=True):
    tile_header(
        "Top 10 戦略 equity", "pages/1_Strategy.py", "🏆",
        "<b>何を表示</b><hr>市場 × 戦略の全 70 組合せのうち、累積 equity が最も高い上位 6 件のオーバーレイ。"
        "<hr><b>なぜ重要</b><br>「どの戦略が最も成績よいか」を視覚化。"
        "全線がジリ上げ = 本物の edge。1 本だけ突出 = 過学習や偶然の可能性。"
        "<hr><b>アクション</b><br>上位の安定的な戦略を本番戦略に採用。"
        "詳細は Strategy ページの Top 10 並び替えで確認。"
    )
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
    tile_header(
        "市場×戦略 matrix", "pages/1_Strategy.py", "🧪",
        "<b>何を表示</b><hr>全市場 × 全戦略の ROI% マトリクス (縮小版)。"
        "<hr><b>なぜ重要</b><br>「どの市場で、どの戦略が効くか」の俯瞰。"
        "市場ごとに最適戦略が違うことが多い (選挙系は短 delay 有利、長期系は長 delay 有利など)。"
        "<hr><b>アクション</b><br>全緑なら戦略安泰、まだら模様なら市場ごとに戦略切替が必要。"
        "詳細は Strategy ページのヒートマップで。"
    )
    rm = rng.normal(3, 7, (8, 6))
    rm[2, :] += 5
    f = go.Figure(data=go.Heatmap(z=rm, colorscale="RdYlGn", zmid=0, showscale=False))
    f.update_layout(**LAY, xaxis=dict(visible=False), yaxis=dict(visible=False))
    st.plotly_chart(f, use_container_width=True, key="t5")

with r2[1], st.container(border=True):
    tile_header(
        "シグナル時間帯", "pages/3_Ops.py", "⏰",
        "<b>何を表示</b><hr>smart money が約定する曜日 (縦) × 時刻 UTC (横) の頻度ヒートマップ。"
        "<hr><b>なぜ重要</b><br>Polymarket は米国時間に活発化。"
        "閑散時間帯の signal は薄く、信頼性低い (1 人の誤発注を copy するリスク)。"
        "<hr><b>アクション</b><br>濃い時間帯のみ稼働させ、薄い時間帯は signal を skip する設定も検討。"
    )
    heat = rng.poisson(3, (7, 24)).astype(float)
    heat[:, 13:22] *= 2.5
    heat[5:7, :] *= 0.6
    f = go.Figure(data=go.Heatmap(z=heat, colorscale="Blues", showscale=False))
    f.update_layout(**LAY, xaxis=dict(visible=False), yaxis=dict(visible=False))
    st.plotly_chart(f, use_container_width=True, key="t6")

with r2[2], st.container(border=True):
    tile_header(
        "DD gauge (今日)", "pages/2_Execute.py", "🛑",
        "<b>何を表示</b><hr>今日 (UTC 0:00 起算) の累積 DD%、許容上限 8%。"
        "緑 → 黄 → 赤 で色変化。<hr><b>なぜ重要</b><br>今この瞬間 "
        "kill switch が発動するまでどれくらい余裕があるかを示す唯一の指標。"
        "<hr><b>アクション</b><br>赤ゾーン (6.4% 超) に入ったら手動で発注停止を検討、"
        "8% 到達で自動 halt が走る。"
    )
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
    tile_header(
        "Latency (signal→fill)", "pages/2_Execute.py", "⚡",
        "<b>何を表示</b><hr>signal 受信から CLOB 約定完了までの所要時間 (ms) のヒストグラム。"
        "オレンジ線 = 中央値 (p50)。<hr><b>なぜ重要</b><br>copy trade の命は速度。"
        "遅いほど smart money の entry 価格から離れ、slippage で利益が削られる。"
        "<hr><b>アクション</b><br>p95 が 3 秒超なら執行ロジック / RPC ノード見直し。"
        "山が右に動いてるなら劣化中。"
    )
    lat = rng.normal(850, 280, 200).clip(min=100)
    f = go.Figure(data=go.Histogram(x=lat, nbinsx=20, marker_color="#2c7fb8"))
    f.add_vline(x=np.median(lat), line_dash="dash", line_color="orange")
    f.update_layout(**LAY, xaxis_title="", yaxis_title="")
    st.plotly_chart(f, use_container_width=True, key="t8")

r3 = st.columns(4)

with r3[0], st.container(border=True):
    tile_header(
        "Position exposure", "pages/2_Execute.py", "💰",
        "<b>何を表示</b><hr>市場別の保有額 (USDC) を横棒で。緑 = 含み益、赤 = 含み損。"
        "<hr><b>なぜ重要</b><br>1 市場に偏りすぎると、その市場 1 つの予測ミスで大ダメージ。"
        "分散具合 (各バーが似た長さか) を視認。"
        "<hr><b>アクション</b><br>単一バーが全体の 25% を超えてたら新規 entry を skip する設定を確認 "
        "(Execute → 停止条件)。"
    )
    labels = ["米大統領", "FRB", "BTC", "AI", "G7", "WC", "投票率"]
    sizes_ = [320, 250, 480, 410, 200, 180, 1370]
    pnls = [22.8, 13.6, 80, 12, -2.8, -30, 90.2]
    colors = ["#2ca02c" if p >= 0 else "#d62728" for p in pnls]
    f = go.Figure(go.Bar(x=sizes_, y=labels, orientation="h", marker_color=colors))
    f.update_layout(**LAY, xaxis=dict(visible=False),
                    yaxis=dict(tickfont=dict(size=8)))
    st.plotly_chart(f, use_container_width=True, key="t9")

with r3[1], st.container(border=True):
    tile_header(
        "Watchlist Top 5", "pages/2_Execute.py", "📋",
        "<b>何を表示</b><hr>監視中ウォレットの上位 5 件と直近 20 日の equity sparkline。"
        "<hr><b>なぜ重要</b><br>個別 wallet のミニ equity curve。"
        "上昇トレンドが続いてるなら active 継続、横ばい / 下降は劣化中。"
        "<hr><b>アクション</b><br>下降中の wallet を Execute → Watchlist タブで active=false。"
        "新しい wallet は Strategy で Phase 0 を回して候補発掘。"
    )
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
    tile_header(
        "受信シグナル", "pages/2_Execute.py", "📨",
        "<b>何を表示</b><hr>直近 5 件の signal と処理結果。"
        "<hr><b>なぜ重要</b><br>システムが正しく signal を取り込んで発注しているかの health check。"
        "数分 signal が来てないなら indexer 停止の可能性。"
        "<hr><b>状態の見方</b><br>"
        "✅ = 約定 / ⏳ = 待機中 / ❌ = CLOB rejected (要 Ops 確認) / "
        "⏭ = リスク上限 skip (Execute の停止条件にヒット)"
    )
    now = datetime.now(UTC)
    df = pd.DataFrame({
        "時刻": [(now - timedelta(seconds=int(s))).strftime("%H:%M:%S")
                 for s in sorted(rng.integers(5, 900, 5))],
        "side": rng.choice(["BUY", "SELL"], 5).tolist(),
        "状態": rng.choice(["✅", "⏳", "❌", "⏭"], 5, p=[0.5, 0.2, 0.1, 0.2]).tolist(),
    })
    st.dataframe(df, use_container_width=True, hide_index=True, height=TILE_H)

with r3[3], st.container(border=True):
    tile_header(
        "Indexer lag", "pages/3_Ops.py", "📡",
        "<b>何を表示</b><hr>indexer の処理遅れ (秒) の過去 24 時間推移。"
        "赤線 = 警報閾値 120 秒。<hr><b>なぜ重要</b><br>indexer が遅れると signal も遅れ、"
        "古い情報で copy することになる。リアルタイム性が崩れると edge が消える。"
        "<hr><b>アクション</b><br>赤線突破が続くなら Ops で dead-letter 確認、"
        "Polygon RPC ノードのリージョン切替を検討。"
    )
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
