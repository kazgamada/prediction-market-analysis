"""Ops — Status + Settings + Diagnostics with hover help."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import streamlit as st
from sqlalchemy import desc, func, select

from copytrader.chain.errors import redact_url
from copytrader.config import settings
from copytrader.db import settings_table
from copytrader.db.engine import get_session
from copytrader.db.models import Cursor, Job, RiskEvent, RpcDeadLetter, Trade
from copytrader.indexer.backfill import CURSOR_NAME
from copytrader.web.auth import require_password
from copytrader.web.format import fmt_ago

st.set_page_config(page_title="Ops", layout="wide",
                   initial_sidebar_state="collapsed")
require_password()

st.markdown("""
<style>
.block-container { padding-top: 0.6rem !important; padding-bottom: 0.4rem !important; max-width: 100% !important; }
[data-testid="stMetric"] { padding: 0.1rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.7rem !important; }
[data-testid="stMetricValue"] { font-size: 1.0rem !important; }
h1, h3, h4, h5 { padding: 0 !important; margin: 0.2rem 0 !important; }
h1 { font-size: 1.2rem !important; }
h5 { font-size: 0.85rem !important; }
hr { margin: 0.3rem 0 !important; }
.stDataFrame { font-size: 0.72rem !important; }
[data-testid="stVerticalBlockBorderWrapper"] { padding: 0.3rem 0.5rem !important; }
.stButton button { padding: 0.2rem 0.5rem !important; font-size: 0.78rem !important; }
input, textarea, .stNumberInput input, .stSelectbox div { font-size: 0.78rem !important; }
.stTabs [data-baseweb="tab"] { padding: 0.2rem 0.5rem !important; font-size: 0.78rem !important; }
code { font-size: 0.7rem !important; }
.help-tip { position: relative; cursor: help; font-size: 0.85rem;
  display: inline-block; margin-left: 0.2rem; opacity: 0.55;
  color: #2c7fb8; font-weight: bold; }
.help-tip:hover { opacity: 1; }
.help-tip .help-popup { visibility: hidden; position: absolute; z-index: 9999;
  width: 340px; background: #1f2933; color: #f7fafc;
  padding: 10px 14px; border-radius: 6px;
  font-size: 0.75rem; line-height: 1.55; font-weight: normal;
  left: 0; top: 1.4rem; white-space: normal; text-align: left;
  box-shadow: 0 6px 18px rgba(0,0,0,0.35); pointer-events: none; }
.help-tip:hover .help-popup { visibility: visible; }
.help-tip .help-popup b { color: #ffd166; }
.help-tip .help-popup hr { border: 0; border-top: 1px solid #4a5568; margin: 6px 0; }
</style>
""", unsafe_allow_html=True)


def help_icon(text: str) -> str:
    return f'<span class="help-tip">ⓘ<span class="help-popup">{text}</span></span>'


HELP = {
    "page": (
        "<b>このページの目的</b><hr>"
        "障害対応 / 設定変更 / 詳細ログを見る画面。"
        "通常運用では開かない、何かおかしい時だけ開く。"
        "<hr><b>主な用途</b><br>"
        "1. ステータスバー: indexer / DB の health check<br>"
        "2. Build/Cursors/Dead-letters: 障害原因の絞り込み<br>"
        "3. Settings: ランタイム設定の調整<br>"
        "4. Recent jobs / Risk events: 履歴の深掘り"
    ),
    "build": (
        "<b>稼働中のバージョンと環境</b><hr>"
        "deploy 直後に「期待したコードが動いているか」を確認する場所。"
        "<hr><b>主要項目</b><br>"
        "・<b>git_sha</b>: コミットハッシュ。GitHub の最新と一致するか<br>"
        "・<b>build_time</b>: イメージビルド日時<br>"
        "・<b>window_days</b>: indexer の backfill 期間<br>"
        "・<b>rpc_http / ws</b>: Polygon RPC エンドポイント (秘匿)。"
        "unset なら indexer 機能不全"
    ),
    "cursors": (
        "<b>indexer 進捗カーソル</b><hr>"
        "各 cursor = 何かを処理する worker の「ここまで処理した」記録。"
        "<hr><b>正常時</b><br>"
        "updated が数分以内に更新され続ける。"
        "<hr><b>異常時</b><br>"
        "updated が古い (&gt; 5 分): worker 停止。"
        "block 値が逆戻り: バグ、即停止して原因究明。"
    ),
    "deadletter": (
        "<b>処理失敗した RPC chunk</b><hr>"
        "indexer が backfill 中に失敗した chunk を後で再試行するためのキュー。"
        "<hr><b>列の見方</b><br>"
        "・<b>id</b>: 内部 id<br>"
        "・<b>retries</b>: 何回再試行したか (上限 3)<br>"
        "・<b>next</b>: 次回再試行までの待ち時間"
        "<hr><b>判断</b><br>"
        "0 件 = 正常。少数 = 一時的なネット不調、放置で OK。"
        "100 件超 = RPC ノード変更を検討。"
    ),
    "settings": (
        "<b>ランタイム設定の上書き</b><hr>"
        "コードのデフォルト値より優先される DB 設定。"
        "再デプロイ無しに挙動を変えられる緊急避難レバー。"
        "<hr><b>主要キー</b><br>"
        "・<b>rank_min_trades</b>: ランキング対象の最低取引数 (デフォルト 30)<br>"
        "・<b>rank_min_volume_usdc</b>: 最低 volume (デフォルト 5000)<br>"
        "・<b>replay_default_delays</b>: デフォルト遅延秒の配列<br>"
        "・<b>exchange_addresses</b>: CTF Exchange アドレス (通常変えない)<br>"
        "・<b>order_filled_topic0</b>: イベントトピック (通常変えない)"
        "<hr><b>使い方</b><br>"
        "JSON で値入力 → Save。現在の override は下に JSON 表示。"
    ),
    "history_tabs": (
        "<b>2 タブの使い分け</b><hr>"
        "・<b>Recent jobs</b>: 直近 15 件の全 job。"
        "phase0 / backfill / rank / replay の実行履歴。FAILED 連発なら DB / RPC 不調<br>"
        "・<b>Risk events</b>: システムが記録した risk 履歴 "
        "(alert=重 / warn=中 / info=軽)。alert が出ているなら必ず深掘り"
        "<hr><b>運用</b><br>"
        "・日次: Risk events で alert が無いか確認<br>"
        "・週次: Recent jobs で FAILED 比率を確認"
    ),
}


st.markdown(
    f"# Ops {help_icon(HELP['page'])}　"
    "<small style='font-size:0.7rem;color:#888;'>indexer / settings / diagnostics</small>",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=5)
def _status_snapshot() -> dict:
    try:
        with get_session() as s:
            cur = s.get(Cursor, CURSOR_NAME)
            one_h_ago = datetime.now(UTC) - timedelta(hours=1)
            trades_1h = int(
                s.execute(
                    select(func.count()).select_from(Trade)
                    .where(Trade.ts >= one_h_ago)
                ).scalar_one()
            )
            trades_total = int(
                s.execute(select(func.count()).select_from(Trade)).scalar_one()
            )
            dl_pending = int(
                s.execute(
                    select(func.count()).select_from(RpcDeadLetter)
                    .where(RpcDeadLetter.resolved_at.is_(None))
                ).scalar_one()
            )
            last_risk = s.execute(
                select(RiskEvent).order_by(RiskEvent.ts.desc()).limit(1)
            ).scalar_one_or_none()
            return {
                "cursor_block": cur.last_block if cur else None,
                "cursor_updated_at": cur.updated_at if cur else None,
                "trades_1h": trades_1h,
                "trades_total": trades_total,
                "dl_pending": dl_pending,
                "last_risk_kind": last_risk.kind if last_risk else None,
                "last_risk_msg": last_risk.message if last_risk else None,
                "last_risk_ts": last_risk.ts if last_risk else None,
                "db_error": None,
            }
    except Exception as e:  # noqa: BLE001
        return {"db_error": str(e)}


snap = _status_snapshot()
sb = st.columns(5)
if snap.get("db_error"):
    sb[0].error(f"db: {snap['db_error'][:40]}")
else:
    sb[0].metric(
        "cursor block",
        f"{snap['cursor_block']:,}" if snap["cursor_block"] else "—",
        fmt_ago(snap["cursor_updated_at"]) if snap["cursor_updated_at"] else "",
        help="indexer が処理した最新ブロック番号 + 最終更新時刻。"
             "updated が 5 分以上止まっていたら indexer 停止疑い。"
             "Fly.io ダッシュボードで indexer マシン状態を確認。",
    )
    sb[1].metric(
        "trades (1h)", f"{snap['trades_1h']:,}",
        help="直近 1 時間で取得した trade 件数。"
             "通常時で数十〜数百件。0 が続くなら indexer 停止または市場閑散。",
    )
    sb[2].metric(
        "trades (total)", f"{snap['trades_total']:,}",
        help="DB に蓄積した全 trade 件数。容量管理の参考 (1M 件超で性能影響)。",
    )
    sb[3].metric(
        "dead-letters", snap["dl_pending"],
        delta_color="inverse" if snap["dl_pending"] > 0 else "off",
        help="未解決の RPC エラー chunk 数。0 が理想。"
             "10 件超で警戒、100 件超なら手動 retry を検討。",
    )
    if snap["last_risk_kind"]:
        sb[4].metric(
            "last risk", snap["last_risk_kind"],
            fmt_ago(snap["last_risk_ts"]), delta_color="inverse",
            help="システムが記録した最後の risk event。"
                 "kind 例: rpc_failure / cursor_stuck / dead_letter_spike など。"
                 "詳細は右の Risk events タブで確認。",
        )
    else:
        sb[4].metric("last risk", "—", "clean",
                     help="risk event 記録なし。システム健全。")

r = st.columns([1.1, 1, 1.2])

with r[0], st.container(border=True):
    st.markdown(f"##### Build / Env {help_icon(HELP['build'])}",
                unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:0.75rem; line-height:1.4'>"
        f"<b>git_sha</b>: <code>{settings.git_sha}</code><br>"
        f"<b>build_time</b>: <code>{settings.build_time}</code><br>"
        f"<b>window_days</b>: {settings.indexer_window_days}<br>"
        f"<b>rpc_http</b>: <code>{redact_url(settings.polygon_rpc_http) or '(unset)'}</code><br>"
        f"<b>rpc_ws</b>: <code>{redact_url(settings.polygon_rpc_ws) or '(unset)'}</code>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(f"##### Cursors {help_icon(HELP['cursors'])}",
                unsafe_allow_html=True)
    try:
        with get_session() as s:
            cursors = s.execute(select(Cursor)).scalars().all()
            for c in cursors:
                st.markdown(
                    f"<div style='font-size:0.75rem'>"
                    f"<b>{c.name}</b>: {c.last_block:,} "
                    f"<span style='color:#888'>({fmt_ago(c.updated_at)})</span></div>",
                    unsafe_allow_html=True,
                )
            if not cursors:
                st.caption("no cursors yet")
    except Exception as e:  # noqa: BLE001
        st.caption(f"db: {e}")
    st.markdown(f"##### Dead-letters {help_icon(HELP['deadletter'])}",
                unsafe_allow_html=True)
    try:
        with get_session() as s:
            rows = s.execute(
                select(RpcDeadLetter)
                .where(RpcDeadLetter.resolved_at.is_(None))
                .order_by(RpcDeadLetter.next_retry).limit(5)
            ).scalars().all()
            if not rows:
                st.caption("none")
            for r_ in rows:
                st.markdown(
                    f"<div style='font-size:0.7rem'>id={r_.id} retries={r_.retries} "
                    f"next={fmt_ago(r_.next_retry)}</div>",
                    unsafe_allow_html=True,
                )
    except Exception as e:  # noqa: BLE001
        st.caption(f"db: {e}")

with r[1], st.container(border=True):
    st.markdown(f"##### Settings overrides {help_icon(HELP['settings'])}",
                unsafe_allow_html=True)
    KNOWN_KEYS = [
        "exchange_addresses",
        "order_filled_topic0",
        "rank_min_trades",
        "rank_min_volume_usdc",
        "replay_default_delays",
    ]
    with st.form("setting"):
        key = st.selectbox("key", KNOWN_KEYS + ["(custom)"],
                           label_visibility="collapsed")
        if key == "(custom)":
            key = st.text_input("custom key", label_visibility="collapsed",
                                placeholder="custom key").strip()
        raw = st.text_area("value (JSON)", "", height=70,
                           label_visibility="collapsed", placeholder="JSON value")
        bc1, bc2 = st.columns(2)
        save = bc1.form_submit_button("Save", type="primary",
                                      use_container_width=True)
        delete = bc2.form_submit_button("Delete", use_container_width=True)
        if save and key:
            try:
                v = json.loads(raw) if raw.strip() else None
                if v is not None:
                    settings_table.set_(key, v)
                    st.success(f"saved {key}")
            except json.JSONDecodeError as e:
                st.error(f"JSON: {e}")
            except Exception as e:  # noqa: BLE001
                st.error(str(e))
        if delete and key:
            from copytrader.db.models import Setting
            try:
                with get_session() as s:
                    row = s.get(Setting, key)
                    if row:
                        s.delete(row)
                        st.success(f"deleted {key}")
            except Exception as e:  # noqa: BLE001
                st.error(str(e))
    try:
        all_overrides = settings_table.all_()
        if all_overrides:
            st.json(all_overrides, expanded=False)
        else:
            st.caption("no overrides set")
    except Exception as e:  # noqa: BLE001
        st.caption(f"db: {e}")

with r[2], st.container(border=True):
    hc1, hc2 = st.columns([5, 1])
    with hc1:
        st.markdown("##### システム履歴")
    with hc2:
        st.markdown(help_icon(HELP["history_tabs"]), unsafe_allow_html=True)
    tab_jobs, tab_risk = st.tabs(["Recent jobs", "Risk events"])
    with tab_jobs:
        try:
            with get_session() as s:
                rows = s.execute(
                    select(Job).order_by(desc(Job.id)).limit(15)
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
        st.dataframe(jdata, use_container_width=True, hide_index=True, height=300)
    with tab_risk:
        try:
            with get_session() as s:
                rows = s.execute(
                    select(RiskEvent).order_by(desc(RiskEvent.ts)).limit(15)
                ).scalars().all()
                if not rows:
                    st.success("no risk events")
                for r_ in rows:
                    sev = {1: "info", 2: "warn", 3: "alert"}.get(
                        r_.severity, str(r_.severity)
                    )
                    st.markdown(
                        f"<div style='font-size:0.72rem'>"
                        f"<b>[{sev}]</b> {r_.kind} "
                        f"<span style='color:#888'>({fmt_ago(r_.ts)})</span>: "
                        f"{r_.message}</div>",
                        unsafe_allow_html=True,
                    )
        except Exception as e:  # noqa: BLE001
            st.caption(f"db: {e}")
