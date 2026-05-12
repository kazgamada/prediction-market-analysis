"""Diagnostics page (F23): cursor / settings / last N risk events / dead-letters / build."""
from __future__ import annotations

import streamlit as st
from sqlalchemy import desc, func, select

from copytrader.chain.errors import redact_url
from copytrader.config import settings
from copytrader.db import settings_table
from copytrader.db.engine import get_session
from copytrader.db.models import Cursor, Job, RiskEvent, RpcDeadLetter
from copytrader.web.auth import require_password
from copytrader.web.format import fmt_ago

st.set_page_config(page_title="Diagnostics", layout="wide")
require_password()
st.title("Diagnostics")

with st.expander("Build", expanded=True):
    st.write({
        "git_sha": settings.git_sha,
        "build_time": settings.build_time,
        "window_days": settings.indexer_window_days,
        "rpc_http": redact_url(settings.polygon_rpc_http) or "(unset)",
        "rpc_ws": redact_url(settings.polygon_rpc_ws) or "(unset)",
    })

with st.expander("Cursors", expanded=True):
    with get_session() as s:
        cursors = s.execute(select(Cursor)).scalars().all()
        for c in cursors:
            st.write(f"{c.name}: block={c.last_block:,}  updated={fmt_ago(c.updated_at)}")
        if not cursors:
            st.info("no cursors yet")

with st.expander("Settings overrides"):
    overrides = settings_table.all_()
    if overrides:
        st.json(overrides)
    else:
        st.info("no overrides")

with st.expander("Recent risk events"):
    with get_session() as s:
        rows = s.execute(
            select(RiskEvent).order_by(desc(RiskEvent.ts)).limit(20)
        ).scalars().all()
        if not rows:
            st.success("no risk events recorded")
        for r in rows:
            sev = {1: "info", 2: "warn", 3: "alert"}.get(r.severity, str(r.severity))
            st.write(f"[{sev}] {r.kind} ({fmt_ago(r.ts)}): {r.message}")
            if r.context:
                st.json(r.context)

with st.expander("Dead-letters (pending)"):
    with get_session() as s:
        count = int(
            s.execute(
                select(func.count())
                .select_from(RpcDeadLetter)
                .where(RpcDeadLetter.resolved_at.is_(None))
            ).scalar_one()
        )
        st.write(f"unresolved: **{count}**")
        rows = s.execute(
            select(RpcDeadLetter)
            .where(RpcDeadLetter.resolved_at.is_(None))
            .order_by(RpcDeadLetter.next_retry)
            .limit(20)
        ).scalars().all()
        for r in rows:
            st.write(f"id={r.id} retries={r.retries} next_retry={fmt_ago(r.next_retry)}")
            st.code(r.error_text)

with st.expander("Recent jobs"):
    with get_session() as s:
        rows = s.execute(select(Job).order_by(desc(Job.id)).limit(20)).scalars().all()
        data = [
            {
                "id": r.id, "kind": r.kind, "status": r.status,
                "created": fmt_ago(r.created_at),
                "finished": fmt_ago(r.finished_at) if r.finished_at else "—",
            }
            for r in rows
        ]
    st.dataframe(data, use_container_width=True)
