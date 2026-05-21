"""Execute — Execution + Watchlist + Jobs + Rollout with hover help."""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from copytrader.db.engine import get_session
from copytrader.db.models import Job, Watchlist
from copytrader.web.auth import require_password
from copytrader.web.format import fmt_ago, short_addr

st.set_page_config(page_title="Execute", layout="wide",
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
.stProgress > div > div > div { height: 6px !important; }
.stButton button { padding: 0.2rem 0.5rem !important; font-size: 0.78rem !important; }
input, .stNumberInput input { font-size: 0.78rem !important; }
.stTabs [data-baseweb="tab"] { padding: 0.2rem 0.5rem !important; font-size: 0.78rem !important; }
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
        "「ロボットが今、何をしているか」を見て、必要なら介入する画面。"
        "毎日 / 何かおかしいと感じたら開く。"
        "<hr><b>主な確認順</b><br>"
        "1. ステータスバー: 残高・PnL・kill switch が緑か<br>"
        "2. リスク列: gauge と progress bar が許容内か<br>"
        "3. ポジション / シグナル / fills: 異常な動きが無いか<br>"
        "4. Rollout: 現在の phase と昇格 / 停止条件"
    ),
    "killswitch": (
        "<b>Kill Switch</b><hr>"
        "全自動発注を即停止するマスタースイッチ。"
        "<hr><b>使い方</b><br>"
        "・障害検知時、不在時、相場急変時の安全策<br>"
        "・ON 中: 新規 signal が来ても発注されない<br>"
        "・既存ポジションは維持される (清算は手動 order タブから)"
        "<hr><b>解除</b><br>"
        "原因を Ops で確認してから解除。"
        "解除直後は溜まった signal が一気に発注されないか注意。"
    ),
    "risk": (
        "<b>4 種のリスク監視</b><hr>"
        "上: 今日の DD gauge / 下: 4 件の上限プログレス。"
        "<hr><b>各 progress の意味</b><br>"
        "・<b>exposure</b>: 全 market への総エクスポージャ / 上限 70%。超過で新規禁止<br>"
        "・<b>単一 token</b>: 1 市場への偏り / 上限 25%。⚠ なら分散見直し<br>"
        "・<b>trades</b>: 当日の取引件数 / 上限 100<br>"
        "・<b>連敗</b>: 連続損失数 / 上限 5。3 連敗で size 自動半減"
        "<hr><b>判断</b><br>"
        "全部緑なら継続。1 件でも ⚠ なら停止条件タブで詳細確認。"
    ),
    "exec_tabs": (
        "<b>3 タブで実行レイヤ全体を把握</b><hr>"
        "・<b>ポジション</b>: 保有中のポジ一覧。PnL マイナスの長期保有は塩漬けリスク<br>"
        "・<b>シグナル</b>: 受信した signal と処理状態。⏭が多い→リスク厳しすぎ、❌が多い→CLOB 接続不調<br>"
        "・<b>fills</b>: 直近約定の latency / slippage / PnL。ms > 3000 や slip% > 1 は要対処"
        "<hr><b>異常検知</b><br>"
        "・ポジションが突然増えた → 設定ミスで全 signal を copy<br>"
        "・シグナルが止まった → indexer 停止<br>"
        "・fills の slippage が高い → RPC ノード不調"
    ),
    "mgmt_tabs": (
        "<b>3 タブの使い分け</b><hr>"
        "・<b>Watchlist</b>: copy 対象 wallet の追加 / 削除。"
        "Strategy で発掘した上位 wallet をここに登録<br>"
        "・<b>Jobs</b>: backend job の実行履歴。phase0 / backfill / rank などの確認<br>"
        "・<b>手動 order</b>: 緊急時の手動発注。通常は使わない"
        "<hr><b>運用</b><br>"
        "週次で Watchlist を update、月次で Jobs の FAILED を Ops で深掘り。"
    ),
    "rollout": (
        "<b>段階的ロールアウト</b><hr>"
        "4 段階で資金規模を徐々に拡大する仕組み。"
        "<hr><b>各 phase の意味</b><br>"
        "・<b>A Paper</b>: 実発注なし、シミュのみ (4 週)<br>"
        "・<b>B Micro</b>: $10/trade、検証スタート (4 週)<br>"
        "・<b>C Small</b>: $50/trade、本格運用準備 (8 週)<br>"
        "・<b>D Scale</b>: 拡大運用、月次レビュー必須"
        "<hr><b>進行</b><br>"
        "緑 ✓ = 完了、青 ● = 現在、灰 = 未到達。"
        "オレンジバー = 現フェーズ内の経過日数。"
        "<hr><b>判断</b><br>"
        "昇格条件 7/7 + 停止条件 0 ヒット で「昇格」ボタンが活性化。"
    ),
    "promo": (
        "<b>次フェーズへの 7 条件</b><hr>"
        "全て ✅ になると「昇格」ボタンが活性化。"
        "<hr><b>各条件</b><br>"
        "・<b>経過 ≥ 28d</b>: 最低検証期間 (短いと偶然のリスク)<br>"
        "・<b>ROI ≥ +3%</b>: 累積利益が一定以上<br>"
        "・<b>DD ≤ 8%</b>: 最大下落幅が許容内<br>"
        "・<b>勝率 ≥ 52%</b>: コイントス以上の勝率<br>"
        "・<b>乖離 ≤ 20%</b>: backtest 予測 vs 実績の差<br>"
        "・<b>Latency ≤ 3000ms</b>: 執行速度<br>"
        "・<b>kill switch test</b>: 停止機能の動作確認"
        "<hr><b>判断</b><br>"
        "⏳ が残ってる項目は時間 / 改善で達成。達成不能なら戦略再検討。"
    ),
    "halt": (
        "<b>即停止すべき 7 条件</b><hr>"
        "いずれか 1 件でも 🛑 になったら kill switch を ON。"
        "<hr><b>各条件</b><br>"
        "・<b>日次 PnL &lt; -5%</b>: 当日の急落<br>"
        "・<b>7d PnL &lt; -8%</b>: 週次の継続損失<br>"
        "・<b>連敗 ≥ 5</b>: 戦略の機能不全<br>"
        "・<b>単一 market &gt; 25%</b>: 集中投資、相場急変で大損<br>"
        "・<b>indexer lag &gt; 120s</b>: データが古い、判断不能<br>"
        "・<b>USDC &lt; $500</b>: 残高不足、新規発注不可<br>"
        "・<b>MATIC &lt; 1.0</b>: ガス枯渇"
        "<hr><b>対処</b><br>"
        "🛑 が出たら原因を Ops で確認、解決してから手動で kill switch 解除。"
    ),
}

