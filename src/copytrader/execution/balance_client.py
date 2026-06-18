"""On-chain balance reader for the risk evaluator's USDC/MATIC floors.

Reads the trader wallet's native (MATIC/POL) balance and an ERC-20 balance
(USDC by default) via JSON-RPC, returning human-scale Decimals. The risk
evaluator consumes these through the `usdc_balance_cache` / `matic_balance_cache`
settings keys (written by the `balance_refresh` job) — see risk.evaluator.

Addresses/decimals are env-overridable so this is not pinned to one chain:
  TRADER_ADDRESS   - wallet to read (required; else returns None)
  USDC_CONTRACT    - ERC-20 token address (default: Polygon bridged USDC.e)
  USDC_DECIMALS    - token decimals (default 6)
"""
from __future__ import annotations

import logging
import os
from decimal import Decimal

from copytrader.chain.client import JsonRpcClient

log = logging.getLogger("execution.balance_client")

# keccak256("balanceOf(address)")[:4]
_BALANCE_OF_SELECTOR = "0x70a08231"
# Polygon bridged USDC.e (the collateral Polymarket settles in).
_DEFAULT_USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"


def _balance_of_calldata(address: str) -> str:
    addr = address.lower().removeprefix("0x").rjust(64, "0")
    return _BALANCE_OF_SELECTOR + addr


async def fetch_balances(client: JsonRpcClient) -> dict[str, Decimal] | None:
    """Return {"usdc": Decimal, "matic": Decimal} or None if no wallet set."""
    address = os.environ.get("TRADER_ADDRESS", "").strip()
    if not address:
        log.info("balance_client: TRADER_ADDRESS unset; skipping")
        return None

    usdc_contract = os.environ.get("USDC_CONTRACT", _DEFAULT_USDC)
    usdc_decimals = int(os.environ.get("USDC_DECIMALS", "6"))

    matic_wei = await client.get_native_balance(address)
    matic = Decimal(matic_wei) / Decimal(10**18)

    raw = await client.eth_call(usdc_contract, _balance_of_calldata(address))
    usdc_units = int(raw, 16) if raw and raw != "0x" else 0
    usdc = Decimal(usdc_units) / Decimal(10**usdc_decimals)

    return {"usdc": usdc, "matic": matic}
