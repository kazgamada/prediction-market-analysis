"""RPC エラーの整形ユーティリティ。

Web3 / requests から伝播してくる例外には RPC URL が丸ごと含まれており、
そこには Alchemy などの API キーがパスとして埋め込まれている。UI（Streamlit）に
そのまま表示するとキーが漏洩するため、メッセージを再構築するヘルパを置く。
"""

from __future__ import annotations

import functools
import re
from typing import Callable, TypeVar

# プロバイダごとの「URL とキー部分」を捕捉するパターン。
# キャプチャ1 = ホスト + バージョンパス、続くトークンを <redacted> に置換する。
_RPC_KEY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(https?://[^/\s]*\.alchemy\.com/v2/)[A-Za-z0-9_-]+"),
    re.compile(r"(https?://[^/\s]*\.infura\.io/v3/)[A-Za-z0-9_-]+"),
    re.compile(r"(https?://[^/\s]*\.quiknode\.pro/)[A-Za-z0-9_-]+"),
    re.compile(r"(https?://[^/\s]*\.blastapi\.io/)[A-Za-z0-9_-]+"),
    re.compile(r"(https?://[^/\s]*\.ankr\.com/[^/\s]+/)[A-Za-z0-9_-]+"),
)

_HTTP_STATUS_RE = re.compile(r"\b(4\d{2}|5\d{2})\s+(?:Client|Server)\s+Error\b")


def redact_rpc_url(text: str) -> str:
    out = text
    for pat in _RPC_KEY_PATTERNS:
        out = pat.sub(r"\1<redacted>", out)
    return out


class RpcError(RuntimeError):
    """API キーを除去済みの RPC エラー。"""


def _http_status(exc: BaseException) -> int | None:
    resp = getattr(exc, "response", None)
    if resp is not None:
        code = getattr(resp, "status_code", None)
        if isinstance(code, int):
            return code
    m = _HTTP_STATUS_RE.search(str(exc))
    if m:
        return int(m.group(1))
    return None


def _response_body(exc: BaseException) -> str | None:
    """`requests.HTTPError` の応答本文を JSON-RPC エラーまで掘って取り出す。"""
    resp = getattr(exc, "response", None)
    if resp is None:
        return None
    try:
        data = resp.json()
    except Exception:
        text = getattr(resp, "text", None)
        return text.strip() if isinstance(text, str) and text.strip() else None
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
            if isinstance(msg, str) and msg:
                return msg
        if isinstance(data.get("message"), str):
            return data["message"]
    return str(data)


def to_rpc_error(exc: BaseException) -> RpcError:
    raw = redact_rpc_url(str(exc))
    body = _response_body(exc)
    body_redacted = redact_rpc_url(body) if body else None
    status = _http_status(exc)
    if status in (400, 401, 403):
        # Alchemy は無効なキーや存在しないアプリに対して 400 を返す。
        # 401/403 は明確な認証エラー。いずれもユーザーが対処可能な情報を出す。
        detail = body_redacted or raw
        return RpcError(
            f"RPC provider rejected the request (HTTP {status}). "
            "POLYGON_RPC_HTTP の API キー / プラン上限 / アプリ設定を確認してください。"
            f" 詳細: {detail}"
        )
    if body_redacted and body_redacted not in raw:
        return RpcError(f"{raw} | body: {body_redacted}")
    return RpcError(raw)


F = TypeVar("F", bound=Callable[..., object])


def wrap_rpc_errors(fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> object:
        try:
            return fn(*args, **kwargs)
        except RpcError:
            raise
        except Exception as e:
            raise to_rpc_error(e) from e

    return wrapper  # type: ignore[return-value]