st.markdown(
    f"# Execute {help_icon(HELP['page'])}　"
    "<small style='font-size:0.7rem;color:#888;'>Phase B Micro — 18/28日 / $10 per trade</small>",
    unsafe_allow_html=True,
)

rng = np.random.default_rng(7)

sb = st.columns([1, 1, 1, 1, 1, 1, 1.2])
sb[0].metric("USDC", "$8,432", "-$120",
             help="Polygon 上の USDC 残高。発注の元手。"
                  "$500 以下で停止条件にヒット、自動発注停止。")
sb[1].metric("MATIC", "12.4", "OK",
             help="Polygon ガス用の MATIC。1.0 未満で発注不能。")
sb[2].metric("オープン", "7", "$3,210",
             help="保有ポジション数 / 総額。"
                  "多すぎ (>15) は管理不能、少なすぎ (<3) は分散効果薄い。")
sb[3].metric("今日 PnL", "+$184", "+2.2%",
             help="本日 0:00 UTC 起算の実現 PnL。"
                  "-5% で日次停止条件ヒット、-3% で警戒モード。")
sb[4].metric("Sharpe 30d", "1.42", "+0.08",
             help="直近 30 日の Sharpe ratio。"
                  "> 1.0 良好、< 0.5 劣化、< 0 戦略破綻。週次レビューの主指標。")
