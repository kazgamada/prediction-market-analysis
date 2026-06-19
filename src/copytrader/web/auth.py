"""Password gate for the Streamlit UI (F20).

`require_password()` is called at the top of every page. If `WEB_PASSWORD`
is not set, `web_main.py` refuses to start (fail-fast). Here we handle
the interactive session check: a correct password is stored in
`st.session_state` so each page only prompts once per browser session.
"""
from __future__ import annotations

import streamlit as st

from copytrader.config import settings


def require_password() -> None:
    """Block the page unless the user has authenticated this session.

    If WEB_PASSWORD is empty (should not reach here — web_main exits first),
    skip the gate to avoid a hard crash in test environments.
    """
    password = settings.web_password
    if not password:
        # web_main should have exited already; degrade gracefully here.
        return

    if st.session_state.get("_auth_ok"):
        return

    st.title("🔐 ログイン")
    entered = st.text_input("パスワード", type="password", key="_pw_input")
    if st.button("ログイン"):
        if entered == password:
            st.session_state["_auth_ok"] = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    st.stop()
