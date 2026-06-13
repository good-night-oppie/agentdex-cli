#!/usr/bin/env bash
# Bootstrap: generate keypair, enroll, wait for confirmation code, mint token.
#
# Usage:
#   OWNER_EMAIL=you@you.com AGENT_NAME=my-bot ./scripts/bootstrap.sh
#
# After it runs you'll have:
#   ./.state/<agent>.key   — Ed25519 priv key (RAW 32B). KEEP PRIVATE.
#   ./.state/<agent>.token — bearer token (7-day expiry). Set ARENA_TOKEN=$(cat ...)
#
# The confirmation code is delivered to OWNER_EMAIL via the deployed owner channel
# (file inbox for local dev, webhook for prod). For local: tail the file inbox.

set -euo pipefail

ARENA="${ARENA_BASE:-https://agentdex.ai-builders.space}"
OWNER_EMAIL="${OWNER_EMAIL:?set OWNER_EMAIL=you@you.com}"
AGENT_NAME="${AGENT_NAME:?set AGENT_NAME=my-bot}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$HERE/.state"
KEYFILE="$HERE/.state/$AGENT_NAME.key"
TOKENFILE="$HERE/.state/$AGENT_NAME.token"

if [ -f "$KEYFILE" ]; then
  echo "[bootstrap] reusing existing keypair: $KEYFILE"
else
  echo "[bootstrap] generating new Ed25519 keypair → $KEYFILE"
fi

cd "$HERE"
uv run python -c "
import sys
from pathlib import Path
from arena_client import AgentIdentity, ArenaClient

name, keyfile, tokenfile = '$AGENT_NAME', Path('$KEYFILE'), Path('$TOKENFILE')
if keyfile.exists():
    agent = AgentIdentity.load(name, keyfile)
else:
    agent = AgentIdentity.new(name)
    agent.save(keyfile)
    keyfile.chmod(0o600)

c = ArenaClient('$ARENA')
print('[bootstrap] requesting enrollment...', file=sys.stderr)
r = c.enroll_request(owner_email='$OWNER_EMAIL', agent=agent)
print('[bootstrap] enrollment requested; check $OWNER_EMAIL for confirmation code', file=sys.stderr)
print('[bootstrap] then run: uv run python -c \"from arena_client import ArenaClient; print(ArenaClient(\\\"$ARENA\\\").enroll_confirm(\\\"<CODE>\\\"))\" > $TOKENFILE')
"
echo "[bootstrap] done. Once you have the token, save it to $TOKENFILE then:"
echo "  export ARENA_TOKEN=\$(cat $TOKENFILE)"
echo "  uv run python agents/max_damage_agent.py --token \"\$ARENA_TOKEN\" \\"
echo "    --keyfile $KEYFILE --agent-name $AGENT_NAME --team-file team.txt --lane sandbox"
