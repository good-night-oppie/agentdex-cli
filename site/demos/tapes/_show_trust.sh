#!/usr/bin/env bash
# Gap 3 helper — show the 4-signal trust composite for the first demo agent.
set -euo pipefail
DB="$1"
AGENT=$(uv run bene --json ls --db "$DB" | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["agent_id"])')
uv run bene trust "$AGENT" --db "$DB" | python3 -m json.tool | head -28
