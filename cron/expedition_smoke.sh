#!/usr/bin/env bash
# cron/expedition_smoke.sh — daily Expedition smoke test wrapper.
#
# Ported from ~/gh/eddie-agi-kb/cron/daily_ingest.sh shape (autonomous-pipeline
# mirror, 2026-06-09). Runs the agentdex-cli M5 acceptance gate in mocked mode
# so the cron job is deterministic + cheap + free of subscription charges.
#
# What it asserts (the "smoke" surface, per EVAL.md gate):
#   1. The Three Cards schema validates round-trip
#   2. The Pareto judge produces winner | no_clear_winner
#   3. The EvolutionCard ships ≥2 mutation seed categories
#   4. Every seed carries seed_provenance ∈ {structural, learned}
#   5. KAOS lineage entry spawns + checkpoints
#
# Errors funnel into monitor-gaps.md (~/.cursor/projects/home-admin/heartbeat/)
# per the gap-log-review memory. Exit 0 always — the gap log + non-zero rc
# captured in the per-day log file is the audit trail; cron must not
# email/disable on transient failures.
#
# Optional env:
#   ADX_SMOKE_TARGET    pytest path filter (default test_expedition_smoke.py)
#   QUOTA               unused at MVP — reserved for live-mode quota later
#   DRY_RUN=1           print the command instead of running it
#
# Designed for daily 03:30 PDT trigger (avoid the :00/:30 cluster).

set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${LOG_DIR:-/tmp}"
TODAY="$(date -u +%Y-%m-%d)"
LOG="$LOG_DIR/adx_expedition_smoke.$TODAY.log"
GAP="${GAP:-$HOME/.cursor/projects/home-admin/heartbeat/monitor-gaps.md}"
TARGET="${ADX_SMOKE_TARGET:-packages/agentdex_cli/tests/test_expedition_smoke.py}"
DRY_RUN="${DRY_RUN:-}"

# Single-instance lock — silent skip if a prior run is still active.
exec 9>/tmp/adx_expedition_smoke.lock
if ! flock -n 9; then
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] prior smoke still active, skipping" >> "$LOG"
  exit 0
fi

cd "$REPO" || {
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] FATAL: cannot cd $REPO" >> "$LOG"
  exit 0
}

CMD=(uv run --no-sync pytest "$TARGET" -q --tb=short)

{
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] expedition_smoke start cmd=${CMD[*]}"
  if [[ -n "$DRY_RUN" ]]; then
    echo "[DRY_RUN] would run: ${CMD[*]}"
    RC=0
  else
    "${CMD[@]}"
    RC=$?
  fi
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] expedition_smoke exit rc=$RC"
  if [[ "$RC" -ne 0 ]]; then
    mkdir -p "$(dirname "$GAP")"
    {
      echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] adx-cli expedition_smoke cron-wrapper FAILED rc=$RC log=$LOG"
    } >> "$GAP"
  fi
} >> "$LOG" 2>&1

exit 0
