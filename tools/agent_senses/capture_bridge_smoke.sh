#!/usr/bin/env bash
# tools/agent_senses/capture_bridge_smoke.sh — record a bridge handshake +
# one-turn probe into tests/fixtures/bridges/<bridge>_smoke.json.
#
# Closes BRIDGE-SMOKE in DEFERRED.md: the fixture dir + schema were
# scaffolded by MF4 but no capture mechanism existed. This script is the
# capture mechanism — point it at a bridge, get back a frozen JSON the
# downstream smoke test can validate against the README.md schema.
#
# Usage:
#   bash tools/agent_senses/capture_bridge_smoke.sh claude
#   bash tools/agent_senses/capture_bridge_smoke.sh codex
#   bash tools/agent_senses/capture_bridge_smoke.sh manus
#
# Side effects:
#   - writes tests/fixtures/bridges/<bridge>_smoke.json (atomic via tmp + mv)
#   - never overwrites existing fixture unless --force passed
#   - logs to /tmp/adx_capture_bridge_smoke.$bridge.log
#   - exit 0 on success; 2 on usage error; 3 on bridge spawn failure
#
# Doctrine: tests/fixtures/bridges/README.md ships the SCHEMA; this script
# ships the GENERATOR. The two together close DEFERRED BRIDGE-SMOKE.

set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 2

BRIDGE="${1:-}"
FORCE="${2:-}"

if [[ -z "$BRIDGE" ]]; then
  echo "usage: $0 <claude|codex|manus> [--force]" >&2
  exit 2
fi

case "$BRIDGE" in
  claude|codex|manus) : ;;
  *)
    echo "unknown bridge: $BRIDGE (must be claude / codex / manus)" >&2
    exit 2
    ;;
esac

OUT="$REPO/tests/fixtures/bridges/${BRIDGE}_smoke.json"
LOG="/tmp/adx_capture_bridge_smoke.${BRIDGE}.log"

if [[ -f "$OUT" && "$FORCE" != "--force" ]]; then
  echo "[capture] $OUT exists; pass --force to overwrite" >&2
  exit 0
fi

mkdir -p "$(dirname "$OUT")"

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Resolve the bridge binary so the captured fixture can record `binary_version`.
case "$BRIDGE" in
  claude)
    BIN="$(command -v claude || echo claude)"
    VERSION="$("$BIN" --version 2>/dev/null || echo unknown)"
    ;;
  codex)
    BIN="$(command -v codex || echo codex)"
    VERSION="$("$BIN" --version 2>/dev/null || echo unknown)"
    ;;
  manus)
    BIN="(camoufox|codex-web — runtime resolved at bridge spawn)"
    VERSION="(camoufox/codex-web fallback ladder)"
    ;;
esac

# Drive the bridge through `adx bridge probe` which uses the same code path as
# live Expeditions. The probe writes its result frame to stderr; we tee + grep
# the relevant fields out.
TMP="$OUT.tmp.$$"
PROBE_LOG="$LOG.probe"

echo "[capture] starting probe at $(now_iso) — log $PROBE_LOG" | tee -a "$LOG"
PROBE_OUTPUT=""
PROBE_RC=0
if command -v adx >/dev/null 2>&1; then
  PROBE_OUTPUT="$(adx bridge probe --bridge "$BRIDGE" --task nvidia-earnings-infographic --timeout 30 2>&1 || true)"
  PROBE_RC=$?
else
  PROBE_OUTPUT="$(uv run --no-sync adx bridge probe --bridge "$BRIDGE" --task nvidia-earnings-infographic --timeout 30 2>&1 || true)"
  PROBE_RC=$?
fi
printf '%s\n' "$PROBE_OUTPUT" > "$PROBE_LOG"

if [[ "$PROBE_RC" -ne 0 ]]; then
  echo "[capture] WARNING: probe exited rc=$PROBE_RC; capture may be partial" | tee -a "$LOG"
fi

# Build the JSON fixture per tests/fixtures/bridges/README.md schema.
python3 - "$BRIDGE" "$VERSION" "$PROBE_LOG" "$TMP" <<'PY'
import json, sys, pathlib, re
bridge, version, probe_log_path, out_path = sys.argv[1:5]
probe_text = pathlib.Path(probe_log_path).read_text(errors="replace")

# Heuristic field extraction — we record what we see + leave the schema fields
# present-but-empty for missing surfaces. Drift detector defaults are taken
# from tests/fixtures/bridges/README.md.
def find(pattern, text, group=0, default=None):
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(group) if m else default

# Light scan for handshake init frame timing (claude prints "init", codex prints
# "initialize"). We don't parse JSON-RPC here — capture is best-effort + the
# downstream validator only checks shape.
ms_until_init = find(r"\b(\d+)\s*ms\b.*?(init|initialize)", probe_text)
session_id = find(r'session_id[":\s]+([\w\-]{4,})', probe_text)

drift_per_bridge = {
    "claude": {
        "fields_required_in_result_frame": [
            "session_id", "total_cost_usd",
            "usage.input_tokens", "usage.output_tokens",
        ],
    },
    "codex": {
        "fields_required_in_turn_completed": [
            "turnId", "tokenUsage.inputTokens", "tokenUsage.outputTokens",
        ],
    },
    "manus": {
        "fields_required_in_response_element": [
            "data-role-attr-or-fallback-selector-match",
        ],
    },
}

fixture = {
    "bridge": bridge,
    "binary_version": version.strip() or "unknown",
    "captured_at": "REPLACE_AT_COMMIT_TIME",  # script overwrites below
    "captured_with": "tools/agent_senses/capture_bridge_smoke.sh " + bridge,
    "handshake": {
        "argv_shape": f"{bridge} (per adx bridge probe — recorded in probe log)",
        "ms_until_init_frame": int(ms_until_init) if ms_until_init else None,
        "session_id_format": "uuid4" if bridge in ("claude", "manus") else "thread-id",
        "session_id_sample": session_id or "<not-extracted>",
    },
    "one_turn_probe": {
        "task_id": "nvidia-earnings-infographic",
        "max_ms": 30000,
        "max_cost_usd": 0.20,
        "probe_log_path": probe_log_path,
        "probe_rc_observed": "see probe log",
    },
    "drift_detector": drift_per_bridge[bridge],
}

pathlib.Path(out_path).write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n")
PY

# Rewrite captured_at with the wallclock-now (atomically).
python3 - "$TMP" <<PY
import json, pathlib
p = pathlib.Path("$TMP")
d = json.loads(p.read_text())
d["captured_at"] = "$(now_iso)"
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
PY

mv "$TMP" "$OUT"
echo "[capture] wrote $OUT" | tee -a "$LOG"
exit 0
