"""Password gate — WEB_PASSWORD required (F20).

WEB_PASSWORD env が未設定なら起動を拒否 (fail-fast)。
設定済みの場合はセッション単位のパスワード認証を強制する。
"""
from __future__ import annotations

import streamlit as st

from copytrader.config import settings


def require_password() -> None:
    """ページを保護する。

    - WEB_PASSWORD が空 → エラー表示して st.stop()
    - 未認証 → ログインフォームを表示して st.stop()
    - 認証済み → 何もしない (ページ本体を描画させる)
    """
    if not settings.web_password:
        st.error(
            "🔒 WEB_PASSWORD が設定されていません。"
            "Fly Secrets (または .env) で WEB_PASSWORD を設定してください。"
        )
        st.stop()

    if st.session_state.get("_authenticated"):
        return

    st.markdown("## 🔐 ログイン")
    with st.form("_login_form"):
        pwd = st.text_input("パスワード", type="password", placeholder="WEB_PASSWORD")
        submitted = st.form_submit_button("ログイン", type="primary")
        if submitted:
            if pwd == settings.web_password:
                st.session_state["_authenticated"] = True
                st.rerun()
            else:
                st.error("パスワードが違います")
    st.stop()
