"""`web` process entrypoint.

Boots:
  1. alembic migration
  2. /healthz /readyz server on $HEALTH_PORT in a background thread
  3. Streamlit on $STREAMLIT_SERVER_PORT (replaces the current process)

We exec streamlit so Fly.io's auto-restart still works cleanly.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from pathlib import Path

from copytrader.config import settings
from copytrader.db.engine import run_migrations
from copytrader.health.server import HealthServer
from copytrader.logging_setup import setup_logging

log = logging.getLogger("runtime.web")


def _rpc_check_factory():
    """Return an awaitable RPC self-test (only valid if RPC_HTTP is set)."""
    if not settings.polygon_rpc_http:
        async def stub() -> tuple[bool, str]:
            return False, "polygon_rpc_http unset"
        return stub
    from copytrader.chain.client import JsonRpcClient

    async def check() -> tuple[bool, str]:
        client = JsonRpcClient(settings.polygon_rpc_http)
        try:
            block = await client.get_block_number()
            return True, f"head={block}"
        finally:
            await client.aclose()

    return check


def _start_health_in_thread() -> None:
    def runner() -> None:
        asyncio.run(HealthServer(settings.health_port, _rpc_check_factory()).run_forever())

    t = threading.Thread(target=runner, name="health", daemon=True)
    t.start()


def main() -> None:
    setup_logging()
    run_migrations()
    _start_health_in_thread()

    # Hand off to streamlit. Use exec so streamlit owns the process.
    app_py = Path(__file__).parent.parent / "web" / "app.py"
    argv = [
        "streamlit", "run", str(app_py),
        "--server.port", os.environ.get("STREAMLIT_SERVER_PORT", "8501"),
        "--server.address", os.environ.get("STREAMLIT_SERVER_ADDRESS", "0.0.0.0"),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    log.info("exec: %s", " ".join(argv))
    # streamlit is on PATH via the installed package
    os.execvp("streamlit", argv)
    # Unreachable
    sys.exit(1)


if __name__ == "__main__":
    main()
