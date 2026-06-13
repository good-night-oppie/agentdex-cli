#!/usr/bin/env bash
# resim_audit.sh — Re-simulation audit job (Phase 10).
#
# Sweeps the event log, audits 100% of disputed battles and 10% random sample
# of completed battles by re-simulating them, quarantining any mismatches.
set -euo pipefail
cd "$(dirname "$0")/.."
EVENTS_PATH="${ARENA_EVENTS_PATH:-/tmp/arena-runtime/events.jsonl}"
ARTIFACTS_DIR="${ARENA_ARTIFACTS_DIR:-/tmp/arena-runtime/artifacts}"
AUDIT_RATE="${ARENA_AUDIT_RATE:-0.10}"

echo "Running re-simulation audit job..."
uv run python scripts/resim_audit.py \
  --events-path "$EVENTS_PATH" \
  --artifacts-dir "$ARTIFACTS_DIR" \
  --rate "$AUDIT_RATE"
