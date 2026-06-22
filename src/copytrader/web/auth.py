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


def _promote_if_admin(user, _session) -> None:
    """許可リスト（ADMIN_EMAILS / 既定 kazgamada@gmail.com）のメールなら admin に昇格。

    OIDC / メール&パスワード / マジックリンクの全ログイン経路で共通利用する。
    渡された ORM オブジェクトを更新するだけで、コミットは呼び出し側 session に任せる。
    """
    if user.email.strip().lower() in _admin_emails() and user.role != "admin":
        user.role = "admin"


def _activate_user_session(user_id):
    """user_id からユーザーを有効化し、セッショントークンを発行して state に載せる。

    無効化済み/不在/DBエラーなら None。許可リストのメールは admin に昇格。
    """
    import streamlit as st

    from copytrader.db.engine import get_session as db_session
    from copytrader.db.models import User

    try:
        with db_session() as s:
            user = s.get(User, user_id)
            if user is None or not user.is_active:
                return None
            _promote_if_admin(user, s)
            s.flush()
            s.refresh(user)
    except Exception:  # noqa: BLE001
        log.warning("session activation failed", exc_info=True)
        return None
    token = _create_session(str(user.id))
    st.session_state[SESSION_COOKIE] = token
    st.session_state["_current_user"] = user
    return user


def register_user(email: str, password: str) -> tuple[bool, str]:
    """新規アカウント登録。成功時 (True, user_id文字列)、失敗時 (False, エラー文)。"""
    import bcrypt
    from sqlalchemy import select

    from copytrader.db.engine import get_session as db_session
    from copytrader.db.models import User

    email_l = (email or "").strip().lower()
    if "@" not in email_l or "." not in email_l:
        return False, "有効なメールアドレスを入力してください"
    if len(password or "") < 8:  # noqa: PLR2004
        return False, "パスワードは8文字以上にしてください"
    try:
        with db_session() as s:
            existing = s.execute(
                select(User).where(User.email == email_l)
            ).scalar_one_or_none()
            if existing is not None:
                return False, "このメールアドレスは既に登録されています"
            user = User(
                email=email_l,
                pw_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
                role="admin" if email_l in _admin_emails() else "user",
                is_active=True,
            )
            s.add(user)
            s.flush()
            uid = str(user.id)
    except Exception:  # noqa: BLE001
        log.warning("register failed", exc_info=True)
        return False, "登録に失敗しました（DBエラー）"
    return True, uid


def _link_base_url() -> str:
    """メールリンクのベース URL。未設定なら空（相対リンクになる旨を UI で警告）。"""
    from copytrader.config import settings
    return (settings.app_base_url or "").rstrip("/")


def request_magic_link(email: str) -> None:
    """マジックリンクを送信する。アカウントが無ければ作成（パスワード不要登録）。

    存在の有無を漏らさないため、UI 側は常に同じ案内を出す。
    """
    from sqlalchemy import select

    from copytrader.db.engine import get_session as db_session
    from copytrader.db.models import User
    from copytrader.email.client import send_magic_link
    from copytrader.web.auth_tokens import PURPOSE_MAGIC_LINK, create_login_token

    email_l = (email or "").strip().lower()
    if "@" not in email_l:
        return
    try:
        with db_session() as s:
            user = s.execute(
                select(User).where(User.email == email_l)
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    email=email_l,
                    pw_hash=_unusable_password_hash(),
                    role="admin" if email_l in _admin_emails() else "user",
                    is_active=True,
                )
                s.add(user)
                s.flush()
            if not user.is_active:
                return
            uid = user.id
        raw = create_login_token(uid, PURPOSE_MAGIC_LINK)
    except Exception:  # noqa: BLE001
        log.warning("magic link request failed", exc_info=True)
        return
    url = f"{_link_base_url()}/?action=magic&token={raw}"
    send_magic_link(email_l, url)


