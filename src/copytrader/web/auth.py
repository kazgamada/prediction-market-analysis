"""Web UI パスワードゲート（セッション維持型）。

`WEB_PASSWORD` が設定されている場合のみ認証を要求する。一度認証すると Streamlit の
`session_state` に保持し、ページ遷移ごとの再認証を避ける（以前ゲートを no-op に
していた「頻繁な再認証要求」問題への対処）。

`WEB_PASSWORD` 未設定時はゲートを開く（ローカル開発用）。本番（Fly.io の公開 URL）では
kill switch・手動 order など資金移動につながる操作を保護するため、必ず設定すること。
"""
from __future__ import annotations

import hmac
import os

_SESSION_KEY = "_auth_ok"


def password_matches(provided: str, expected: str) -> bool:
    """定数時間比較。expected が空ならゲート無効（常に True）。"""
    if not expected:
        return True
    return hmac.compare_digest(provided or "", expected)


def require_password() -> None:
    """未認証ならログインフォームを出してページ描画を止める。

    `WEB_PASSWORD` 未設定なら即 return（ゲート無効）。
    """
    expected = os.environ.get("WEB_PASSWORD", "")
    if not expected:
        return

    import streamlit as st

    if st.session_state.get(_SESSION_KEY):
        return

    st.markdown("## 🔒 ログイン")
    with st.form("auth_gate"):
        pw = st.text_input("パスワード", type="password")
        submitted = st.form_submit_button("ログイン")
    if submitted:
        if password_matches(pw, expected):
            st.session_state[_SESSION_KEY] = True
            st.rerun()
        else:
            st.error("パスワードが違います")

    if not st.session_state.get(_SESSION_KEY):
        st.stop()
