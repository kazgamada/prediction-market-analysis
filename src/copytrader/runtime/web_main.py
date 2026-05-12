"""`web` process entrypoint.

Boots:
  1. setup_logging() + boot-environment dump (which secrets are set, redacted)
  2. /healthz /readyz server on $HEALTH_PORT in a background thread.
     The health server starts FIRST — before alembic — so that even if a
     migration crash makes the app unable to serve the UI, /readyz still
     responds with the failure reason. This trades a small race (between
     server-bind and migrate-start) for huge observability.
  3. alembic migration (best-effort; failure is logged but does NOT exit)
  4. Streamlit on $STREAMLIT_SERVER_PORT (replaces the current process)
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from pathlib import Path

from copytrader.chain.errors import redact_url
from copytrader.config import settings
from copytrader.health.server import HealthServer
from copytrader.logging_setup import setup_logging

log = logging.getLogger("runtime.web")

_MIGRATION_STATE: dict[str, str | None] = {"status": "pending", "error": None}


def _dump_boot_env() -> None:
    """Log which secrets are present (values redacted). T3 prevention.

    This is the first thing operators look at after a deploy: it confirms
    secrets propagated and that the URLs aren't typos.
    """
    def present(name: str) -> str:
        v = os.environ.get(name) or ""
        return f"set (len={len(v)})" if v else "UNSET"

    log.info("boot env:")
    log.info("  DATABASE_URL: %s", present("DATABASE_URL"))
    log.info("  POLYGON_RPC_HTTP: %s (%s)",
             present("POLYGON_RPC_HTTP"), redact_url(settings.polygon_rpc_http))
    log.info("  POLYGON_RPC_WS: %s (%s)",
             present("POLYGON_RPC_WS"), redact_url(settings.polygon_rpc_ws))
    log.info("  WEB_PASSWORD: %s", present("WEB_PASSWORD"))
    log.info("  STREAMLIT_SERVER_PORT: %s",
             os.environ.get("STREAMLIT_SERVER_PORT", "(default 8501)"))
    log.info("  HEALTH_PORT: %s", settings.health_port)


def _rpc_check_factory():
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
    """Start the health server in a daemon thread so the main thread can
    proceed to exec streamlit. The server keeps running even after main
    threads have moved on — until execvp replaces the process image.
    """
    rpc_check = _rpc_check_factory()
    health = HealthServer(settings.health_port, rpc_check)

    # Augment readyz with migration status.
    original_readyz = health.readyz

    async def readyz_with_migration(request):  # type: ignore[no-untyped-def]
        resp = await original_readyz(request)
        try:
            import json
            body = json.loads(resp.body.decode())
        except Exception:  # noqa: BLE001
            body = {}
        body["migration"] = _MIGRATION_STATE
        from aiohttp import web as _w
        status = 200 if (body.get("db") == "ok"
                         and _MIGRATION_STATE["status"] == "ok") else 503
        return _w.json_response(body, status=status)

    health.readyz = readyz_with_migration  # type: ignore[assignment]

    def runner() -> None:
        asyncio.run(health.run_forever())

    t = threading.Thread(target=runner, name="health", daemon=True)
    t.start()


def _run_migrations_safely() -> None:
    global _MIGRATION_STATE
    try:
        from copytrader.db.engine import run_migrations
        run_migrations()
        _MIGRATION_STATE = {"status": "ok", "error": None}
    except Exception as e:  # noqa: BLE001
        log.exception("migration failed; web will start in degraded mode")
        _MIGRATION_STATE = {
            "status": "failed",
            "error": f"{type(e).__name__}: {e}",
        }


def main() -> None:
    setup_logging()
    log.info("web_main: boot start (git_sha=%s build_time=%s)",
             settings.git_sha, settings.build_time)
    _dump_boot_env()

    # Step 1: health server first so /readyz responds even if migrate fails.
    _start_health_in_thread()

    # Step 2: migrate (best-effort; degraded mode if it fails).
    _run_migrations_safely()

    # Step 3: hand off to streamlit.
    app_py = Path(__file__).parent.parent / "web" / "app.py"
    argv = [
        "streamlit", "run", str(app_py),
        "--server.port", os.environ.get("STREAMLIT_SERVER_PORT", "8501"),
        "--server.address", os.environ.get("STREAMLIT_SERVER_ADDRESS", "0.0.0.0"),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    log.info("exec: %s", " ".join(argv))
    try:
        os.execvp("streamlit", argv)
    except FileNotFoundError:
        log.exception("streamlit not on PATH; falling back to python -m streamlit")
        argv2 = [sys.executable, "-m", "streamlit", *argv[1:]]
        os.execvp(sys.executable, argv2)
    sys.exit(1)


if __name__ == "__main__":
    main()
