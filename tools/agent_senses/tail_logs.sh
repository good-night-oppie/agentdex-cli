#!/usr/bin/env bash
# Agent sense — peek recent logs without flooding context (G2 ep4 read-back loop).
#
# Args:
#   $1  area: expedition | langfuse | bridge | gateway | all  (default: all)
#   $2  lines (default: 40)
#
# Looks under (in order):
#   - latest expeditions/<id>/trace/*.jsonl              (per-baseline trace tail)
#   - .langfuse/*.log                                    (self-hosted Langfuse if running)
#   - /tmp/adx_bridges_*.log                             (bridge process stderr drain)
#   - /tmp/hermes_gateway_*.log                          (Hermes gateway stderr drain)
#
# Prints area headers around each tail so the agent knows what it is reading.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

AREA="${1:-all}"
LINES="${2:-40}"

_section() {
  printf '\n=== %s ===\n' "$1"
}

_tail_expedition() {
  _section "expedition (latest trace tails)"
  local latest
  latest="$(find expeditions -maxdepth 1 -mindepth 1 -type d -printf '%T@ %p\n' 2>/dev/null \
    | sort -nr | head -1 | cut -d' ' -f2-)" || true
  if [[ -z "${latest:-}" ]]; then
    echo "(no expeditions/ dir yet)"; return
  fi
  echo "latest: $latest"
  if compgen -G "$latest/trace/*.jsonl" > /dev/null; then
    for f in "$latest"/trace/*.jsonl; do
      printf '\n--- %s ---\n' "$(basename "$f")"
      tail -n "$LINES" "$f"
    done
  else
    echo "(no trace/*.jsonl in $latest)"
  fi
}

_tail_glob() {
  local label="$1" pattern="$2"
  _section "$label"
  if compgen -G "$pattern" > /dev/null; then
    for f in $pattern; do
      printf '\n--- %s ---\n' "$f"
      tail -n "$LINES" "$f"
    done
  else
    echo "(no $pattern)"
  fi
}

case "$AREA" in
  expedition) _tail_expedition ;;
  langfuse)   _tail_glob "langfuse"  ".langfuse/*.log" ;;
  bridge)     _tail_glob "bridge"    "/tmp/adx_bridges_*.log" ;;
  gateway)    _tail_glob "gateway"   "/tmp/hermes_gateway_*.log" ;;
  all)
    _tail_expedition
    _tail_glob "langfuse"  ".langfuse/*.log"
    _tail_glob "bridge"    "/tmp/adx_bridges_*.log"
    _tail_glob "gateway"   "/tmp/hermes_gateway_*.log"
    ;;
  *)
    echo "usage: $0 [expedition|langfuse|bridge|gateway|all] [lines]" >&2
    exit 2
    ;;
esac
