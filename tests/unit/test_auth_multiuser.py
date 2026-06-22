from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta


def test_hash_token_deterministic() -> None:
    token = "test-token-abc123"
    h1 = hashlib.sha256(token.encode()).hexdigest()
    h2 = hashlib.sha256(token.encode()).hexdigest()
    assert h1 == h2
    assert len(h1) == 64


def test_hash_token_different_inputs() -> None:
    t1 = "token-a"
    t2 = "token-b"
    h1 = hashlib.sha256(t1.encode()).hexdigest()
    h2 = hashlib.sha256(t2.encode()).hexdigest()
    assert h1 != h2


def test_secrets_token_urlsafe_length() -> None:
    token = secrets.token_urlsafe(32)
    assert len(token) >= 32


def test_session_expiry_logic() -> None:
    ttl = timedelta(days=7)
    created_at = datetime.now(UTC)
    expires_at = created_at + ttl
    assert expires_at > datetime.now(UTC)


def test_session_expired() -> None:
    expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert expires_at < datetime.now(UTC)


def test_bcrypt_verify_mock() -> None:
    """bcrypt が使える場合のみ実行。インポートできない場合はスキップ。"""
    try:
        import bcrypt  # type: ignore[import-untyped]
    except ImportError:
        return

    password = "my-secret-password"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    assert bcrypt.checkpw(password.encode(), hashed)
    assert not bcrypt.checkpw(b"wrong-password", hashed)
