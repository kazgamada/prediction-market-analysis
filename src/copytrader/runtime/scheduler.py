"""Tiny async interval scheduler: periodic tasks alongside the WS subscriber."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

log = logging.getLogger(__name__)


async def run_every(name: str, seconds: float, fn: Callable[[], Awaitable[None]]) -> None:
    """Run `fn` on a fixed interval forever, swallowing per-iteration errors."""
    while True:
        try:
            await fn()
        except Exception as e:
            log.exception("periodic task %s failed: %s", name, e)
        await asyncio.sleep(seconds)


async def run_every_sync(name: str, seconds: float, fn: Callable[[], None]) -> None:
    """Run a blocking sync `fn` on an interval, off the event loop."""
    loop = asyncio.get_running_loop()
    while True:
        try:
            await loop.run_in_executor(None, fn)
        except Exception as e:
            log.exception("periodic task %s failed: %s", name, e)
        await asyncio.sleep(seconds)