def request_password_reset(email: str) -> None:
    """パスワードリセットリンクを送信する（存在しないメールでも無反応で同じ案内）。"""
    from sqlalchemy import select

    from copytrader.db.engine import get_session as db_session
    from copytrader.db.models import User
    from copytrader.email.client import send_password_reset
    from copytrader.web.auth_tokens import PURPOSE_PASSWORD_RESET, create_login_token

    email_l = (email or "").strip().lower()
    try:
        with db_session() as s:
            user = s.execute(
                select(User).where(User.email == email_l)
            ).scalar_one_or_none()
            if user is None or not user.is_active:
                return
            uid = user.id
        raw = create_login_token(uid, PURPOSE_PASSWORD_RESET)
    except Exception:  # noqa: BLE001
        log.warning("password reset request failed", exc_info=True)
        return
    url = f"{_link_base_url()}/?action=reset&token={raw}"
    send_password_reset(email_l, url)


def _set_password(user_id, new_password: str) -> bool:
    """ユーザーのパスワードを更新する。"""
    import bcrypt

    from copytrader.db.engine import get_session as db_session
    from copytrader.db.models import User

    try:
        with db_session() as s:
            user = s.get(User, user_id)
            if user is None:
                return False
            user.pw_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        return True
    except Exception:  # noqa: BLE001
        log.warning("set password failed", exc_info=True)
        return False


def _show_set_new_password_form(token: str, purpose: str) -> None:
    """リセットリンク経由で新パスワードを設定するフォーム。"""
    import streamlit as st

    from copytrader.web.auth_tokens import consume_login_token

    _prelogin_chrome()
    st.markdown("## 🔑 新しいパスワードの設定")
    with st.form("set_new_pw"):
        pw1 = st.text_input("新しいパスワード", type="password")
        pw2 = st.text_input("新しいパスワード（確認）", type="password")
        submitted = st.form_submit_button("パスワードを更新", type="primary")
    if submitted:
        if pw1 != pw2:
            st.error("パスワードが一致しません")
            return
        if len(pw1) < 8:  # noqa: PLR2004
            st.error("パスワードは8文字以上にしてください")
            return
        user_id = consume_login_token(token, purpose)
        if user_id is None:
            st.error("リンクが無効か期限切れです。再度リセットを依頼してください。")
            return
        if _set_password(user_id, pw1):
            st.success("パスワードを更新しました。ログインし直してください。")
            st.query_params.clear()
        else:
            st.error("更新に失敗しました")


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

    # 1.5) メールリンク（マジックリンク / パスワードリセット）のクエリ処理
    if _handle_email_link_params():
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

    # 4) 緊急フォールバック: DB 接続不可 & WEB_PASSWORD 設定時のみ単一パスワードゲート。
    #    通常運用では §5 の統合ログインページを常に表示する（認証画面が出ない問題の解消）。
    expected = os.environ.get("WEB_PASSWORD", "")
    if expected and not _oauth_configured() and not _db_reachable():
        _legacy_password_gate(expected)
        return

    # 5) 統合ログインページ（Google + パスワード + マジックリンク + 新規登録 + リセット）
    _show_login_form()
    st.stop()


def _db_reachable() -> bool:
    """DB に到達できるか（緊急フォールバック判定用）。"""
    try:
        from copytrader.db.engine import ping
        return ping()
    except Exception:  # noqa: BLE001
        return False


def _handle_email_link_params() -> bool:
    """URL の ?action=magic|reset&token=... を処理する。

    - magic: トークンを消費してログイン → True
    - reset: 新パスワード設定フォームを表示（送信で消費）→ st.stop() するため戻らない
    認証が成立/フォーム表示したら True、無関係なら False。
    """
    import streamlit as st

    try:
        params = st.query_params
        action = params.get("action")
        token = params.get("token")
    except Exception:  # noqa: BLE001
        return False
    if not action or not token:
        return False

    from copytrader.web.auth_tokens import (
        PURPOSE_MAGIC_LINK,
        PURPOSE_PASSWORD_RESET,
        consume_login_token,
    )

    if action == "magic":
        user_id = consume_login_token(token, PURPOSE_MAGIC_LINK)
        if user_id is None:
            _prelogin_chrome()
            st.error("ログインリンクが無効か期限切れです。もう一度お試しください。")
            st.query_params.clear()
            return False
        user = _activate_user_session(user_id)
        if user is None:
            return False
        st.query_params.clear()
        st.rerun()

    if action == "reset":
        _show_set_new_password_form(token, PURPOSE_PASSWORD_RESET)
        st.stop()

    return False


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


