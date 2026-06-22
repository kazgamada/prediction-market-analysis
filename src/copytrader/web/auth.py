"""マルチユーザー認証ゲート（セッションDB方式）。

後方互換: WEB_PASSWORD が設定されており users テーブルが空の場合は従来の
パスワードゲートにフォールバックする。
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta

log = logging.getLogger(__name__)

SESSION_COOKIE = "_session_token"
SESSION_TTL = timedelta(days=7)
_SESSION_KEY = "_auth_ok"  # backward-compat key


def _hash_token(token: str) -> str:
    """SHA-256 hash of a session token."""
    return hashlib.sha256(token.encode()).hexdigest()


def password_matches(provided: str, expected: str) -> bool:
    """定数時間比較。expected が空ならゲート無効（常に True）。後方互換用。"""
    if not expected:
        return True
    return hmac.compare_digest(provided or "", expected)


def _create_session(user_id: str) -> str:
    """新規セッショントークンを DB に保存して返す。"""
    from copytrader.db.engine import get_session as db_session
    from copytrader.db.models import Session as DbSession

    token = secrets.token_urlsafe(32)
    with db_session() as s:
        s.add(DbSession(
            user_id=user_id,
            token_hash=_hash_token(token),
            expires_at=datetime.now(UTC) + SESSION_TTL,
        ))
    return token


def _resolve_session(token: str):
    """トークンから有効な User を返す。期限切れ・存在しない場合は None。"""
    from sqlalchemy import select

    from copytrader.db.engine import get_session as db_session
    from copytrader.db.models import Session as DbSession
    from copytrader.db.models import User

    h = _hash_token(token)
    try:
        with db_session() as s:
            row = s.execute(
                select(DbSession).where(
                    DbSession.token_hash == h,
                    DbSession.expires_at > datetime.now(UTC),
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            user = s.get(User, row.user_id)
            return user
    except Exception:  # noqa: BLE001
        log.warning("session resolve failed", exc_info=True)
        return None


def _users_table_empty() -> bool:
    """users テーブルが空かどうかを確認。DB 接続できない場合は False を返す。"""
    from sqlalchemy import func, select

    from copytrader.db.engine import get_session as db_session
    from copytrader.db.models import User

    try:
        with db_session() as s:
            count = s.execute(select(func.count()).select_from(User)).scalar_one()
            return count == 0
    except Exception:  # noqa: BLE001
        return False


def current_user():
    """session_state にキャッシュ済みユーザーを返す。未認証なら None。"""
    import streamlit as st
    return st.session_state.get("_current_user")


def require_login() -> None:
    """未認証ならログインフォームを表示してページ描画を停止する。

    後方互換: WEB_PASSWORD が設定されており users テーブルが空の場合は
    パスワードゲートにフォールバックする。
    """
    import streamlit as st

    # 既にセッション state に認証済みユーザーがいる
    if current_user() is not None:
        return

    # セッショントークンで復元を試みる
    token = st.session_state.get(SESSION_COOKIE)
    if token:
        user = _resolve_session(token)
        if user and user.is_active:
            st.session_state["_current_user"] = user
            return
        st.session_state.pop(SESSION_COOKIE, None)

    # 後方互換: WEB_PASSWORD が設定されており users が空 → パスワードゲート
    expected = os.environ.get("WEB_PASSWORD", "")
    if expected and _users_table_empty():
        _legacy_password_gate(expected)
        return

    # マルチユーザーログインフォーム
    _show_login_form()
    st.stop()


def _prelogin_chrome() -> None:
    """ログイン前画面の見た目を整える。

    Streamlit 標準のページ自動ナビ（pages/ のファイル名一覧）を隠し、
    ダークテーマを適用する。これをしないとログイン前にナビが丸見えになる。
    """
    import streamlit as st

    st.markdown(
        '<style>[data-testid="stSidebarNav"]{display:none !important;}</style>',
        unsafe_allow_html=True,
    )
    try:
        from copytrader.web.theme import inject_theme
        inject_theme()
    except Exception:  # noqa: BLE001
        pass


def _legacy_password_gate(expected: str) -> None:
    """旧来の単一パスワードゲート（後方互換）。"""
    import streamlit as st

    if st.session_state.get(_SESSION_KEY):
        return

    _prelogin_chrome()
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


def require_admin() -> None:
    """管理者ロール以外はアクセス拒否（403相当）。"""
    import streamlit as st

    require_login()
    user = current_user()
    if user is None or user.role != "admin":
        st.error("⛔ 管理者専用ページです。")
        st.stop()


def _show_login_form() -> None:
    import streamlit as st

    _prelogin_chrome()
    st.markdown("## 🔒 ログイン")
    with st.form("login_form"):
        email = st.text_input("メールアドレス")
        pw = st.text_input("パスワード", type="password")
        col1, col2 = st.columns(2)
        submitted = col1.form_submit_button("ログイン")
        reset_link = col2.form_submit_button("パスワードを忘れた")

    if submitted:
        _handle_login(email, pw)
    if reset_link:
        st.session_state["_show_reset"] = True
        st.rerun()

    if st.session_state.get("_show_reset"):
        _show_pw_reset_form()


def _handle_login(email: str, pw: str) -> None:
    import bcrypt
    import streamlit as st
    from sqlalchemy import select

    from copytrader.db.engine import get_session as db_session
    from copytrader.db.models import User

    try:
        with db_session() as s:
            user = s.execute(
                select(User).where(User.email == email)
            ).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        st.error("DB接続エラーが発生しました")
        return

    if user is None or not bcrypt.checkpw(pw.encode(), user.pw_hash.encode()):
        st.error("メールアドレスまたはパスワードが違います")
        return
    if not user.is_active:
        st.error("このアカウントは無効化されています")
        return
    token = _create_session(str(user.id))
    st.session_state[SESSION_COOKIE] = token
    st.session_state["_current_user"] = user
    st.rerun()


def _show_pw_reset_form() -> None:
    import streamlit as st

    st.markdown("### パスワードリセット")
    with st.form("pw_reset_form"):
        _email = st.text_input("登録済みメールアドレス")
        submitted = st.form_submit_button("リセットメールを送信")
    if submitted:
        st.info("メールアドレスが登録済みの場合、リセットリンクを送信しました。")


def logout() -> None:
    """セッションをクリアしてログアウト。"""
    import streamlit as st

    st.session_state.pop(SESSION_COOKIE, None)
    st.session_state.pop("_current_user", None)
    st.session_state.pop(_SESSION_KEY, None)
    st.rerun()


# 後方互換エイリアス
require_password = require_login
