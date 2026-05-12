"""Watchlist page (F18): add / remove / toggle."""
from __future__ import annotations

import re

import streamlit as st
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from copytrader.db.engine import get_session
from copytrader.db.models import Watchlist
from copytrader.web.auth import require_password
from copytrader.web.format import fmt_ago, short_addr

st.set_page_config(page_title="Watchlist", layout="wide")
require_password()
st.title("Watchlist")

ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _addr_to_bytes(s: str) -> bytes | None:
    s = s.strip()
    if not ADDR_RE.match(s):
        return None
    return bytes.fromhex(s[2:].lower())


with st.form("add"):
    a_str = st.text_input("address (0x...)").strip()
    note = st.text_input("note (optional)")
    submitted = st.form_submit_button("Add / Update", type="primary")
    if submitted:
        ab = _addr_to_bytes(a_str)
        if ab is None:
            st.error("invalid address")
        else:
            with get_session() as s:
                stmt = pg_insert(Watchlist).values(
                    address=ab, note=note or None, active=True,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[Watchlist.address],
                    set_={"note": stmt.excluded.note, "active": True},
                )
                s.execute(stmt)
            st.success(f"Added/updated {short_addr(ab)}")

st.subheader("Current watchlist")
with get_session() as s:
    rows = s.execute(select(Watchlist).order_by(Watchlist.added_at.desc())).scalars().all()
    data = [
        {
            "address": "0x" + r.address.hex(),
            "note": r.note,
            "active": r.active,
            "added": fmt_ago(r.added_at),
        }
        for r in rows
    ]
st.dataframe(data, use_container_width=True)

with st.form("toggle"):
    a2 = st.text_input("address to toggle / remove")
    col1, col2 = st.columns(2)
    toggle = col1.form_submit_button("Toggle active")
    remove = col2.form_submit_button("Remove")
    ab = _addr_to_bytes(a2) if a2 else None
    if ab is None and (toggle or remove):
        st.error("invalid address")
    elif toggle and ab is not None:
        with get_session() as s:
            row = s.get(Watchlist, ab)
            if row:
                row.active = not row.active
                st.success(f"{short_addr(ab)} active={row.active}")
    elif remove and ab is not None:
        with get_session() as s:
            row = s.get(Watchlist, ab)
            if row:
                s.delete(row)
                st.success(f"removed {short_addr(ab)}")
