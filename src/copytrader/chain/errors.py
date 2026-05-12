"""RPC error wrappers.

Two invariants must hold (T3, T4 prevention):
  1. API keys embedded in RPC URLs must never appear in `str(exception)`.
  2. The full JSON-RPC error body must be retained, not summarized to nothing.
"""
from __future__ import annotations

import re

# Strips the last URL path segment if it looks like an API key (>= 16 alphanum).
_KEY_RE = re.compile(r"(/[A-Za-z0-9_-]{16,})(?=/?$|\?)")


def redact_url(url: str) -> str:
    if not url:
        return url
    return _KEY_RE.sub("/***", url)


def redact(text: str | None) -> str:
    if not text:
        return text or ""
    return _KEY_RE.sub("/***", text)


class RpcError(Exception):
    """JSON-RPC or HTTP transport error.

    `body` retains the raw error response so operators can debug 4xx/5xx
    without losing context (T4 prevention).
    """

    def __init__(
        self,
        message: str,
        *,
        url: str | None = None,
        status: int | None = None,
        code: int | None = None,
        body: dict | str | None = None,
    ):
        self.url = redact_url(url) if url else None
        self.status = status
        self.code = code
        self.body = body
        super().__init__(self._format(message))

    def _format(self, message: str) -> str:
        parts = [redact(message)]
        if self.status is not None:
            parts.append(f"status={self.status}")
        if self.code is not None:
            parts.append(f"code={self.code}")
        if self.url:
            parts.append(f"url={self.url}")
        if self.body is not None:
            # Truncate for readability but include the head.
            b = str(self.body)
            if len(b) > 500:
                b = b[:500] + "...(truncated)"
            parts.append(f"body={redact(b)}")
        return " | ".join(parts)


class RpcAuthError(RpcError):
    """401/403 from RPC provider — usually a bad or expired API key."""


class RpcRateLimitError(RpcError):
    """429 from RPC provider — back off and retry."""


class RpcChunkTooLargeError(RpcError):
    """Provider rejected the block range (Alchemy: eth_getLogs > 10k blocks)."""
