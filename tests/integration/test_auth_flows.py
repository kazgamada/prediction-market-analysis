"""統合ログイン（マジックリンク/リセットトークン・新規登録）の検証。"""
from __future__ import annotations

from datetime import timedelta

import bcrypt
import pytest


def _make_user(email: str, *, active: bool = True):
    from copytrader.db.engine import get_session
    from copytrader.db.models import User
    with get_session() as s:
        u = User(
            email=email,
            pw_hash=bcrypt.hashpw(b"pw12345678", bcrypt.gensalt()).decode(),
            role="user",
            is_active=active,
        )
        s.add(u)
        s.flush()
        return u.id


def test_login_token_roundtrip(fresh_db) -> None:
    from copytrader.web.auth_tokens import (
        PURPOSE_MAGIC_LINK,
        consume_login_token,
        create_login_token,
    )
    uid = _make_user("a@example.com")
    raw = create_login_token(uid, PURPOSE_MAGIC_LINK)
    assert consume_login_token(raw, PURPOSE_MAGIC_LINK) == uid
    # 一度使ったら無効（ワンタイム）
    assert consume_login_token(raw, PURPOSE_MAGIC_LINK) is None


def test_login_token_wrong_purpose(fresh_db) -> None:
    from copytrader.web.auth_tokens import (
        PURPOSE_MAGIC_LINK,
        PURPOSE_PASSWORD_RESET,
        consume_login_token,
        create_login_token,
    )
    uid = _make_user("b@example.com")
    raw = create_login_token(uid, PURPOSE_MAGIC_LINK)
    # 用途が違えば拒否
    assert consume_login_token(raw, PURPOSE_PASSWORD_RESET) is None


def test_login_token_expired(fresh_db) -> None:
    from copytrader.web.auth_tokens import (
        PURPOSE_PASSWORD_RESET,
        consume_login_token,
        create_login_token,
    )
    uid = _make_user("c@example.com")
    raw = create_login_token(uid, PURPOSE_PASSWORD_RESET, ttl=timedelta(seconds=-1))
    assert consume_login_token(raw, PURPOSE_PASSWORD_RESET) is None


def test_consume_unknown_token(fresh_db) -> None:
    from copytrader.web.auth_tokens import PURPOSE_MAGIC_LINK, consume_login_token
    assert consume_login_token("does-not-exist", PURPOSE_MAGIC_LINK) is None
    assert consume_login_token("", PURPOSE_MAGIC_LINK) is None


def test_register_user_allowlisted_is_admin(fresh_db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", "boss@example.com")
    from sqlalchemy import select

    from copytrader.db.engine import get_session
    from copytrader.db.models import User
    from copytrader.web.auth import register_user

    ok, _ = register_user("boss@example.com", "password123")
    assert ok
    with get_session() as s:
        u = s.execute(select(User).where(User.email == "boss@example.com")).scalar_one()
        assert u.role == "admin"


def test_register_user_non_admin_and_validation(fresh_db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", "boss@example.com")
    from copytrader.web.auth import register_user

    ok, _ = register_user("user@example.com", "password123")
    assert ok
    # 弱いパスワード
    ok, msg = register_user("x@example.com", "short")
    assert not ok and "8" in msg
    # 不正なメール
    ok, _ = register_user("notanemail", "password123")
    assert not ok
    # 重複
    ok, msg = register_user("user@example.com", "password123")
    assert not ok and "既に" in msg


def test_set_password_then_login_hash(fresh_db) -> None:
    from copytrader.db.engine import get_session
    from copytrader.db.models import User
    from copytrader.web.auth import _set_password

    uid = _make_user("d@example.com")
    assert _set_password(uid, "brandnewpass123")
    with get_session() as s:
        u = s.get(User, uid)
        assert bcrypt.checkpw(b"brandnewpass123", u.pw_hash.encode())
