"""Single place where logging is configured."""
from __future__ import annotations

import logging
import os
import sys

_DONE = False


def setup_logging(level: str | int | None = None) -> None:
    global _DONE
    if _DONE:
        return
    lvl = level or os.environ.get("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # Mute noisy 3rd party loggers.
    for name in ("websockets.client", "websockets.server", "web3.providers", "httpx", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
    _DONE = True
