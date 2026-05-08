"""chain.errors のレダクション / 変換テスト。"""

from __future__ import annotations

from copytrader.chain.errors import RpcError, redact_rpc_url, to_rpc_error


def test_redact_alchemy_key():
    msg = (
        "400 Client Error: Bad Request for url: "
        "https://polygon-mainnet.g.alchemy.com/v2/nOJ3Rwx0CYXLlMVHaJIc2"
    )
    redacted = redact_rpc_url(msg)
    assert "nOJ3Rwx0CYXLlMVHaJIc2" not in redacted
    assert "<redacted>" in redacted
    assert "polygon-mainnet.g.alchemy.com/v2/" in redacted


def test_redact_infura_key():
    msg = "boom https://mainnet.infura.io/v3/abcdef0123456789 oops"
    assert "abcdef0123456789" not in redact_rpc_url(msg)


def test_to_rpc_error_400_includes_hint():
    raw = Exception(
        "400 Client Error: Bad Request for url: "
        "https://polygon-mainnet.g.alchemy.com/v2/SECRETKEY"
    )
    err = to_rpc_error(raw)
    assert isinstance(err, RpcError)
    s = str(err)
    assert "SECRETKEY" not in s
    assert "HTTP 400" in s
    assert "POLYGON_RPC_HTTP" in s


def test_to_rpc_error_passthrough_for_non_http():
    err = to_rpc_error(ValueError("query returned more than 10000 results: too large"))
    # 「too large」検出が iter_logs の自動分割で機能し続けることを保証する。
    assert "too large" in str(err).lower()
