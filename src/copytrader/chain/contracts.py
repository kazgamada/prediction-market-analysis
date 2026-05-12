"""Polygon mainnet contract addresses + event signatures.

V2 only (T2 prevention). Addresses can be overridden via the `settings`
table at runtime if Polymarket ever redeploys.
"""
from __future__ import annotations

from eth_utils import keccak

from copytrader.db import settings_table

# ----- Defaults (Polygon mainnet, fetched 2026-05-12 from ctf-exchange-v2 repo) -----

CTF_EXCHANGE_V2 = "0xE111180000d2663C0091e4f400237545B87B996B".lower()
NEG_RISK_CTF_EXCHANGE_V2 = "0xe2222d279d744050d28e00520010520000310F59".lower()

# Standard Polygon mainnet tokens.
USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174".lower()
CONDITIONAL_TOKENS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045".lower()

# Event signature (V2): OrderFilled(bytes32, address, address, uint8, uint256, uint256, uint256, uint256, bytes32, bytes32)
# First three args indexed (orderHash, maker, taker).
ORDER_FILLED_SIG = (
    "OrderFilled(bytes32,address,address,uint8,uint256,uint256,uint256,uint256,bytes32,bytes32)"
)
ORDER_FILLED_TOPIC0 = "0x" + keccak(text=ORDER_FILLED_SIG).hex()


def exchange_addresses() -> list[str]:
    """Return the list of exchange addresses to subscribe to, settings table-aware."""
    override = settings_table.get("exchange_addresses")
    if override:
        return [a.lower() for a in override]
    return [CTF_EXCHANGE_V2, NEG_RISK_CTF_EXCHANGE_V2]


def order_filled_topic0() -> str:
    override = settings_table.get("order_filled_topic0")
    if override:
        return override.lower()
    return ORDER_FILLED_TOPIC0


def exchange_name(address: str) -> str:
    a = address.lower()
    if a == CTF_EXCHANGE_V2:
        return "ctf"
    if a == NEG_RISK_CTF_EXCHANGE_V2:
        return "neg_risk"
    return "unknown"
