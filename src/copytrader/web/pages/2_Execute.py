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
from copytrader.web.theme import (
    ACCENT_CYAN, ACCENT_GREEN, ACCENT_RED, ACCENT_YELLOW,
    LIVE_LAYOUT, LIVE_PALETTE, STATIC_LAYOUT, STATIC_PALETTE,
    TILE_BG, inject_theme,
)
from copytrader.web.format import fmt_ago, short_addr

st.set_page_config(page_title="Execute", layout="wide",
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


# ---------------------------------------------------------------------------
# Real-data accessors (graceful fall-through to mocks if DB is empty/down)
# ---------------------------------------------------------------------------

from copytrader.db import settings_table as _st  # noqa: E402
from copytrader.db.models import (  # noqa: E402
    Execution as ExecModel,
)
from copytrader.db.models import (
    Position as PosModel,
)
from copytrader.db.models import (
    RiskEvaluation,
)
from copytrader.db.models import (
    Signal as SigModel,
)
from copytrader.db.models import (
    TradePnl as TPModel,
)


@st.cache_data(ttl=5)
def _real_metrics() -> dict:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func, select

    out: dict = {"db_ok": True, "error": None}
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = datetime.now(UTC) - timedelta(days=7)
    month_ago = datetime.now(UTC) - timedelta(days=30)
    try:
        with get_session() as s:
            out["today_pnl"] = float(s.execute(
                select(func.coalesce(func.sum(TPModel.realized_usdc), 0))
                .where(TPModel.ts >= midnight)
            ).scalar_one())
            out["week_pnl"] = float(s.execute(
                select(func.coalesce(func.sum(TPModel.realized_usdc), 0))
                .where(TPModel.ts >= week_ago)
            ).scalar_one())
            out["month_pnl"] = float(s.execute(
                select(func.coalesce(func.sum(TPModel.realized_usdc), 0))
                .where(TPModel.ts >= month_ago)
            ).scalar_one())
            open_count, open_total = s.execute(
                select(
                    func.count().filter(PosModel.open_size_shares > 0),
                    func.coalesce(func.sum(PosModel.open_size_usdc), 0),
                ).select_from(PosModel)
            ).first() or (0, 0)
            out["open_count"] = int(open_count or 0)
            out["open_total_usdc"] = float(open_total or 0)
            # latest risk metrics
            latest_risk = s.execute(
                select(RiskEvaluation).order_by(RiskEvaluation.ts.desc()).limit(1)
            ).scalar_one_or_none()
            out["risk"] = {
                "allow": bool(latest_risk.allow_new) if latest_risk else True,
                "halted": list(latest_risk.halted_reasons or [])
                if latest_risk else [],
                "metrics": dict(latest_risk.metrics_snapshot or {})
                if latest_risk else {},
            }
    except Exception as e:  # noqa: BLE001
        out["db_ok"] = False
        out["error"] = str(e)
    out["usdc"] = float(_st.get("usdc_balance_cache") or 0.0)
    out["matic"] = float(_st.get("matic_balance_cache") or 0.0)
    out["kill_switch_on"] = bool(_st.get("kill_switch_on") or False)
    out["phase"] = str(_st.get("rollout_phase") or "A")
    return out


_M = _real_metrics()

sb = st.columns([1, 1, 1, 1, 1, 1, 1.2])
sb[0].metric(
    "USDC", f"${_M['usdc']:,.0f}" if _M["usdc"] else "—",
    help="Polygon 上の USDC 残高 (settings.usdc_balance_cache、execution layer 更新)。"
         "$500 以下で停止条件にヒット、自動発注停止。",
)
sb[1].metric(
    "MATIC", f"{_M['matic']:.1f}" if _M["matic"] else "—",
    help="Polygon ガス用の MATIC。1.0 未満で発注不能。",
)
sb[2].metric(
    "オープン", str(_M.get("open_count", 0)),
    f"${_M.get('open_total_usdc', 0):,.0f}",
    help="保有ポジション数 / 総額 (positions テーブル)。"
         "多すぎ (>15) は管理不能、少なすぎ (<3) は分散効果薄い。",
)
today_pnl = _M.get("today_pnl", 0.0)
sb[3].metric(
    "今日 PnL", f"${today_pnl:+,.2f}",
    delta_color="normal" if today_pnl >= 0 else "inverse",
    help="本日 0:00 UTC 起算の実現 PnL (trade_pnl テーブル)。"
         "-5% で日次停止条件ヒット、-3% で警戒モード。",
)
week_pnl = _M.get("week_pnl", 0.0)
sb[4].metric(
    "7d PnL", f"${week_pnl:+,.2f}",
    delta_color="normal" if week_pnl >= 0 else "inverse",
    help="過去 7 日の実現 PnL。週次トレンド指標。"
         "-8% で週次停止条件ヒット。",
)
month_pnl = _M.get("month_pnl", 0.0)
sb[5].metric(
    "30d PnL", f"${month_pnl:+,.2f}",
    help="過去 30 日の実現 PnL。月次レビューの主指標。",
)
with sb[6]:
    st.markdown(help_icon(HELP["killswitch"]), unsafe_allow_html=True)
    kill_default = _M.get("kill_switch_on", False)
    kill = st.toggle("Kill Switch", value=kill_default, key="kill_switch_live")
    if kill != kill_default:
        # User toggled — persist to settings
        try:
            from copytrader.db.models import AuditLog
            _st.set_("kill_switch_on", kill)
            with get_session() as _s:
                _s.add(AuditLog(actor="web", action=(
                    "kill_switch_on" if kill else "kill_switch_off"),
                    details={"via": "web_ui"}))
            st.toast(f"Kill switch → {'ON' if kill else 'OFF'}")
        except Exception as e:  # noqa: BLE001
            st.error(f"persist failed: {e}")
    if kill:
        st.error("🛑 HALTED")
    else:
        st.success("🟢 LIVE")
if not _M.get("db_ok"):
    st.caption(f"⚠️ DB アクセス失敗: {_M.get('error', '')[:80]}")

r1 = st.columns([1, 1.3, 1.4])

with r1[0], st.container(border=True):
    st.markdown(f"##### リスク {help_icon(HELP['risk'])}",
                unsafe_allow_html=True)
    rmet = _M.get("risk", {}).get("metrics", {})
    today_dd_pct = abs(float(rmet.get("today_pnl_pct", 0.0)))
    halt_limit = abs(float(_st.get("halt_daily_pnl_pct") or -5.0))
    g = go.Figure(go.Indicator(
        mode="gauge+number", value=today_dd_pct,
        number={"suffix": "%", "valueformat": ".1f",
                "font": {"size": 22, "color": "#fafafa"}},
        title={"text": "今日 DD", "font": {"size": 10, "color": "#7a8499"}},
        gauge={
            "axis": {"range": [0, halt_limit],
                     "tickfont": {"size": 8, "color": "#7a8499"}},
            "bar": {"color": ACCENT_RED},
            "bgcolor": TILE_BG,
            "bordercolor": "#1a2230",
            "steps": [{"range": [0, halt_limit * 0.5], "color": "#0d3320"},
                      {"range": [halt_limit * 0.5, halt_limit * 0.8],
                       "color": "#3d2f0a"},
                      {"range": [halt_limit * 0.8, halt_limit],
                       "color": "#3d0d12"}],
            "threshold": {"line": {"color": ACCENT_RED, "width": 3},
                          "thickness": 0.75, "value": halt_limit}}))
    g.update_layout(
        **{**LIVE_LAYOUT, "height": 140,
           "margin": dict(t=20, b=0, l=10, r=10)},
    )
    st.plotly_chart(g, use_container_width=True)
    # Live progress bars from risk_evaluations.metrics_snapshot
    exp_pct = float(rmet.get("total_exposure_pct", 0.0))
    exp_lim = float(_st.get("limit_total_exposure_pct") or 70.0)
    st.progress(min(exp_pct / max(exp_lim, 1), 1.0),
                text=f"exposure {exp_pct:.0f}/{exp_lim:.0f}%")
    single_pct = float(rmet.get("max_single_market_pct", 0.0))
    single_lim = float(_st.get("limit_single_token_pct") or 25.0)
    over = " ⚠" if single_pct > single_lim else ""
    st.progress(min(single_pct / max(single_lim, 1), 1.0),
                text=f"単一 token {single_pct:.0f}/{single_lim:.0f}%{over}")
    daily_trades = int(rmet.get("daily_trades", 0))
    trades_lim = int(_st.get("limit_daily_trades") or 100)
    st.progress(min(daily_trades / max(trades_lim, 1), 1.0),
                text=f"trades {daily_trades}/{trades_lim}")
    cl = int(rmet.get("consecutive_losses", 0))
    cl_lim = int(_st.get("halt_consecutive_losses") or 5)
    st.progress(min(cl / max(cl_lim, 1), 1.0),
                text=f"連敗 {cl}/{cl_lim}")

with r1[1], st.container(border=True):
    hc1, hc2 = st.columns([5, 1])
    with hc1:
        st.markdown("##### 実行レイヤ")
    with hc2:
        st.markdown(help_icon(HELP["exec_tabs"]), unsafe_allow_html=True)
    tab_pos, tab_sig, tab_fill = st.tabs(["ポジション", "シグナル", "fills"])
    with tab_pos:
        try:
            with get_session() as s:
                rows = s.execute(
                    select(PosModel).where(PosModel.open_size_shares > 0)
                    .order_by(PosModel.open_size_usdc.desc()).limit(15)
                ).scalars().all()
                pos_data = [
                    {
                        "market": r.market_label or str(r.token_id)[:14] + "…",
                        "side": "B" if int(r.side) == 0 else "S",
                        "size": float(r.open_size_usdc),
                        "entry": float(r.avg_price),
                        "保有": fmt_ago(r.opened_at),
                    }
                    for r in rows
                ]
        except Exception as e:  # noqa: BLE001
            pos_data = []
            st.caption(f"db: {e}")
        if not pos_data:
            st.caption("(オープンポジションなし)")
        st.dataframe(
            pos_data, use_container_width=True, hide_index=True, height=220,
            column_config={
                "size": st.column_config.NumberColumn(format="$%.0f"),
                "entry": st.column_config.NumberColumn(format="%.3f"),
            },
        )
    with tab_sig:
        try:
            with get_session() as s:
                rows = s.execute(
                    select(SigModel)
                    .order_by(SigModel.id.desc()).limit(15)
                ).scalars().all()
                status_icon = {
                    "PENDING": "⏳", "EXECUTING": "⏳", "EXECUTED": "✅",
                    "SKIPPED": "⏭", "REJECTED": "❌", "LEGACY": "·",
                }
                sig_data = [
                    {
                        "時刻": r.detected_at.strftime("%H:%M:%S")
                        if r.detected_at else r.ts.strftime("%H:%M:%S"),
                        "wallet": "0x" + r.address.hex()[:8],
                        "side": "B" if int(r.side) == 0 else "S",
                        "price": float(r.price),
                        "size": float(r.size_usdc),
                        " ": status_icon.get(r.status, r.status[:2]),
                        "reason": r.skip_reason or "",
                    }
                    for r in rows
                ]
        except Exception as e:  # noqa: BLE001
            sig_data = []
            st.caption(f"db: {e}")
        if not sig_data:
            st.caption("(シグナル受信なし — Watchlist の wallet が発注すると現れる)")
        st.dataframe(
            sig_data, use_container_width=True, hide_index=True, height=220,
            column_config={
                "price": st.column_config.NumberColumn(format="%.3f"),
                "size": st.column_config.NumberColumn(format="$%.0f"),
            },
        )
    with tab_fill:
        try:
            with get_session() as s:
                rows = s.execute(
                    select(ExecModel)
                    .where(ExecModel.status.in_(["FILLED", "PARTIAL"]))
                    .order_by(ExecModel.placed_at.desc()).limit(15)
                ).scalars().all()
                fills_data = [
                    {
                        "時刻": r.fill_time.strftime("%H:%M:%S")
                        if r.fill_time else r.placed_at.strftime("%H:%M:%S"),
                        "token": str(r.token_id)[:8] + "…",
                        "side": "B" if int(r.side) == 0 else "S",
                        "size": float(r.size_usdc),
                        "price": float(r.filled_price or r.limit_price),
                        "ms": r.signal_to_place_ms or 0,
                    }
                    for r in rows
                ]
        except Exception as e:  # noqa: BLE001
            fills_data = []
            st.caption(f"db: {e}")
        if not fills_data:
            st.caption("(約定なし — execution_enabled=true で動き始める)")
        st.dataframe(
            fills_data, use_container_width=True, hide_index=True, height=220,
            column_config={
                "size": st.column_config.NumberColumn(format="$%.0f"),
                "price": st.column_config.NumberColumn(format="%.3f"),
                "ms": st.column_config.NumberColumn(format="%d ms"),
            },
        )

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
        try:
            with get_session() as s:
                rows = s.execute(
                    select(Watchlist).order_by(Watchlist.added_at.desc()).limit(20)
                ).scalars().all()
                wdata = [
                    {
                        "address": "0x" + r.address.hex()[:16] + "…",
                        "note": r.note,
                        "active": r.active,
                        "added": fmt_ago(r.added_at),
                    }
                    for r in rows
                ]
        except Exception as e:  # noqa: BLE001
            wdata = []
            st.caption(f"db: {e}")
        st.dataframe(wdata, use_container_width=True, hide_index=True, height=160)
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
        st.dataframe(jdata, use_container_width=True, hide_index=True, height=220)
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
        ("A", "Paper", 28, 0, "#475569"),
        ("B", "Micro", 28, 10, "#3aa3ff"),
        ("C", "Small", 56, 50, "#1d4ed8"),
        ("D", "Scale", 9999, 250, "#7c3aed"),
    ]
    CUR, DAY = 1, 18
    stp = go.Figure()
    for i, (pid, name, dur, sz, col) in enumerate(PHASES):
        if i < CUR:
            color, op, suf = ACCENT_GREEN, 1.0, " ✓"
        elif i == CUR:
            color, op, suf = col, 1.0, " ●"
        else:
            color, op, suf = "#1f2937", 1.0, ""
        stp.add_shape(type="rect", x0=i + 0.05, x1=i + 0.95, y0=0.35, y1=0.85,
                      fillcolor=color, opacity=op,
                      line=dict(width=1, color="#1a2230"))
        text_color = "#fafafa" if i <= CUR else "#7a8499"
        stp.add_annotation(
            x=i + 0.5, y=0.6, showarrow=False,
            text=f"<b>{pid}{suf}</b> {name}　<span style='font-size:8px'>{dur}d/${sz}</span>",
            font=dict(size=10, color=text_color))
        if i < len(PHASES) - 1:
            stp.add_annotation(x=i + 1, y=0.6, showarrow=False, text="→",
                               font=dict(size=14, color="#475569"))
    prog = DAY / max(1, PHASES[CUR][2])
    stp.add_shape(type="rect", x0=CUR + 0.05,
                  x1=CUR + 0.05 + 0.9 * min(prog, 1.0),
                  y0=0.27, y1=0.32, fillcolor=ACCENT_YELLOW, line=dict(width=0))
    stp.update_layout(
        **{**LIVE_LAYOUT, "height": 70,
           "margin": dict(t=0, b=0, l=5, r=5),
           "xaxis": dict(visible=False, range=[0, len(PHASES)]),
           "yaxis": dict(visible=False, range=[0, 1]),
           "plot_bgcolor": "rgba(0,0,0,0)"},
    )
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
