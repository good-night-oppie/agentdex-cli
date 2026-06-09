#!/usr/bin/env bash
# Agent sense — canonical test command (G2 ep4 read-back loop).
#
# Per AGENTS.md "agents that only write are blind; senses are the read-back loop."
# This script is the SINGLE source of truth for "is the codebase green?". Anything
# else that asserts test health is doctrine drift.
#
# Args (all optional):
#   $1  path filter (default: packages/)
#   -v  pass-through verbose
#   --slow  drop -x so a single fail does not short-circuit the loop
#
# Exit code: pytest's exit code (0 = green; non-zero = the agent must read the
# tail and reason about the failure before another write).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PATH_FILTER="${1:-packages/}"
shift || true

EXTRA=( "-x" "-q" )
for arg in "$@"; do
  case "$arg" in
    --slow) EXTRA=( "-q" ) ;;
    -v)     EXTRA+=( "-v" ) ;;
    *)      EXTRA+=( "$arg" ) ;;
  esac
done

exec uv run --no-sync pytest "$PATH_FILTER" "${EXTRA[@]}"
