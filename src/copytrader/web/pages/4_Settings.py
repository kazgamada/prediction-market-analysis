"""Settings page (F19): runtime overrides for indexer thresholds & contracts."""
from __future__ import annotations

import json

import streamlit as st

from copytrader.db import settings_table
from copytrader.web.auth import require_password

st.set_page_config(page_title="Settings", layout="wide")
require_password()
st.title("Settings")
st.caption(
    "Runtime overrides stored in the `settings` table. Empty value = use code default."
)

KNOWN_KEYS = [
    "exchange_addresses",
    "order_filled_topic0",
    "rank_min_trades",
    "rank_min_volume_usdc",
    "replay_default_delays",
]

with st.form("setting"):
    key = st.selectbox("key", KNOWN_KEYS + ["(custom)"])
    if key == "(custom)":
        key = st.text_input("custom key").strip()
    raw = st.text_area("value (JSON)", "")
    save = st.form_submit_button("Save", type="primary")
    delete = st.form_submit_button("Delete this key")
    if save and key:
        try:
            v = json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError as e:
            st.error(f"invalid JSON: {e}")
            v = None
        if v is not None:
            settings_table.set_(key, v)
            st.success(f"saved {key}")
    if delete and key:
        from copytrader.db.engine import get_session
        from copytrader.db.models import Setting
        with get_session() as s:
            row = s.get(Setting, key)
            if row:
                s.delete(row)
                st.success(f"deleted {key}")

st.subheader("Current overrides")
all_settings = settings_table.all_()
if not all_settings:
    st.info("No runtime overrides set.")
else:
    st.json(all_settings)