sb[5].metric("phase 累計", "+$72", "+$8 (24h)",
             help="現 rollout phase 開始からの累計 PnL。"
                  "phase 完了時の昇格判断に使う。")
with sb[6]:
    st.markdown(help_icon(HELP["killswitch"]), unsafe_allow_html=True)
    kill = st.toggle("Kill Switch", value=False, key="kill_mock")
    if kill:
        st.error("🛑 HALTED")
    else:
        st.success("🟢 LIVE")

r1 = st.columns([1, 1.3, 1.4])

with r1[0], st.container(border=True):
    st.markdown(f"##### リスク {help_icon(HELP['risk'])}",
                unsafe_allow_html=True)
    g = go.Figure(go.Indicator(
        mode="gauge+number", value=3.2,
        number={"suffix": "%", "valueformat": ".1f", "font": {"size": 20}},
        title={"text": "今日 DD", "font": {"size": 10}},
        gauge={"axis": {"range": [0, 8], "tickfont": {"size": 8}},
               "bar": {"color": "#d9534f"},
               "steps": [{"range": [0, 4], "color": "#e7f6e7"},
                         {"range": [4, 6.4], "color": "#fff3cd"},
                         {"range": [6.4, 8], "color": "#f8d7da"}],
               "threshold": {"line": {"color": "red", "width": 3},
                             "thickness": 0.75, "value": 8}}))
    g.update_layout(height=140, margin=dict(t=20, b=0, l=10, r=10))
    st.plotly_chart(g, use_container_width=True)
    st.progress(0.43, text="exposure 43/70%")
    st.progress(1.0, text="単一 token 27/25% ⚠")
    st.progress(0.62, text="trades 62/100")
    st.progress(0.38, text="連敗 2/5")

with r1[1], st.container(border=True):
    hc1, hc2 = st.columns([5, 1])
    with hc1:
        st.markdown("##### 実行レイヤ")
    with hc2:
        st.markdown(help_icon(HELP["exec_tabs"]), unsafe_allow_html=True)
    tab_pos, tab_sig, tab_fill = st.tabs(["ポジション", "シグナル", "fills"])
    with tab_pos:
        pos = pd.DataFrame({
            "market": ["米大統領 — Dem", "FRB 6月 — Yes", "BTC>$150k — Yes",
                       "AI — No", "G7 — Yes", "WC — Brazil", "投票率 — Yes"],
            "side": ["B", "B", "B", "S", "B", "B", "B"],
            "size": [320, 250, 480, 410, 200, 180, 1370],
            "PnL": [22.8, 13.6, 80.0, 12.0, -2.8, -30.0, 90.2],
            "保有": ["2h", "5h", "1d", "3d", "12h", "8h", "30m"],
        })
        st.dataframe(pos, use_container_width=True, hide_index=True, height=220,
                     column_config={
                         "size": st.column_config.NumberColumn(format="$%d"),
                         "PnL": st.column_config.NumberColumn(format="$%+.1f"),
                     })
    with tab_sig:
        now = datetime.now(UTC)
        sig = pd.DataFrame({
            "時刻": [(now - timedelta(seconds=int(s))).strftime("%H:%M:%S")
                     for s in sorted(rng.integers(5, 900, 8))],
            "wallet": [f"0x{rng.integers(0, 16**8):08x}" for _ in range(8)],
            "market": rng.choice(["米大統領", "FRB", "BTC", "AI"], 8),
            "side": rng.choice(["B", "S"], 8).tolist(),
            "price": [round(float(rng.uniform(0.1, 0.9)), 3) for _ in range(8)],
            "状態": rng.choice(["✅", "⏳", "❌", "⏭"], 8, p=[0.5, 0.2, 0.1, 0.2]).tolist(),
        })
        st.dataframe(sig, use_container_width=True, hide_index=True, height=220)
    with tab_fill:
        fills = pd.DataFrame({
            "時刻": [(datetime.now(UTC) - timedelta(seconds=int(s))).strftime("%H:%M:%S")
                     for s in sorted(rng.integers(30, 7200, 8))],
            "market": rng.choice(["米大統領", "FRB", "BTC", "AI", "WC"], 8),
            "side": rng.choice(["B", "S"], 8).tolist(),
            "size": [int(rng.choice([50, 100, 150, 200])) for _ in range(8)],
            "ms": [int(rng.normal(850, 280)) for _ in range(8)],
            "slip%": [round(float(rng.normal(0.4, 0.6)), 2) for _ in range(8)],
            "PnL": [round(float(rng.normal(2, 12)), 2) for _ in range(8)],
        })
        st.dataframe(fills, use_container_width=True, hide_index=True, height=220,
                     column_config={
                         "size": st.column_config.NumberColumn(format="$%d"),
                         "ms": st.column_config.NumberColumn(format="%d"),
                         "slip%": st.column_config.NumberColumn(format="%+.2f"),
                         "PnL": st.column_config.NumberColumn(format="$%+.1f"),
                     })

