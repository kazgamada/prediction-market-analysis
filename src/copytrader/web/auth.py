"""Single-password gate (F20)."""
from __future__ import annotations

import streamlit as st

from copytrader.config import settings


def require_password() -> None:
    """Block rendering until the right password is entered.

    Fail-fast: if WEB_PASSWORD is empty, the app refuses to render. This
    prevents accidentally exposing the UI on Fly.io.
    """
    if not settings.web_password:
        st.error(
            "WEB_PASSWORD is not configured. Set it in your environment "
            "(e.g. `fly secrets set WEB_PASSWORD=...`) and reload."
        )
        st.stop()

    if st.session_state.get("authed"):
        return

    with st.form("login"):
        pw = st.text_input("Password", type="password")
        ok = st.form_submit_button("Sign in")
        if ok:
            if pw == settings.web_password:
                st.session_state["authed"] = True
                st.rerun()
            else:
                st.error("Wrong password.")
    st.stop()
