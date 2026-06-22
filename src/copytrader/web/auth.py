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


def _admin_emails() -> set[str]:
    """管理者として扱うメールアドレス（小文字）の集合。

    ADMIN_EMAILS 環境変数（カンマ区切り）で指定。既定は kazgamada@gmail.com。
    """
    raw = os.environ.get("ADMIN_EMAILS", "kazgamada@gmail.com")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _oauth_configured() -> bool:
    """Streamlit ネイティブ OIDC（[auth]）が設定済みかどうか。"""
    import streamlit as st
    try:
        return "auth" in st.secrets
    except Exception:  # noqa: BLE001
        return False


def _unusable_password_hash() -> str:
    """OAuth ユーザー用の、ログインに使えないランダム bcrypt ハッシュ。"""
    import bcrypt
    return bcrypt.hashpw(secrets.token_urlsafe(32).encode(), bcrypt.gensalt()).decode()


def _provision_oauth_user(email: str, name: str | None = None) -> bool:
    """Google ログイン済みユーザーを DB に get-or-create し、session に載せる。

    - 既存なら取得。無ければ作成（role はメールが admin 許可リストにあれば admin）。
    - admin 許可リストのメールは毎回 admin に昇格（運営者を確実に admin にする）。
    返り値: 成功したら True。無効化済み/DB エラーなら False。
    """
    import streamlit as st
    from sqlalchemy import select

    from copytrader.db.engine import get_session as db_session
    from copytrader.db.models import User

    email_l = (email or "").strip().lower()
    if not email_l:
        return False
    is_admin = email_l in _admin_emails()
    try:
        with db_session() as s:
            user = s.execute(
                select(User).where(User.email == email_l)
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    email=email_l,
                    pw_hash=_unusable_password_hash(),
                    role="admin" if is_admin else "user",
                    is_active=True,
                )
                s.add(user)
                s.flush()
            elif is_admin and user.role != "admin":
                # 許可リストのメールは admin に昇格
                user.role = "admin"
            if not user.is_active:
                return False
            s.refresh(user)
    except Exception:  # noqa: BLE001
        log.warning("oauth user provision failed", exc_info=True)
        st.error("DB接続エラーが発生しました（ユーザー登録）。")
        return False

    st.session_state["_current_user"] = user
    return True


def require_login() -> None:
    """未認証ならログインページを表示してページ描画を停止する。

    優先順位:
      1) session_state にユーザーがいればそのまま
      2) Google ネイティブ OIDC（st.user.is_logged_in）→ DB プロビジョニング
      3) セッショントークン（メール/パスワードユーザー）で復元
      4) 後方互換: OIDC 未設定 & WEB_PASSWORD 設定 & users 空 → パスワードゲート
      5) それ以外はログインページ（Google + メール/パスワード）
    """
    import streamlit as st

    # 1) 既にセッション state に認証済みユーザーがいる
    if current_user() is not None:
        return

    # 2) Google ネイティブ OIDC でログイン済み → プロビジョニング
    if _oauth_configured():
        user_obj = getattr(st, "user", None)
        if user_obj is not None and getattr(user_obj, "is_logged_in", False):
            email = getattr(user_obj, "email", None)
            if _provision_oauth_user(email, getattr(user_obj, "name", None)):
                return
            # 無効化済み等 → ログアウトしてフォームへ
            try:
                st.logout()
            except Exception:  # noqa: BLE001
                pass

    # 3) セッショントークンで復元を試みる（メール/パスワードユーザー）
    token = st.session_state.get(SESSION_COOKIE)
    if token:
        user = _resolve_session(token)
        if user and user.is_active:
            st.session_state["_current_user"] = user
            return
        st.session_state.pop(SESSION_COOKIE, None)

    # 4) 後方互換: OIDC 未設定 & WEB_PASSWORD 設定 & users 空 → パスワードゲート
    expected = os.environ.get("WEB_PASSWORD", "")
    if expected and not _oauth_configured() and _users_table_empty():
        _legacy_password_gate(expected)
        return

    # 5) ログインページ（Google + メール/パスワード）
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
    st.caption("Copytrader 管理コンソール")

    # Google ログイン（OIDC 設定済みのときだけ表示）
    if _oauth_configured():
        with st.container(border=True):
            st.markdown("#### Google でログイン")
            st.caption("Google アカウントでサインインします。")
            if st.button("🔵 Google でログイン", type="primary",
                         use_container_width=True, key="_google_login"):
                st.login("google")
        st.markdown(
            "<div style='text-align:center;color:#666;margin:0.5rem 0;'>"
            "— または —</div>",
            unsafe_allow_html=True,
        )

    with st.container(border=True):
        st.markdown("#### メール / パスワード")
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
    # 管理者許可リスト（ADMIN_EMAILS / 既定 kazgamada@gmail.com）のメールは
    # ログイン方式に依らず admin に昇格させる。OIDC 未設定でメール/パスワード
    # ログインした運営者の「管理者メニューが出ない」を防ぐ（OAuth 経路と同挙動）。
    if user.email.strip().lower() in _admin_emails() and user.role != "admin":
        try:
            with db_session() as s2:
                u2 = s2.get(User, user.id)
                if u2 is not None:
                    u2.role = "admin"
                    s2.flush()
                    s2.refresh(u2)
                    user = u2
        except Exception:  # noqa: BLE001
            log.warning("admin 昇格に失敗", exc_info=True)
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
    # Google ネイティブ OIDC でログイン中なら併せてサインアウト
    if _oauth_configured():
        user_obj = getattr(st, "user", None)
        if user_obj is not None and getattr(user_obj, "is_logged_in", False):
            try:
                st.logout()
                return
            except Exception:  # noqa: BLE001
                pass
    st.rerun()


# 後方互換エイリアス
require_password = require_login