with r1[2], st.container(border=True):
    hc1, hc2 = st.columns([5, 1])
    with hc1:
        st.markdown("##### 管理オペレーション")
    with hc2:
        st.markdown(help_icon(HELP["mgmt_tabs"]), unsafe_allow_html=True)
    tab_wl, tab_jobs, tab_manual = st.tabs(["Watchlist", "Jobs", "手動 order"])
    ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

    def _addr_to_bytes(s: str) -> bytes | None:
        s = s.strip()
        if not ADDR_RE.match(s):
            return None
        return bytes.fromhex(s[2:].lower())

    with tab_wl:
        with st.form("add_wl"):
            ac1, ac2, ac3 = st.columns([3, 2, 1])
            a_str = ac1.text_input("address (0x...)", label_visibility="collapsed",
                                   placeholder="0x...")
            note = ac2.text_input("note", label_visibility="collapsed",
                                  placeholder="note")
            ok = ac3.form_submit_button("Add", type="primary",
                                        use_container_width=True)
            if ok:
                ab = _addr_to_bytes(a_str)
                if ab is None:
                    st.error("invalid address")
                else:
                    try:
                        with get_session() as s:
                            stmt = pg_insert(Watchlist).values(
                                address=ab, note=note or None, active=True,
                            )
                            stmt = stmt.on_conflict_do_update(
                                index_elements=[Watchlist.address],
                                set_={"note": stmt.excluded.note, "active": True},
                            )
                            s.execute(stmt)
                        st.success(f"added {short_addr(ab)}")
                    except Exception as e:  # noqa: BLE001
                        st.error(str(e))
        # Watchlist 一覧 + toggle / delete
        try:
            with get_session() as s:
                wl_rows = s.execute(
                    select(Watchlist).order_by(Watchlist.added_at.desc()).limit(20)
                ).scalars().all()
                wl_list = [(r.address, r.note, r.active, r.added_at) for r in wl_rows]
        except Exception as e:  # noqa: BLE001
            wl_list = []
            st.caption(f"db: {e}")

        for addr_b, wl_note, wl_active, wl_added in wl_list:
            addr_disp = "0x" + addr_b.hex()[:16] + "…"
            wc1, wc2, wc3, wc4 = st.columns([3, 2, 1, 1])
            wc1.markdown(
                f"<span style='font-size:0.75rem;font-family:monospace'>{addr_disp}</span>"
                + (f" <span style='color:#888;font-size:0.65rem'>{wl_note}</span>" if wl_note else ""),
                unsafe_allow_html=True,
            )
            wc2.caption(fmt_ago(wl_added))
            toggle_label = "🟢 active" if wl_active else "⚪ inactive"
            if wc3.button(toggle_label, key=f"wl_toggle_{addr_b.hex()[:8]}",
                          use_container_width=True):
                try:
                    from sqlalchemy import update as sa_update
                    with get_session() as s:
                        s.execute(
                            sa_update(Watchlist)
                            .where(Watchlist.address == addr_b)
                            .values(active=not wl_active)
                        )
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(str(e))
            if wc4.button("🗑", key=f"wl_del_{addr_b.hex()[:8]}",
                          use_container_width=True):
                try:
                    with get_session() as s:
                        row = s.get(Watchlist, addr_b)
                        if row:
                            s.delete(row)
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(str(e))

    with tab_jobs:
        try:
            with get_session() as s:
                rows = s.execute(
                    select(Job).order_by(desc(Job.created_at)).limit(15)
                ).scalars().all()
                jdata = [
                    {
                        "id": r.id, "kind": r.kind, "status": r.status,
                        "created": fmt_ago(r.created_at),
                        "finished": fmt_ago(r.finished_at) if r.finished_at else "—",
                    }
                    for r in rows
                ]
        except Exception as e:  # noqa: BLE001
            jdata = []
            st.caption(f"db: {e}")
        st.dataframe(jdata, use_container_width=True, hide_index=True, height=140)

        # Job live log (F17)
        from copytrader.db.models import JobLog
        jc1, jc2 = st.columns([2, 1])
        selected_jid = jc1.number_input(
            "Job ID でログを表示",
            min_value=1, step=1,
            value=jdata[0]["id"] if jdata and "id" in jdata[0] else 1,
            key="exec_job_id",
            label_visibility="collapsed",
        )
        auto_ref = jc2.checkbox("自動更新 (2s)", key="exec_auto_ref")

        @st.cache_data(ttl=2)
        def _exec_job_logs(jid: int) -> tuple[dict | None, list[str]]:
            try:
                with get_session() as s:
                    j = s.get(Job, jid)
                    if not j:
                        return None, []
                    logs = s.execute(
                        select(JobLog).where(JobLog.job_id == jid)
                        .order_by(JobLog.ts).limit(300)
                    ).scalars().all()
                    return (
                        {"status": j.status, "progress": j.progress,
                         "result": j.result, "error": j.error_text},
                        [f"[{lg.ts.strftime('%H:%M:%S')}] {lg.message}" for lg in logs],
                    )
            except Exception as e:  # noqa: BLE001
                return None, [str(e)]

        jmeta, jlogs = _exec_job_logs(int(selected_jid))
        if jmeta:
            sc = {"SUCCEEDED": "green", "FAILED": "red", "RUNNING": "orange"}.get(
                jmeta["status"], "gray"
            )
            st.markdown(
                f"<b style='color:{sc}'>{jmeta['status']}</b>"
                + (f" — {jmeta['error']}" if jmeta.get("error") else ""),
                unsafe_allow_html=True,
            )
            if jmeta.get("result"):
                st.json(jmeta["result"], expanded=False)
            if jlogs:
                st.code("\n".join(jlogs[-80:]), language=None)
            else:
                st.caption("ログなし")
        else:
            st.caption("job が見つかりません")

        if auto_ref:
            import time as _time
            _time.sleep(2)
            st.rerun()
    with tab_manual:
        with st.form("manual"):
            mc1, mc2 = st.columns(2)
            mc1.text_input("token_id", "0x1234abcd…", disabled=True)
            mc2.selectbox("side", ["BUY", "SELL"])
            mc1.number_input("size $", min_value=10, max_value=1000, value=50,
                             step=10)
            mc2.number_input("price", min_value=0.01, max_value=0.99, value=0.50,
                             step=0.01, format="%.2f")
            mc1.selectbox("TIF", ["GTC", "IOC", "FOK"])
            confirm = mc2.checkbox("リスク無視")
            st.form_submit_button("発注", type="primary",
                                  use_container_width=True, disabled=not confirm)

