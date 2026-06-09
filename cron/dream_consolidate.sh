#!/usr/bin/env bash
# cron/dream_consolidate.sh — nightly KAOS dream consolidation + Expedition
# lineage surface. Ported from ~/gh/eddie-agi-kb/scripts/dream_nightly.sh
# (autonomous-pipeline mirror, 2026-06-09). Designed for 03:00 PDT trigger,
# 30 min after the daily expedition_smoke at 02:30 PDT.
#
# What it writes (per the upstream "ONE proposal file per run" invariant):
#   sweeps/<YYYY-MM-DD>-dream-consolidate.md
# Allowed writes outside that path:
#   - ~/.cursor/projects/home-admin/heartbeat/monitor-gaps.md (one line per error)
#   - /tmp/adx_dream_sandbox.db* (KAOS sandbox so host KAOS DB stays untouched)
#   - sweeps/_kaos-digests/ (kaos dream digests live here per AC8 write-tree rule)
#
# Doctrine anchor: G14 ep29 [29-0535] "Cursor weekly automated repair task" +
# G9 ablation evidence — the consolidation surfaces the last N Expeditions'
# mutation seeds so a human (or the weekly_harness_audit) can spot
# seed_provenance drift (M5 = all structural; M7 raises bar to ≥1 learned).
#
# Exit 0 always (cron must not email/disable on transient failures).

set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 0

TODAY="$(date -u +%Y-%m-%d)"
NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SWEEPS_DIR="$REPO/sweeps"
OUT="$SWEEPS_DIR/${TODAY}-dream-consolidate.md"
GAP="${GAP:-$HOME/.cursor/projects/home-admin/heartbeat/monitor-gaps.md}"
KAOS_SANDBOX_DB="/tmp/adx_dream_sandbox.db"
KAOS_DIGEST_DIR="$SWEEPS_DIR/_kaos-digests"
LOG="${LOG:-/tmp/adx_dream_consolidate.$TODAY.log}"

exec 9>/tmp/adx_dream_consolidate.lock
if ! flock -n 9; then
  echo "[$NOW_ISO] prior dream consolidate still active, skipping" >> "$LOG"
  exit 0
fi

mkdir -p "$SWEEPS_DIR" "$KAOS_DIGEST_DIR"

log_gap() {
  local msg="$1"
  mkdir -p "$(dirname "$GAP")"
  printf '[%s] adx-cli dream_consolidate %s\n' "$NOW_ISO" "$msg" >> "$GAP"
}

# Idempotent: skip if today's consolidation exists.
if [[ -f "$OUT" ]]; then
  echo "[$NOW_ISO] $OUT exists, idempotent skip" >> "$LOG"
  exit 0
fi

{
  cat <<EOF
# Dream consolidation — $TODAY

_Generated $NOW_ISO by cron/dream_consolidate.sh_

This file is auto-generated. Sections below are PROPOSALS / SURFACES only —
no primary artifact is modified by the dream loop. Review + act manually as
tiny PRs per feedback_tiny_pr_discipline memory.

## §1 KAOS dream consolidation (sandboxed)

\`\`\`
EOF

  if command -v kaos >/dev/null 2>&1; then
    [ -f "$KAOS_SANDBOX_DB" ] || kaos init --db "$KAOS_SANDBOX_DB" >/dev/null 2>&1 || true
    if ! timeout 60 kaos dream consolidate --dry-run --db "$KAOS_SANDBOX_DB" 2>&1 | head -200; then
      echo "(kaos dream consolidate --dry-run failed or timed out; see gap log)"
      log_gap "kaos dream consolidate --dry-run failed"
    fi
    echo ""
    echo "--- kaos dream run --dry-run ---"
    if ! timeout 60 kaos dream run --dry-run --db "$KAOS_SANDBOX_DB" \
                              --digest-dir "$KAOS_DIGEST_DIR" --no-print-digest 2>&1 | head -200; then
      echo "(kaos dream run --dry-run failed or timed out; see gap log)"
      log_gap "kaos dream run --dry-run failed"
    fi
  else
    echo "kaos CLI not on PATH — skipping dream consolidation."
    log_gap "kaos CLI not on PATH"
  fi

  cat <<EOF
\`\`\`

## §2 Expedition lineage surface (last 5 expeditions)

| Expedition | Verdict | Seed categories | Provenance |
|---|---|---|---|
EOF

  # Walk the 5 most-recently-modified expedition dirs, summarise verdict +
  # mutation-seed counts per category + flag any seed with seed_provenance="learned".
  # Per python -c so YAML parsing is sane.
  python3 - "$REPO" <<'PY' 2>&1 || log_gap "expedition surface walk crashed"
import sys, pathlib, yaml, os
repo = pathlib.Path(sys.argv[1])
exp_dirs = sorted(
    (d for d in (repo / "expeditions").iterdir() if d.is_dir()),
    key=lambda d: d.stat().st_mtime, reverse=True,
)
for d in exp_dirs[:5]:
    pv = d / "pareto_verdict.yaml"
    ev = d / "evolution_card.yaml"
    if not (pv.is_file() and ev.is_file()):
        print(f"| `{d.name}` | (incomplete) | — | — |")
        continue
    try:
        pareto = yaml.safe_load(pv.read_text())
        evo = yaml.safe_load(ev.read_text())
    except Exception as e:
        print(f"| `{d.name}` | parse error: {e} | — | — |")
        continue
    verdict = pareto.get("verdict_kind", "?")
    winner = pareto.get("winner") or "—"
    seeds = evo.get("mutation_seeds") or {}
    cats = ",".join(f"{k}({len(v)})" for k, v in sorted(seeds.items()))
    provs = sorted({s.get("seed_provenance", "?") for v in seeds.values() for s in v})
    flag = " 🌱 LEARNED" if "learned" in provs else ""
    prov_s = ",".join(provs) + flag
    print(f"| `{d.name}` | {verdict}/{winner} | {cats or '—'} | {prov_s or '—'} |")
PY

  cat <<EOF

## §3 Mutation-seed kind frequency (across §2 expeditions)

Surfaces recurring seed.kind strings — repeated seeds across expeditions
indicate a stable doctrine gap worth a phase 8 polish PR.

\`\`\`
EOF
  python3 - "$REPO" <<'PY' 2>&1 || log_gap "seed frequency walk crashed"
import sys, pathlib, yaml, collections
repo = pathlib.Path(sys.argv[1])
exp_dirs = sorted(
    (d for d in (repo / "expeditions").iterdir() if d.is_dir()),
    key=lambda d: d.stat().st_mtime, reverse=True,
)
freq = collections.Counter()
for d in exp_dirs[:5]:
    ev = d / "evolution_card.yaml"
    if not ev.is_file():
        continue
    try:
        evo = yaml.safe_load(ev.read_text())
    except Exception:
        continue
    seeds = evo.get("mutation_seeds") or {}
    for cat, items in seeds.items():
        for s in items:
            freq[(cat, s.get("kind", "?"))] += 1
for (cat, kind), n in freq.most_common(15):
    print(f"  {n}×  {cat:10s}  {kind}")
PY

  cat <<EOF
\`\`\`

---
DONE_JSON {"out": "$OUT", "ts": "$NOW_ISO"}
EOF
} >> "$OUT" 2>>"$LOG"

echo "[$NOW_ISO] dream_consolidate wrote $OUT" >> "$LOG"
exit 0
