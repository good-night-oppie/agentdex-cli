#!/usr/bin/env bash
# Boot a local Pokémon Showdown server for the poke-env battle substrate (ADR-0014).
#
# Uses the pokemon-showdown binary ALREADY VENDORED in packages/adx_showdown
# (npm dep pokemon-showdown@0.11.10) — no external clone, repo-self-contained.
# Local-first dev runs on 127.0.0.1; the identical invocation runs on the box
# (54.203.252.69) once deployed.
#
# Usage:
#   scripts/adx_ps_server.sh                  # 127.0.0.1:8000, --no-security
#   ADX_PS_HOST=0.0.0.0 ADX_PS_PORT=8000 scripts/adx_ps_server.sh
#
# Then point poke-env at ws://$ADX_PS_HOST:$ADX_PS_PORT/showdown/websocket
# (see scripts/spikes/*.py). --no-security lets any username connect (dev only).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PS_BIN="$REPO_ROOT/packages/adx_showdown/node_modules/.bin/pokemon-showdown"
ADX_PS_HOST="${ADX_PS_HOST:-127.0.0.1}"
ADX_PS_PORT="${ADX_PS_PORT:-8000}"

if [[ ! -x "$PS_BIN" ]]; then
  echo "error: vendored pokemon-showdown not found at $PS_BIN" >&2
  echo "  run 'npm install' in packages/adx_showdown first." >&2
  exit 1
fi

# The npm package ships only config-example.js (v0.11.10 excludes config/* except
# the example), but server/config-loader requires config.js at startup — without
# it the server exits before listening and the poke-env spikes cannot connect.
# Mirror the official `cp config/config-example.js config/config.js` setup step.
PS_CONFIG_DIR="$REPO_ROOT/packages/adx_showdown/node_modules/pokemon-showdown/config"
PS_CONFIG="$PS_CONFIG_DIR/config.js"
if [[ ! -f "$PS_CONFIG" ]]; then
  if [[ ! -f "$PS_CONFIG_DIR/config-example.js" ]]; then
    echo "error: pokemon-showdown config-example.js missing at $PS_CONFIG_DIR" >&2
    echo "  run 'npm install' in packages/adx_showdown first." >&2
    exit 1
  fi
  cp "$PS_CONFIG_DIR/config-example.js" "$PS_CONFIG"
  echo "[adx-ps] created config.js from config-example.js (first run)"
fi

# This is a --no-security server: ANY username connects, no auth. PS reads the
# bind host only from config.js (the 0.11.10 CLI has no bindaddress flag) and its
# config-example default is '0.0.0.0' — every interface. Left at the default, the
# banner says 127.0.0.1 while the socket is actually reachable by anyone who can
# hit the port. So bind explicitly to ADX_PS_HOST, and refuse the all-interfaces
# address unless the operator knowingly opts in.
if [[ "$ADX_PS_HOST" == "0.0.0.0" && "${ADX_PS_ALLOW_PUBLIC:-0}" != "1" ]]; then
  echo "error: refusing to bind a --no-security server to 0.0.0.0 (all interfaces)." >&2
  echo "  that exposes an unauthenticated server to the whole network." >&2
  echo "  set ADX_PS_ALLOW_PUBLIC=1 to opt in, or pin ADX_PS_HOST to a specific IP." >&2
  exit 1
fi
sed -i "s|^exports\.bindaddress = .*|exports.bindaddress = '${ADX_PS_HOST}';|" "$PS_CONFIG"

echo "[adx-ps] starting Pokémon Showdown server on ${ADX_PS_HOST}:${ADX_PS_PORT} (--no-security)"
echo "[adx-ps] websocket: ws://${ADX_PS_HOST}:${ADX_PS_PORT}/showdown/websocket"
echo "[adx-ps] bindaddress pinned to ${ADX_PS_HOST} in config.js"
exec node "$PS_BIN" start --no-security --port "$ADX_PS_PORT"
