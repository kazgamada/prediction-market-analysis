"""Status page (F15): cursor / lag / 1h trade count / dead-letters / RPC self-test."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import streamlit as st
from sqlalchemy import func, select

from copytrader.db.engine import get_session
from copytrader.db.models import Cursor, RiskEvent, RpcDeadLetter, Trade
from copytrader.indexer.backfill import CURSOR_NAME
from copytrader.web.auth import require_password
from copytrader.web.format import fmt_ago

st.set_page_config(page_title="Status", layout="wide")
require_password()
st.title("Status")
st.caption("Indexer + worker liveness snapshot. Refresh the page to update.")


@st.cache_data(ttl=5)
def _snapshot() -> dict:
    with get_session() as s:
        cur = s.get(Cursor, CURSOR_NAME)
        one_h_ago = datetime.now(UTC) - timedelta(hours=1)
        trades_1h = int(
            s.execute(
                select(func.count()).select_from(Trade).where(Trade.ts >= one_h_ago)
            ).scalar_one()
        )
        trades_total = int(s.execute(select(func.count()).select_from(Trade)).scalar_one())
        dl_pending = int(
            s.execute(
                select(func.count())
                .select_from(RpcDeadLetter)
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
        }


snap = _snapshot()
c1, c2, c3, c4 = st.columns(4)
c1.metric("cursor block", f"{snap['cursor_block']:,}" if snap["cursor_block"] else "—")
c2.metric("trades (1h)", f"{snap['trades_1h']:,}")
c3.metric("trades (total)", f"{snap['trades_total']:,}")
c4.metric("dead-letters", snap["dl_pending"])

st.write(f"cursor last updated: **{fmt_ago(snap['cursor_updated_at'])}**")
if snap["last_risk_kind"]:
    st.warning(
        f"Last risk event: **{snap['last_risk_kind']}** "
        f"({fmt_ago(snap['last_risk_ts'])}): {snap['last_risk_msg']}"
    )
else:
    st.success("No risk events recorded.")
