#!/usr/bin/env bash
# Agent sense — peek perf / coverage / size deltas (G2 ep4 read-back loop).
#
# Prints a single screen of "is the system shape moving in the right direction":
#   - test count + pass/skip/fail tally (collect-only is cheap)
#   - SLOC by top-level package
#   - latest 5 commits on main with size delta
#   - latest Expedition pareto verdict
#   - line count of doctrine anchors (IDEAL_EXPERIENCE.md / EVAL.md / AGENTS.md)
#
# No args. Fast (<3s).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

_section() { printf '\n=== %s ===\n' "$1"; }

_section "tests (collect-only)"
if uv run --no-sync pytest packages/ --collect-only -q 2>/dev/null | tail -3; then :; fi

_section "SLOC by package"
for d in packages/*/src; do
  pkg="$(basename "$(dirname "$d")")"
  loc=$(find "$d" -name '*.py' -type f -exec wc -l {} + 2>/dev/null | tail -1 | awk '{print $1}')
  printf '%-24s %s\n' "$pkg" "${loc:-0}"
done

_section "recent commits (latest 5 w/ size delta)"
git log -5 --pretty=format:'%h %ad %s' --date=short --shortstat | head -20

_section "latest expedition verdict"
latest="$(find expeditions -maxdepth 1 -mindepth 1 -type d -printf '%T@ %p\n' 2>/dev/null \
  | sort -nr | head -1 | cut -d' ' -f2-)" || true
if [[ -n "${latest:-}" && -f "$latest/pareto_verdict.yaml" ]]; then
  echo "expedition: $(basename "$latest")"
  head -10 "$latest/pareto_verdict.yaml"
else
  echo "(no pareto_verdict.yaml in latest expedition)"
fi

_section "doctrine anchor line counts (G14/G13/G2 health)"
for f in IDEAL_EXPERIENCE.md EVAL.md AUTONOMY_THRESHOLD.md AGENTS.md; do
  if [[ -f "$f" ]]; then
    printf '%-26s %s lines\n' "$f" "$(wc -l < "$f")"
  fi
done
