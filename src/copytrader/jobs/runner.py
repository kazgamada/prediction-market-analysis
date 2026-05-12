"""Worker main loop. Run from the worker process."""
from __future__ import annotations

import asyncio
import logging
import os
import socket

from copytrader.jobs.handlers import HANDLERS
from copytrader.jobs.queue import JobHandle, claim

log = logging.getLogger(__name__)

POLL_S = 2.0


def _worker_id() -> str:
    return f"{socket.gethostname()}/{os.getpid()}"


def _run_once(worker_id: str) -> bool:
    with claim(worker_id) as job:
        if job is None:
            return False
        handler = HANDLERS.get(job.kind)
        if handler is None:
            raise RuntimeError(f"no handler for kind={job.kind}")
        handle = JobHandle(job)
        handle.log(f"start kind={job.kind} worker={worker_id}")
        handler(handle)
        handle.log("done")
        return True


async def run() -> None:
    worker_id = _worker_id()
    log.info("worker starting: %s", worker_id)
    while True:
        ran = False
        try:
            ran = await asyncio.to_thread(_run_once, worker_id)
        except Exception:  # noqa: BLE001
            log.exception("worker loop error")
        if not ran:
            await asyncio.sleep(POLL_S)
