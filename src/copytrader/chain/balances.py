"""Read on-chain CTF outcome-token balances for a holder."""

from __future__ import annotations

from decimal import Decimal

from web3 import Web3

from copytrader.chain.client import PolygonClient
from copytrader.chain.contracts import (
    CONDITIONAL_TOKENS,
    CTF_BALANCE_OF_ABI,
    TOKEN_DECIMALS,
)

TOKEN_UNIT = Decimal(10) ** TOKEN_DECIMALS


def get_ctf_balance(holder: str, token_id: str | int, client: PolygonClient | None = None) -> Decimal:
    """Return the on-chain CTF balance for `holder` of `token_id` in token units."""
    client = client or PolygonClient()
    contract = client.w3.eth.contract(
        address=Web3.to_checksum_address(CONDITIONAL_TOKENS),
        abi=CTF_BALANCE_OF_ABI,
    )
    raw = contract.functions.balanceOf(
        Web3.to_checksum_address(holder), int(token_id)
    ).call()
    return Decimal(raw) / TOKEN_UNIT


def get_ctf_balances(holder: str, token_ids: list[str], client: PolygonClient | None = None) -> dict[str, Decimal]:
    """Read balances for many token_ids sequentially. Multicall would be faster
    but plain reads are fine at our scale and avoid extra contract deps."""
    client = client or PolygonClient()
    out: dict[str, Decimal] = {}
    for tid in token_ids:
        try:
            out[tid] = get_ctf_balance(holder, tid, client)
        except Exception:
            out[tid] = Decimal(0)
    return out
