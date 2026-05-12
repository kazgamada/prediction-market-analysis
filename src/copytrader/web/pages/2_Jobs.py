"""Jobs page (F17): list + live log view."""
from __future__ import annotations

import streamlit as st
from sqlalchemy import desc, select

from copytrader.db.engine import get_session
from copytrader.db.models import Job, JobLog
from copytrader.web.auth import require_password
from copytrader.web.format import fmt_ago

st.set_page_config(page_title="Jobs", layout="wide")
require_password()
st.title("Jobs")

kind = st.selectbox("kind filter", ["(all)", "phase0", "backfill", "rank", "replay"])
limit = st.slider("show", 5, 100, 30)

with get_session() as s:
    q = select(Job).order_by(desc(Job.created_at)).limit(limit)
    if kind != "(all)":
        q = q.where(Job.kind == kind)
    rows = s.execute(q).scalars().all()
    listing = [
        {
            "id": r.id,
            "kind": r.kind,
            "status": r.status,
            "created": fmt_ago(r.created_at),
            "started": fmt_ago(r.started_at) if r.started_at else "—",
            "finished": fmt_ago(r.finished_at) if r.finished_at else "—",
        }
        for r in rows
    ]
st.dataframe(listing, use_container_width=True)

selected_id = st.number_input("Open job ID for live logs", min_value=0, value=0, step=1)
if selected_id > 0:
    with get_session() as s:
        job = s.get(Job, int(selected_id))
        if not job:
            st.error(f"Job {selected_id} not found")
        else:
            st.write(f"**status:** {job.status}  **kind:** {job.kind}")
            st.json({"params": job.params, "progress": job.progress, "result": job.result})
            if job.error_text:
                st.error(job.error_text)
            log_rows = (
                s.execute(
                    select(JobLog)
                    .where(JobLog.job_id == job.id)
                    .order_by(JobLog.id)
                    .limit(500)
                ).scalars().all()
            )
    if selected_id > 0 and job:
        log_text = "\n".join(
            f"{r.ts.strftime('%H:%M:%S')} [{r.level}] {r.message}" for r in log_rows
        )
        st.code(log_text or "(no logs yet)", language="text")

    # Cheap polling: rerun every 2 seconds when the job is RUNNING.
    if job and job.status == "RUNNING":
        import time
        time.sleep(2)
        st.rerun()
