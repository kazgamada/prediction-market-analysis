#!/usr/bin/env bash
# One-shot Fly.io deploy for the polymarket-copytrader monitor process.
#
# Preconditions you must have set up beforehand:
#   1. flyctl installed and `fly auth login` done
#   2. POLYGON_RPC_HTTP and POLYGON_RPC_WS in env (or .env, sourced below)
#   3. Optional: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
#   4. For paper/live processes: POLYMARKET_API_KEY/SECRET/PASSPHRASE,
#      WALLET_PRIVATE_KEY, optional WALLET_PROXY_ADDRESS
#
# What it does (idempotent):
#   - Reads .env if present
#   - `fly launch --no-deploy --copy-config` (first time) or noop
#   - Creates an attached managed Postgres if one isn't attached
#   - Pushes the required secrets
#   - Deploys; release_command runs alembic upgrade head
#
# Usage:
#   ./scripts/deploy-fly.sh                   # deploy monitor
#   APP=my-app-name ./scripts/deploy-fly.sh   # custom app name

set -euo pipefail

APP="${APP:-polymarket-copytrader}"
REGION="${REGION:-nrt}"

if ! command -v fly >/dev/null 2>&1 && ! command -v flyctl >/dev/null 2>&1; then
  echo "flyctl not found. Install: https://fly.io/docs/hands-on/install-flyctl/" >&2
  exit 1
fi
FLY="$(command -v fly || command -v flyctl)"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  . .env
  set +a
fi

: "${POLYGON_RPC_HTTP:?POLYGON_RPC_HTTP is required}"
: "${POLYGON_RPC_WS:?POLYGON_RPC_WS is required}"

# 1. App
if ! "$FLY" apps list 2>/dev/null | awk '{print $1}' | grep -qx "$APP"; then
  echo ">> creating app $APP in $REGION"
  "$FLY" apps create "$APP" --machines
else
  echo ">> app $APP already exists"
fi

# 2. Postgres
if ! "$FLY" pg list 2>/dev/null | awk '{print $1}' | grep -qx "${APP}-db"; then
  echo ">> creating attached managed Postgres ${APP}-db"
  "$FLY" pg create --name "${APP}-db" --region "$REGION" --vm-size shared-cpu-1x --initial-cluster-size 1 --volume-size 3
  "$FLY" pg attach "${APP}-db" --app "$APP"
else
  echo ">> postgres ${APP}-db already exists"
fi

# 3. Secrets
secrets=(
  "POLYGON_RPC_HTTP=$POLYGON_RPC_HTTP"
  "POLYGON_RPC_WS=$POLYGON_RPC_WS"
)
[[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] && secrets+=("TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN")
[[ -n "${TELEGRAM_CHAT_ID:-}"   ]] && secrets+=("TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID")
[[ -n "${POLYMARKET_API_KEY:-}" ]] && secrets+=("POLYMARKET_API_KEY=$POLYMARKET_API_KEY")
[[ -n "${POLYMARKET_API_SECRET:-}"     ]] && secrets+=("POLYMARKET_API_SECRET=$POLYMARKET_API_SECRET")
[[ -n "${POLYMARKET_API_PASSPHRASE:-}" ]] && secrets+=("POLYMARKET_API_PASSPHRASE=$POLYMARKET_API_PASSPHRASE")
[[ -n "${WALLET_PRIVATE_KEY:-}"        ]] && secrets+=("WALLET_PRIVATE_KEY=$WALLET_PRIVATE_KEY")
[[ -n "${WALLET_PROXY_ADDRESS:-}"      ]] && secrets+=("WALLET_PROXY_ADDRESS=$WALLET_PROXY_ADDRESS")

echo ">> setting ${#secrets[@]} secrets"
"$FLY" secrets set --app "$APP" "${secrets[@]}"

# 4. Deploy
echo ">> deploying"
"$FLY" deploy --app "$APP" --config fly.toml

echo
echo "Deployment complete."
echo "Tail logs:    $FLY logs --app $APP"
echo "Open shell:   $FLY ssh console --app $APP"
echo "Run rank:     $FLY ssh console --app $APP -C 'copytrader rank --window 30 --watchlist-top 10'"
echo "Switch to paper mode: edit fly.toml processes -> paper, then $FLY deploy"
