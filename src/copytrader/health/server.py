"""Lightweight aiohttp /healthz /readyz server + Stripe webhook."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from aiohttp import web

from copytrader.db.engine import ping as db_ping

log = logging.getLogger(__name__)

_RPC_CACHE_SECONDS = 30


@dataclass
class _RpcSelfTest:
    ok: bool
    detail: str
    checked_at: float


class HealthServer:
    def __init__(
        self,
        port: int,
        rpc_check: Callable[[], Awaitable[tuple[bool, str]]] | None = None,
    ):
        self.port = port
        self.rpc_check = rpc_check
        self._cached: _RpcSelfTest | None = None
        self._lock = asyncio.Lock()

    async def _get_rpc(self) -> _RpcSelfTest:
        now = time.time()
        if self._cached and now - self._cached.checked_at < _RPC_CACHE_SECONDS:
            return self._cached
        async with self._lock:
            if self._cached and time.time() - self._cached.checked_at < _RPC_CACHE_SECONDS:
                return self._cached
            if self.rpc_check is None:
                self._cached = _RpcSelfTest(False, "no rpc_check configured", time.time())
            else:
                try:
                    ok, detail = await self.rpc_check()
                except Exception as e:  # noqa: BLE001
                    ok, detail = False, f"{type(e).__name__}: {e}"
                self._cached = _RpcSelfTest(ok, detail, time.time())
        return self._cached

    async def healthz(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def readyz(self, _request: web.Request) -> web.Response:
        db_ok = db_ping()
        rpc = await self._get_rpc()
        body = {
            "status": "ok" if db_ok else "degraded",
            "db": "ok" if db_ok else "down",
            "rpc": "ok" if rpc.ok else "down",
            "rpc_detail": rpc.detail,
            "rpc_checked_at": rpc.checked_at,
        }
        status = 200 if db_ok else 503
        return web.json_response(body, status=status)

    def make_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/healthz", self.healthz)
        app.router.add_get("/readyz", self.readyz)
        app.router.add_post("/stripe/webhook", stripe_webhook)
        return app

    async def run_forever(self) -> None:
        runner = web.AppRunner(self.make_app())
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=self.port)
        await site.start()
        log.info("health server listening on :%d", self.port)
        await asyncio.Event().wait()


async def stripe_webhook(request: web.Request) -> web.Response:
    """Stripe Webhook ハンドラ（署名検証付き）。"""
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")

    if not stripe_key:
        log.warning("STRIPE_SECRET_KEY not set; ignoring webhook")
        return web.Response(status=200, text="ok")

    payload = await request.read()
    sig = request.headers.get("Stripe-Signature", "")

    try:
        import stripe
        stripe.api_key = stripe_key

        if webhook_secret:
            event = stripe.Webhook.construct_event(payload, sig, webhook_secret)
        else:
            import json
            event = json.loads(payload)
            log.warning("STRIPE_WEBHOOK_SECRET not set; skipping signature verification")
    except Exception as e:  # noqa: BLE001
        log.warning("stripe webhook signature verification failed: %s", e)
        return web.Response(status=400, text="invalid signature")

    event_type = event.get("type", "")
    event_data = event.get("data", {}).get("object", {})

    if event_type == "invoice.paid":
        _handle_invoice_paid(event_data)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(event_data)
    elif event_type == "charge.refunded":
        _handle_refund(event_data)
    else:
        log.debug("unhandled stripe event type: %s", event_type)

    return web.Response(status=200, text="ok")


def _handle_invoice_paid(invoice: dict) -> None:
    """invoice.paid イベント処理: subscription_status を active に更新。"""
    customer_id = invoice.get("customer")
    if not customer_id:
        return
    try:
        from sqlalchemy import select

        from copytrader.db.engine import get_session
        from copytrader.db.models import User

        with get_session() as s:
            user = s.execute(
                select(User).where(User.stripe_customer_id == customer_id)
            ).scalar_one_or_none()
            if user:
                user.subscription_status = "active"
                log.info("invoice.paid: updated user %s status to active", user.email)
    except Exception:  # noqa: BLE001
        log.warning("_handle_invoice_paid failed", exc_info=True)


def _handle_subscription_updated(subscription: dict) -> None:
    """customer.subscription.updated イベント処理: ステータス更新。"""
    customer_id = subscription.get("customer")
    status = subscription.get("status")
    period_end_ts = subscription.get("current_period_end")
    if not customer_id:
        return
    try:
        import datetime

        from sqlalchemy import select

        from copytrader.db.engine import get_session
        from copytrader.db.models import User

        with get_session() as s:
            user = s.execute(
                select(User).where(User.stripe_customer_id == customer_id)
            ).scalar_one_or_none()
            if user:
                user.subscription_status = status
                if period_end_ts:
                    user.subscription_period_end = datetime.datetime.fromtimestamp(
                        period_end_ts, tz=datetime.UTC
                    )
                log.info("subscription.updated: user %s status=%s", user.email, status)
    except Exception:  # noqa: BLE001
        log.warning("_handle_subscription_updated failed", exc_info=True)


def _handle_refund(charge: dict) -> None:
    """charge.refunded イベント処理: ログ記録のみ。"""
    log.info("charge.refunded: charge_id=%s amount_refunded=%s",
             charge.get("id"), charge.get("amount_refunded"))
