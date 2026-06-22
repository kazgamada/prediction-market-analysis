"""マジックリンク / パスワードリセットのワンタイムトークン処理。

生トークンは呼び出し側がメール送信に使い、DB には SHA-256 ハッシュのみ保存する。
Streamlit 非依存（純ロジック）なのでユニットテストしやすい。
"""
from __future__ import annotations

import hashlib
import secrets
import uuid as _uuid_mod
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from copytrader.db.engine import get_session
from copytrader.db.models import LoginToken

PURPOSE_MAGIC_LINK = "magic_link"
PURPOSE_PASSWORD_RESET = "password_reset"

DEFAULT_TTL = timedelta(hours=1)


def hash_token(token: str) -> str:
    """トークンの SHA-256 ハッシュ。"""
    return hashlib.sha256(token.encode()).hexdigest()


def create_login_token(
    user_id: _uuid_mod.UUID,
    purpose: str,
    *,
    ttl: timedelta = DEFAULT_TTL,
) -> str:
    """ワンタイムトークンを発行して DB に保存し、生トークンを返す。"""
    raw = secrets.token_urlsafe(32)
    with get_session() as s:
        s.add(LoginToken(
            user_id=user_id,
            token_hash=hash_token(raw),
            purpose=purpose,
            expires_at=datetime.now(UTC) + ttl,
        ))
    return raw


def consume_login_token(raw: str, purpose: str) -> _uuid_mod.UUID | None:
    """トークンを検証し、有効なら used_at を立てて user_id を返す。

    無効（存在しない / 期限切れ / 使用済み / 用途不一致）なら None。
    """
    if not raw:
        return None
    h = hash_token(raw)
    now = datetime.now(UTC)
    with get_session() as s:
        row = s.execute(
            select(LoginToken).where(LoginToken.token_hash == h)
        ).scalar_one_or_none()
        if row is None or row.purpose != purpose:
            return None
        if row.used_at is not None or row.expires_at <= now:
            return None
        row.used_at = now
        return row.user_id