r2 = st.columns([1.5, 1, 1])

with r2[0], st.container(border=True):
    st.markdown(f"##### Rollout 進行 (A→B→C→D) {help_icon(HELP['rollout'])}",
                unsafe_allow_html=True)
    PHASES = [
        ("A", "Paper", 28, 0, "#9aa0a6"),
        ("B", "Micro", 28, 10, "#5b9bd5"),
        ("C", "Small", 56, 50, "#2c7fb8"),
        ("D", "Scale", 9999, 250, "#1a5490"),
    ]
    CUR, DAY = 1, 18
    stp = go.Figure()
    for i, (pid, name, dur, sz, col) in enumerate(PHASES):
        if i < CUR:
            color, op, suf = "#2ca02c", 1.0, " ✓"
        elif i == CUR:
            color, op, suf = col, 1.0, " ●"
        else:
            color, op, suf = "#cccccc", 0.5, ""
        stp.add_shape(type="rect", x0=i + 0.05, x1=i + 0.95, y0=0.35, y1=0.85,
                      fillcolor=color, opacity=op, line=dict(width=0))
        stp.add_annotation(
            x=i + 0.5, y=0.6, showarrow=False,
            text=f"<b>{pid}{suf}</b> {name}　<span style='font-size:8px;color:#eee'>{dur}d/${sz}</span>",
            font=dict(size=10, color="white" if op > 0.7 else "#666"))
        if i < len(PHASES) - 1:
            stp.add_annotation(x=i + 1, y=0.6, showarrow=False, text="→",
                               font=dict(size=14, color="#888"))
    prog = DAY / max(1, PHASES[CUR][2])
    stp.add_shape(type="rect", x0=CUR + 0.05,
                  x1=CUR + 0.05 + 0.9 * min(prog, 1.0),
                  y0=0.27, y1=0.32, fillcolor="#ff8c00", line=dict(width=0))
    stp.update_layout(height=70, margin=dict(t=0, b=0, l=5, r=5),
                      xaxis=dict(visible=False, range=[0, len(PHASES)]),
                      yaxis=dict(visible=False, range=[0, 1]),
                      plot_bgcolor="white")
    st.plotly_chart(stp, use_container_width=True, key="stepper")
    ac = st.columns(4)
    ac[0].button("→ C 昇格", type="primary", use_container_width=True,
                 disabled=True,
                 help="昇格条件 7/7 + 停止条件 0 のときだけ活性化。"
                      "現在: 5/7 + 1 ヒットなので不可。")
    ac[1].button("継続", use_container_width=True,
                 help="何もせず現フェーズを継続。デフォルト動作。")
    ac[2].button("← A 降格", use_container_width=True,
                 help="1 つ前の phase に戻す。重大な問題発生時に使う。")
    confirm_h = ac[3].checkbox(
        "HALT", help="緊急停止の確認。ON にしてから次のボタンで全自動発注停止。")
    st.button("🛑 全停止", use_container_width=True, disabled=not confirm_h,
              help="全自動発注を即停止 (Kill Switch ON と同等)。")

