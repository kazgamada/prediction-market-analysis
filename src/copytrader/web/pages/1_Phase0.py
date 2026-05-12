"""Phase 0 page (F16): one-click end-to-end run."""
from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st
from sqlalchemy import desc, select

from copytrader.db.engine import get_session
from copytrader.db.models import Job
from copytrader.jobs.queue import enqueue
from copytrader.web.auth import require_password
from copytrader.web.format import fmt_ago

st.set_page_config(page_title="Phase 0", layout="wide")
require_password()
st.title("Phase 0")
st.caption("One-click: backfill → rank → replay. Worker picks it up from the queue.")

with st.form("phase0_form"):
    c1, c2, c3 = st.columns(3)
    window = c1.number_input("window (days)", min_value=1, max_value=90, value=30)
    top_n = c2.number_input("watchlist top N", min_value=1, max_value=200, value=10)
    copy_usd = c3.number_input("copy USD / trade", min_value=1, max_value=10000, value=50)
    delays_str = st.text_input("delays (seconds, comma-separated)", "30,60,120")
    submitted = st.form_submit_button("Run Phase 0", type="primary")
    if submitted:
        delays = [int(x.strip()) for x in delays_str.split(",") if x.strip()]
        idem = f"phase0:{datetime.now(UTC).strftime('%Y%m%d%H%M')}:{window}:{top_n}"
        jid = enqueue(
            "phase0",
            {
                "window": int(window),
                "watchlist_top": int(top_n),
                "delays": delays,
                "copy_usd_per_trade": float(copy_usd),
            },
            idempotency_key=idem,
        )
        st.success(f"Enqueued job #{jid}. Open the Jobs page to follow progress.")

st.subheader("Recent Phase 0 runs")
with get_session() as s:
    rows = (
        s.execute(
            select(Job).where(Job.kind == "phase0").order_by(desc(Job.created_at)).limit(10)
        ).scalars().all()
    )
    data = [
        {
            "id": r.id,
            "status": r.status,
            "created": fmt_ago(r.created_at),
            "finished": fmt_ago(r.finished_at) if r.finished_at else "—",
            "window": (r.params or {}).get("window"),
            "result?": "yes" if r.result else "no",
        }
        for r in rows
    ]
st.dataframe(data, use_container_width=True)
