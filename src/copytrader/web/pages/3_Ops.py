"""Ops — Status + Settings + Diagnostics on single viewport."""
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
</style>
""", unsafe_allow_html=True)

st.markdown("# Ops　<small style='font-size:0.7rem;color:#888;'>indexer / settings / diagnostics</small>",
            unsafe_allow_html=True)


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
    sb[0].metric("cursor block",
                 f"{snap['cursor_block']:,}" if snap["cursor_block"] else "—",
                 fmt_ago(snap["cursor_updated_at"]) if snap["cursor_updated_at"] else "")
    sb[1].metric("trades (1h)", f"{snap['trades_1h']:,}")
    sb[2].metric("trades (total)", f"{snap['trades_total']:,}")
    sb[3].metric("dead-letters", snap["dl_pending"],
                 delta_color="inverse" if snap["dl_pending"] > 0 else "off")
    if snap["last_risk_kind"]:
        sb[4].metric("last risk", snap["last_risk_kind"],
                     fmt_ago(snap["last_risk_ts"]), delta_color="inverse")
    else:
        sb[4].metric("last risk", "—", "clean")

r = st.columns([1.1, 1, 1.2])

with r[0], st.container(border=True):
    st.markdown("##### Build / Env")
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
    st.markdown("##### Cursors")
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
    st.markdown("##### Dead-letters (pending)")
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
    st.markdown("##### Settings overrides")
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
