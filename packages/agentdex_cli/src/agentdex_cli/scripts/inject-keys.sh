#!/usr/bin/env bash
# Inject MySearch + bridge keys into the current shell via 1Password.
#
# Usage:
#   1. Edit the OP_REFS map below to match your 1Password vault/item layout.
#   2. Source (not exec) this script before launching Claude Code / Hermes:
#        source ~/gh/agentdex-cli/scripts/inject-keys.sh
#
# Dependencies: 1Password CLI (`op`) authenticated. Either an
# OP_SERVICE_ACCOUNT_TOKEN is exported, or `op signin` succeeded.
#
# Safety: never echos secret values. On failure, prints which ref failed
# and exits non-zero (still returns to the parent shell when sourced).

set -uo pipefail

if ! command -v op >/dev/null 2>&1; then
    echo "[inject-keys] 1Password CLI 'op' not found in PATH" >&2
    return 1 2>/dev/null || exit 1
fi

# ────────────────────────────────────────────────────────────────────────
# Edit these refs to match your vault. Format: op://<vault>/<item>/<field>
# Run `op item list` to discover items, `op item get <id>` for field names.
# ────────────────────────────────────────────────────────────────────────
declare -A OP_REFS=(
  [MYSEARCH_TAVILY_API_KEY]="op://Personal/tavily/credential"
  [MYSEARCH_FIRECRAWL_API_KEY]="op://Personal/firecrawl/credential"
  [MYSEARCH_EXA_API_KEY]="op://Personal/exa/credential"
  [MYSEARCH_XAI_API_KEY]="op://Personal/xai/credential"
)

errs=0
for var in "${!OP_REFS[@]}"; do
    ref="${OP_REFS[$var]}"
    if value="$(op read "$ref" 2>/dev/null)" && [ -n "$value" ]; then
        export "$var=$value"
        echo "[inject-keys] $var ← $ref ✓"
    else
        echo "[inject-keys] $var ← $ref ✗" >&2
        errs=$((errs + 1))
    fi
done

unset value ref var
if [ "$errs" -gt 0 ]; then
    echo "[inject-keys] $errs ref(s) failed. Run 'op item list' to fix paths." >&2
    return 1 2>/dev/null || exit 1
fi
echo "[inject-keys] all keys exported."
