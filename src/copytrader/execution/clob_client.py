"""py-clob-client wrapper with fail-soft credentials handling.

If CLOB_API_KEY/SECRET/PASSPHRASE or TRADER_PRIVATE_KEY are unset, all
order-placing methods return a "dry-run" result with no network call. This
lets us deploy code into Phase A (paper) without touching live trading.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

log = logging.getLogger("execution.clob")

CLOB_HOST = os.environ.get("CLOB_HOST", "https://clob.polymarket.com")


@dataclass(frozen=True)
class OrderResult:
    success: bool
    order_id: str | None
    error: str | None = None
    dry_run: bool = False


def _creds_present() -> bool:
    return all(
        os.environ.get(k)
        for k in (
            "CLOB_API_KEY",
            "CLOB_API_SECRET",
            "CLOB_API_PASSPHRASE",
            "TRADER_PRIVATE_KEY",
        )
    )


class ClobClient:
    """Thin wrapper over py-clob-client. Lazy-loaded so import never fails."""

    def __init__(self) -> None:
        self._impl = None
        self._init_error: str | None = None

    def _ensure_impl(self) -> bool:
        if self._impl is not None:
            return True
        if not _creds_present():
            self._init_error = "credentials missing (dry-run mode)"
            return False
        try:
            from py_clob_client.client import ClobClient as _Impl
            from py_clob_client.constants import POLYGON

            self._impl = _Impl(
                host=CLOB_HOST,
                key=os.environ["TRADER_PRIVATE_KEY"],
                chain_id=POLYGON,
            )
            api_creds_cls = self._impl.create_api_key  # noqa: F841
            self._impl.set_api_creds(
                self._impl.derive_api_key(
                    key=os.environ["CLOB_API_KEY"],
                    secret=os.environ["CLOB_API_SECRET"],
                    passphrase=os.environ["CLOB_API_PASSPHRASE"],
                ),
            )
            return True
        except Exception as e:  # noqa: BLE001
            self._init_error = f"py-clob-client init failed: {e}"
            log.warning(self._init_error)
            return False

    def post_order(
        self,
        *,
        token_id: int,
        side: int,
        size_shares: Decimal,
        price: Decimal,
        tif: str = "GTC",
    ) -> OrderResult:
        """Submit a limit order. Returns OrderResult.

        side: 0=BUY, 1=SELL (matches our internal convention).
        """
        if not self._ensure_impl():
            log.info(
                "DRY-RUN post_order token=%s side=%s size=%s price=%s tif=%s reason=%s",
                token_id, side, size_shares, price, tif, self._init_error,
            )
            return OrderResult(
                success=True, order_id=None, error=None, dry_run=True,
            )
        try:
            from py_clob_client.clob_types import OrderArgs

            args = OrderArgs(
                price=float(price),
                size=float(size_shares),
                side="BUY" if side == 0 else "SELL",
                token_id=str(token_id),
            )
            resp: Any = self._impl.create_and_post_order(args)
            order_id = (resp or {}).get("orderID") or (resp or {}).get("order_id")
            return OrderResult(
                success=bool(order_id),
                order_id=order_id,
                error=None if order_id else str(resp),
            )
        except Exception as e:  # noqa: BLE001
            log.exception("post_order failed: %s", e)
            return OrderResult(success=False, order_id=None, error=str(e))

    def cancel_order(self, order_id: str) -> bool:
        if not self._ensure_impl():
            log.info("DRY-RUN cancel_order %s", order_id)
            return True
        try:
            self._impl.cancel(order_id=order_id)
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("cancel_order %s failed: %s", order_id, e)
            return False

    def get_order(self, order_id: str) -> dict | None:
        if not self._ensure_impl():
            return None
        try:
            return self._impl.get_order(order_id=order_id)
        except Exception as e:  # noqa: BLE001
            log.warning("get_order %s failed: %s", order_id, e)
            return None


_singleton: ClobClient | None = None


def get_clob() -> ClobClient:
    global _singleton
    if _singleton is None:
        _singleton = ClobClient()
    return _singleton
