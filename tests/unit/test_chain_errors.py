"""T3 / T4: URL keys redacted, error bodies preserved."""
from __future__ import annotations

from copytrader.chain.errors import RpcError, redact, redact_url


def test_redact_url_strips_api_key_segment() -> None:
    raw = "https://polygon-mainnet.g.alchemy.com/v2/abc123XYZ_456789-key"
    out = redact_url(raw)
    assert "abc123XYZ_456789-key" not in out
    assert out.endswith("/***")


def test_redact_url_no_key_unchanged() -> None:
    raw = "https://example.com/rpc"
    assert redact_url(raw) == raw


def test_redact_url_empty() -> None:
    assert redact_url("") == ""


def test_redact_string_strips_key() -> None:
    msg = "fetch failed at https://rpc.example.com/v2/sk_live_abcdefghij1234567890"
    out = redact(msg)
    assert "sk_live_abcdefghij1234567890" not in out


def test_rpc_error_preserves_body() -> None:
    body = {"error": {"code": -32000, "message": "boom"}}
    e = RpcError(
        "rpc failed",
        url="https://x.example.com/v2/sk_live_abcdefghij1234567890",
        status=500,
        code=-32000,
        body=body,
    )
    s = str(e)
    assert "sk_live_abcdefghij1234567890" not in s, "API key leaked!"
    assert "boom" in s, "body content must be preserved"
    assert e.body == body, "body attr unchanged for debugging"


def test_rpc_error_truncates_long_body() -> None:
    body = "x" * 5000
    e = RpcError("bad", body=body)
    s = str(e)
    assert "truncated" in s
    assert len(s) < 2000
