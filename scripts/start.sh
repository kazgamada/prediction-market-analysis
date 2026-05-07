#!/bin/bash
set -u

# Kick off the data download in the background so the web service can come up
# immediately for healthchecks. /api/markets returns a friendly 404 until the
# download.sh sentinel is in place.
(
    bash scripts/download.sh \
        || echo "[start.sh] scripts/download.sh failed; /api/markets will keep returning 404 until data is seeded."
) &

exec uv run --no-sync uvicorn web.server:app --host 0.0.0.0 --port "${PORT:-8000}"
