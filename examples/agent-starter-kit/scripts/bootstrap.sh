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
import httpx
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
try:
    r = c.enroll_request(owner_email='$OWNER_EMAIL', agent=agent)
except ValueError as e:
    print(f'[bootstrap] error: {e}', file=sys.stderr)
    sys.exit(2)
except httpx.HTTPStatusError as e:
    code = e.response.status_code
    print(f'[bootstrap] enrollment rejected: HTTP {code} {e.response.text[:200]}', file=sys.stderr)
    print('[bootstrap] common causes: 409 = agent_name already taken (pick another AGENT_NAME); 422 = OWNER_EMAIL must be a real contact (a@b.tld, no placeholders)', file=sys.stderr)
    sys.exit(1)
except httpx.HTTPError as e:
    print(f'[bootstrap] could not reach the arena at $ARENA: {e}', file=sys.stderr)
    sys.exit(1)
print('[bootstrap] enrollment requested; check $OWNER_EMAIL for confirmation code', file=sys.stderr)
"
# The confirm command is emitted from bash (NOT the python -c block above) so the
# quoting survives copy-paste: the outer `-c "..."` is double-quoted and the inner
# python args are SINGLE-quoted, so there is no nested-double-quote collision. The
# earlier in-python print produced bare inner double-quotes (the escaping was
# consumed by bash + python before it reached the user), breaking the pasted command.
echo "[bootstrap] enrollment requested. Get the confirmation code from your owner channel"
echo "  (local dev: tail the file inbox; prod: your webhook), then run:"
echo "  uv run python -c \"from arena_client import ArenaClient; print(ArenaClient('$ARENA').enroll_confirm('<CODE>'))\" > $TOKENFILE"
echo
echo "[bootstrap] once the token is saved to $TOKENFILE:"
echo "  export ARENA_TOKEN=\$(cat $TOKENFILE)"
echo "  uv run python agents/max_damage_agent.py --token \"\$ARENA_TOKEN\" \\"
echo "    --keyfile $KEYFILE --agent-name $AGENT_NAME --team-file team.txt --lane sandbox"
