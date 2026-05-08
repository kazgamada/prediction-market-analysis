"""Thin wrapper around py-clob-client.

Phase 0-3 only need read access (orderbook / midpoint) which doesn't require
auth. From Phase 4 onward we also need signed order placement; that path
expects WALLET_PRIVATE_KEY + POLYMARKET_API_KEY/SECRET/PASSPHRASE in env.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from copytrader.config import get_settings

log = logging.getLogger(__name__)

POLYGON_CHAIN_ID = 137


@dataclass
class OrderResult:
    success: bool
    order_id: str | None
    error: str | None
    raw: dict | None = None


class ClobClient:
    """Wraps py_clob_client.ClobClient with our config + lazy import.

    The underlying SDK is heavyweight; only import when actually needed so the
    rest of the package (indexer, ranking, backtest) can run without it.
    """

    def __init__(self, *, signed: bool = False):
        self._settings = get_settings()
        self._signed = signed
        self._client = None  # lazily built

    def _ensure(self):
        if self._client is not None:
            return self._client
        from py_clob_client.client import ClobClient as _Sdk

        host = self._settings.polymarket_clob_url
        if self._signed:
            if not self._settings.wallet_private_key:
                raise RuntimeError("WALLET_PRIVATE_KEY required for signed CLOB client")
            if not (
                self._settings.polymarket_api_key
                and self._settings.polymarket_api_secret
                and self._settings.polymarket_api_passphrase
            ):
                raise RuntimeError(
                    "POLYMARKET_API_KEY/SECRET/PASSPHRASE required for signed client"
                )
            from py_clob_client.clob_types import ApiCreds

            creds = ApiCreds(
                api_key=self._settings.polymarket_api_key,
                api_secret=self._settings.polymarket_api_secret,
                api_passphrase=self._settings.polymarket_api_passphrase,
            )
            # signature_type=0 -> EOA. Users with Polymarket UI proxy wallets
            # need signature_type=1 and funder=proxy_address.
            kwargs = dict(host=host, key=self._settings.wallet_private_key, chain_id=POLYGON_CHAIN_ID, creds=creds)
            if self._settings.wallet_proxy_address:
                kwargs.update(signature_type=1, funder=self._settings.wallet_proxy_address)
            self._client = _Sdk(**kwargs)
        else:
            self._client = _Sdk(host=host, chain_id=POLYGON_CHAIN_ID)
        return self._client

    # -- read-only methods --
    def midpoint(self, token_id: str) -> Decimal | None:
        try:
            data = self._ensure().get_midpoint(token_id)
            mid = data.get("mid") if isinstance(data, dict) else data
            return Decimal(str(mid)) if mid is not None else None
        except Exception as e:
            log.warning("midpoint failed token=%s err=%s", token_id, e)
            return None

    def orderbook(self, token_id: str) -> dict | None:
        try:
            return self._ensure().get_order_book(token_id)
        except Exception as e:
            log.warning("orderbook failed token=%s err=%s", token_id, e)
            return None

    def best_price(self, token_id: str, side: str) -> Decimal | None:
        try:
            data = self._ensure().get_price(token_id, side.lower())
            p = data.get("price") if isinstance(data, dict) else data
            return Decimal(str(p)) if p is not None else None
        except Exception as e:
            log.warning("price failed token=%s err=%s", token_id, e)
            return None

    # -- signed methods --
    def balance_allowance(self) -> dict | None:
        try:
            return self._ensure().get_balance_allowance(None)
        except Exception as e:
            log.warning("balance_allowance failed: %s", e)
            return None

    def place_market(
        self,
        token_id: str,
        side: str,
        size_tokens: float,
        limit_price: Optional[float] = None,
    ) -> OrderResult:
        """Place a (limit-priced) market order.

        Polymarket doesn't have true market orders; we pass a limit price aggressive
        enough to cross. If `limit_price` is None we use 0.99 for BUY and 0.01 for
        SELL to ensure execution.
        """
        if not self._signed:
            raise RuntimeError("place_market requires signed=True")
        from py_clob_client.clob_types import OrderArgs, OrderType

        side_str = side.upper()
        if side_str not in ("BUY", "SELL"):
            raise ValueError(f"side must be BUY/SELL, got {side!r}")

        if limit_price is None:
            limit_price = 0.99 if side_str == "BUY" else 0.01

        args = OrderArgs(
            price=float(limit_price),
            size=float(size_tokens),
            side=side_str,
            token_id=token_id,
        )
        try:
            sdk = self._ensure()
            signed = sdk.create_order(args)
            resp = sdk.post_order(signed, OrderType.GTC)
            order_id = (resp or {}).get("orderID") or (resp or {}).get("orderId")
            return OrderResult(success=True, order_id=order_id, error=None, raw=resp)
        except Exception as e:
            log.exception("place_market failed")
            return OrderResult(success=False, order_id=None, error=str(e))

    def cancel(self, order_id: str) -> bool:
        if not self._signed:
            raise RuntimeError("cancel requires signed=True")
        try:
            self._ensure().cancel(order_id=order_id)
            return True
        except Exception as e:
            log.warning("cancel failed id=%s err=%s", order_id, e)
            return False

    def cancel_all(self) -> bool:
        if not self._signed:
            raise RuntimeError("cancel_all requires signed=True")
        try:
            self._ensure().cancel_all()
            return True
        except Exception as e:
            log.warning("cancel_all failed: %s", e)
            return False

    def get_order(self, order_id: str) -> dict | None:
        try:
            return self._ensure().get_order(order_id)
        except Exception as e:
            log.warning("get_order failed id=%s err=%s", order_id, e)
            return None

    def get_trades(self, order_id: str | None = None) -> list[dict]:
        try:
            sdk = self._ensure()
            if order_id:
                return list(sdk.get_trades({"id": order_id}) or [])
            return list(sdk.get_trades() or [])
        except Exception as e:
            log.warning("get_trades failed: %s", e)
            return []