_GOOGLE_G_B64 = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA0OCA0OCI+PHBhdGggZmlsbD0iI0VBNDMzNSIgZD0iTTI0IDkuNWMzLjU0IDAgNi43MSAxLjIyIDkuMjEgMy42bDYuODUtNi44NUMzNS45IDIuMzggMzAuNDcgMCAyNCAwIDE0LjYyIDAgNi41MSA1LjM4IDIuNTYgMTMuMjJsNy45OCA2LjE5QzEyLjQzIDEzLjcyIDE3Ljc0IDkuNSAyNCA5LjV6Ii8+PHBhdGggZmlsbD0iIzQyODVGNCIgZD0iTTQ2Ljk4IDI0LjU1YzAtMS41Ny0uMTUtMy4wOS0uMzgtNC41NUgyNHY5LjAyaDEyLjk0Yy0uNTggMi45Ni0yLjI2IDUuNDgtNC43OCA3LjE4bDcuNzMgNmM0LjUxLTQuMTggNy4wOS0xMC4zNiA3LjA5LTE3LjY1eiIvPjxwYXRoIGZpbGw9IiNGQkJDMDUiIGQ9Ik0xMC41MyAyOC41OWMtLjQ4LTEuNDUtLjc2LTIuOTktLjc2LTQuNTlzLjI3LTMuMTQuNzYtNC41OWwtNy45OC02LjE5Qy45MiAxNi40NiAwIDIwLjEyIDAgMjRjMCAzLjg4LjkyIDcuNTQgMi41NiAxMC43OGw3Ljk3LTYuMTl6Ii8+PHBhdGggZmlsbD0iIzM0QTg1MyIgZD0iTTI0IDQ4YzYuNDggMCAxMS45My0yLjEzIDE1Ljg5LTUuODFsLTcuNzMtNmMtMi4xNSAxLjQ1LTQuOTIgMi4zLTguMTYgMi4zLTYuMjYgMC0xMS41Ny00LjIyLTEzLjQ3LTkuOTFsLTcuOTggNi4xOUM2LjUxIDQyLjYyIDE0LjYyIDQ4IDI0IDQ4eiIvPjwvc3ZnPg=="

_LOGIN_CSS = """
<style>
button[kind="primaryFormSubmit"] {
    background: #b5651d !important;
    border: 1px solid #b5651d !important;
    color: #fff !important;
}
button[kind="primaryFormSubmit"]:hover { background: #c9761f !important; }
button[kind="tertiaryFormSubmit"] {
    color: #c9761f !important; padding: 0 !important; min-height: auto !important;
    font-size: 0.8rem !important; float: right;
}
.login-or {
    display: flex; align-items: center; text-align: center;
    color: #6b7280; font-size: 0.8rem; margin: 0.6rem 0;
}
.login-or::before, .login-or::after {
    content: ""; flex: 1; border-bottom: 1px solid #2a2f3a;
}
.login-or:not(:empty)::before { margin-right: .6em; }
.login-or:not(:empty)::after { margin-left: .6em; }
.login-title { text-align: center; font-size: 1.5rem; font-weight: 700; margin: 0.2rem 0 0.2rem; }
.login-sub { text-align: center; color: #9aa3b2; font-size: 0.85rem; margin-bottom: 1rem; }
.login-foot { text-align: center; color: #6b7280; font-size: 0.75rem; margin-top: 0.8rem; }
.login-foot a { color: #c9761f; }

/* Google ログインボタン: ダーク背景 + 多色 G ロゴ（白背景にしない） */
.st-key-_google_login button {
    background-color: #131314 !important;
    border: 1px solid #5f6368 !important;
    color: #e3e3e3 !important;
    font-weight: 600 !important;
    padding-left: 2.8rem !important;
    background-image: url("data:image/svg+xml;base64,GOOGLE_G_B64") !important;
    background-repeat: no-repeat !important;
    background-position: 0.9rem center !important;
    background-size: 1.15rem 1.15rem !important;
}
.st-key-_google_login button:hover {
    background-color: #1f2023 !important;
    border-color: #8a8f96 !important;
    color: #ffffff !important;
}
</style>
"""


