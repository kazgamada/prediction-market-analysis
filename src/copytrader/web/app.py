"""Streamlit entrypoint. Real pages live under web/pages/."""
from __future__ import annotations

import streamlit as st

from copytrader.web.auth import require_password

st.set_page_config(page_title="polymarket-copytrader", layout="wide")
require_password()

st.title("polymarket-copytrader")
st.caption("Phase 0 rebuild. Use the sidebar to navigate.")
st.info("Open `Status` to see indexer state, `Phase 0` to run the end-to-end backtest.")