with r2[1], st.container(border=True):
    st.markdown(f"##### 昇格条件 (5/7) {help_icon(HELP['promo'])}",
                unsafe_allow_html=True)
    promo = [
        ("経過 ≥ 28d", False, "18日"),
        ("ROI ≥ +3%", True, "+4.2%"),
        ("DD ≤ 8%", True, "-5.1%"),
        ("勝率 ≥ 52%", True, "56.8%"),
        ("乖離 ≤ 20%", True, "12%"),
        ("Latency ≤ 3000ms", False, "3,420"),
        ("kill switch test", True, "3日前"),
    ]
    pdf = pd.DataFrame([
        {"条件": c, "現在": n, " ": "✅" if ok else "⏳"}
        for c, ok, n in promo
    ])
    st.dataframe(pdf, use_container_width=True, hide_index=True, height=185)

with r2[2], st.container(border=True):
    st.markdown(f"##### 停止条件 (1 ヒット ⚠) {help_icon(HELP['halt'])}",
                unsafe_allow_html=True)
    halt = [
        ("日次 PnL < -5%", False, "+0.9%"),
        ("7d PnL < -8%", False, "+2.1%"),
        ("連敗 ≥ 5", False, "2"),
        ("単一 market > 25%", True, "27%"),
        ("indexer lag > 120s", False, "18s"),
        ("USDC < $500", False, "$8,432"),
        ("MATIC < 1.0", False, "12.4"),
    ]
    hdf = pd.DataFrame([
        {"条件": c, "現在": n, " ": "🛑" if t else "🟢"}
        for c, t, n in halt
    ])
    st.dataframe(hdf, use_container_width=True, hide_index=True, height=185)