def _show_login_form() -> None:
    """統合ログインページ（中央カード・1カラム）。

    上から Google → メールリンク（マジックリンク）→ メール/パスワード →
    「パスワードをお忘れですか？」→ ログイン、最下部に新規登録。
    """
    import streamlit as st

    _prelogin_chrome()
    st.markdown(_LOGIN_CSS.replace("GOOGLE_G_B64", _GOOGLE_G_B64),
                unsafe_allow_html=True)

    _, mid, _ = st.columns([1, 1.5, 1])
    with mid, st.container(border=True):
        st.markdown('<div class="login-title">ログイン</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="login-sub">Copytrader にログインして運用を管理しましょう</div>',
            unsafe_allow_html=True,
        )

        # Google ログイン（ダーク背景 + 多色 G ロゴ・白背景にしない）。
        # 常に表示し、OIDC 未設定でクリックされたらセットアップ案内を出す。
        if st.button("Google でログイン", use_container_width=True,
                     key="_google_login"):
            if _oauth_configured():
                st.login("google")
            else:
                st.error("Google ログインは未設定です。"
                         "[auth] secrets（GOOGLE_CLIENT_ID 等）を設定してください"
                         "（docs/setup/google-oauth.md 参照）。")
        st.markdown('<div class="login-or">または</div>', unsafe_allow_html=True)

        with st.form("login_form", border=False):
            magic_clicked = st.form_submit_button(
                "✉️ メールリンクでログイン", use_container_width=True)
            st.markdown('<div class="login-or">または</div>', unsafe_allow_html=True)
            email = st.text_input("メールアドレス", key="li_email",
                                  placeholder="example@mail.com")
            pw = st.text_input("パスワード", type="password", key="li_pw",
                               placeholder="パスワードを入力")
            forgot_clicked = st.form_submit_button(
                "パスワードをお忘れですか？", type="tertiary")
            login_clicked = st.form_submit_button(
                "ログイン", type="primary", use_container_width=True)
            st.markdown('<div class="login-or"></div>', unsafe_allow_html=True)
            signup_clicked = st.form_submit_button(
                "新規登録（メール + パスワード）", use_container_width=True)

        if login_clicked:
            _handle_login(email, pw)
        elif signup_clicked:
            _handle_signup(email, pw)
        elif magic_clicked:
            if "@" not in (email or ""):
                st.warning("メールアドレスを入力してください。")
            else:
                request_magic_link(email)
                st.success("メールアドレスが有効なら、ログインリンクを送信しました。"
                           "メールをご確認ください。")
        elif forgot_clicked:
            if "@" not in (email or ""):
                st.warning("メールアドレスを入力してください。")
            else:
                request_password_reset(email)
                st.success("メールアドレスが登録済みなら、再設定リンクを送信しました。")

        st.markdown(
            '<div class="login-foot">ログイン／登録することで、利用規約と'
            'プライバシーポリシーに同意したものとみなされます。</div>',
            unsafe_allow_html=True,
        )


def _handle_signup(email: str, pw: str) -> None:
    import streamlit as st

    ok, result = register_user(email, pw)
    if not ok:
        st.error(result)
        return
    if _activate_user_session(result) is None:
        st.error("ログインに失敗しました")
        return
    st.rerun()


def _handle_login(email: str, pw: str) -> None:
    import bcrypt
    import streamlit as st
    from sqlalchemy import select

    from copytrader.db.engine import get_session as db_session
    from copytrader.db.models import User

    try:
        with db_session() as s:
            user = s.execute(
                select(User).where(User.email == (email or "").strip().lower())
            ).scalar_one_or_none()
            ok = user is not None and bcrypt.checkpw(pw.encode(), user.pw_hash.encode())
            active = bool(user and user.is_active)
            uid = user.id if user else None
    except Exception:  # noqa: BLE001
        st.error("DB接続エラーが発生しました")
        return

    if not ok:
        st.error("メールアドレスまたはパスワードが違います")
        return
    if not active:
        st.error("このアカウントは無効化されています")
        return
    # 許可リストのメールは _activate_user_session 内で admin に昇格される。
    if _activate_user_session(uid) is None:
        st.error("ログインに失敗しました")
        return
    st.rerun()


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
