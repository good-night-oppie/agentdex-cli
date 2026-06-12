#!/usr/bin/env bash
# arena_selftest.sh — nightly instrument self-test (ADR-0010 phase 5).
#
# Runs the 200-battle anchor calibration; exits NON-ZERO when ordering or
# 2·RD separation fails. Publication gates on this exit code (EVAL §Arena:
# "publication halts automatically if self-test fails") — the deploy phase
# wires the gateway to refuse rated publishing while the last self-test is
# red. Report JSON lands beside the events log for the audit trail.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT_DIR="${ARENA_SELFTEST_DIR:-/tmp/agentdex/arena-selftest}"
mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
uv run python - "$OUT_DIR/$STAMP" <<'PY'
import asyncio, json, pathlib, sys
from adx_showdown.calibration import run_calibration

base = pathlib.Path(sys.argv[1])
report = asyncio.run(run_calibration(base.with_suffix(".events.jsonl")))
base.with_suffix(".report.json").write_text(json.dumps(report, indent=1) + "\n")
print(json.dumps(report["ratings"], indent=1))
if not report["publication_allowed"]:
    print("SELFTEST FAILED — publication halted", file=sys.stderr)
    sys.exit(1)
print("SELFTEST OK — publication allowed")
PY
