"""Lightweight aiohttp /healthz /readyz server.

Started inside each runtime process so that Fly.io and curl can answer
"is this process alive?" without parsing Streamlit's HTML. Result of the
last RPC self-test is cached for 30 seconds (T21 prevention: observability
shipped from S1, not bolted on later).
"""
from __future__ import annotations

import asyncio
import logging
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
        return app

    async def run_forever(self) -> None:
        runner = web.AppRunner(self.make_app())
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=self.port)
        await site.start()
        log.info("health server listening on :%d", self.port)
        # Park forever.
        await asyncio.Event().wait()
