#!/usr/bin/env bash
# cron/weekly_harness_audit.sh — weekly harness-praxis doctrine fire-vs-friction
# audit. Mirrors ~/gh/eddie-agi-kb/scripts/weekly_meta_audit.sh in shape but
# scoped to agentdex-cli's much smaller surface (no per-rule fire counters yet).
#
# Citations (harness-praxis discipline — every behavior anchored to a source):
#   - G14 ep29 [29-0535] "Cursor weekly automated repair task" — weekly cron
#     is THE mechanism by which Ideal Moments 1-6 of IDEAL_EXPERIENCE.md v2
#     stay live. Without the periodic check, doctrine drift accumulates.
#   - G2 ep6 [06-0028] "文档是建议 / 而agent需要的是法律" — the audit checks
#     that prose claims have code-level enforcement (the MF2/MF3/MF4 gaps the
#     harness-praxis tracer found on 2026-06-09 were exactly this drift).
# TODO (PR-I, workflow w0z1i9vcs P4): sunset tracking — DEAD-week bucket
# per G13 ep28 [28-0830] "eval集不能只增不删" — DEFERRED to M6 audit v2
# (see future ADR). The current scaled-down §2 only detects MISSING
# anchors, not DEAD ones (file exists but unreferenced from any senses /
# EVAL / CLAUDE.md / IDEAL_EXPERIENCE.md). Citation was earlier in this
# header but pruned because cite-without-impl is the exact drift the
# script exists to catch (self-fulfilling MF-class gap).
#
# Behavior contract:
#   1. Read 7-day window of commits, count files-per-commit (tiny-PR violation
#      detection per feedback_tiny_pr_discipline memory)
#   2. Re-grep doctrine anchors (AGENTS.md scripts, EVAL.md fixture dirs,
#      IDEAL_EXPERIENCE.md async primitives, CLAUDE.md sync_toc reference)
#      against current filesystem
#   3. Run agent_senses peek_metrics + run_tests for system-shape baseline
#   4. Write proposal markdown under sweeps/<date>-weekly-harness-audit.md
#   5. Idempotent — skip if today's audit exists
#   6. Exit 0 always
#
# Designed for Sunday 04:00 PDT trigger (mirror eddie-agi-kb dream-1h-after
# pattern — dream_consolidate runs at 03:00, audit at 04:00).

set -u
# PR-D (workflow w0z1i9vcs P9): match the ancestor weekly_meta_audit.sh
# discipline. pipefail catches §1's `git log ... | awk` mid-pipeline
# failures that today vanish silently because the outer braces redirect
# into $LOG. `|| true` keeps the exit-0 contract on shells without
# pipefail support.
set -o pipefail 2>/dev/null || true
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SWEEPS_DIR="$REPO/sweeps"
TODAY="$(date -u +%Y-%m-%d)"
OUT="$SWEEPS_DIR/${TODAY}-weekly-harness-audit.md"
GAP="${GAP:-$HOME/.cursor/projects/home-admin/heartbeat/monitor-gaps.md}"
WINDOW_DAYS="${WINDOW_DAYS:-7}"
TINY_PR_FILE_CAP="${TINY_PR_FILE_CAP:-10}"  # >10 files in one commit = violation
LOG="${LOG:-/tmp/adx_weekly_harness_audit.$TODAY.log}"

exec 9>/tmp/adx_weekly_harness_audit.lock
if ! flock -n 9; then
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] prior audit still active, skipping" >> "$LOG"
  exit 0
fi

cd "$REPO" || {
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] FATAL: cannot cd $REPO" >> "$LOG"
  exit 0
}

log_gap() {
  mkdir -p "$(dirname "$GAP")"
  printf '[%s] adx-cli weekly_harness_audit %s\n' \
    "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$1" >> "$GAP"
}

mkdir -p "$SWEEPS_DIR"

if [[ -f "$OUT" ]]; then
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $OUT exists, idempotent skip" >> "$LOG"
  exit 0
fi

{
  cat <<EOF
# Weekly harness audit — $TODAY

_Generated $(date -u +'%Y-%m-%dT%H:%M:%SZ') by cron/weekly_harness_audit.sh._

This file is auto-generated. Sections below are READ-ONLY signals — no
primary artifact is modified by the audit. Review + act manually as
[tiny PRs](~/.claude/projects/-home-admin-gh-agentdex-cli/memory/feedback_tiny_pr_discipline.md).

## 1. Commit shape (Ideal moment 1)

\`\`\`
EOF

  # Last 7-day commits with files-changed count.
  # PR-D (workflow w0z1i9vcs P10): --no-merges drops merge commits whose
  # shortstat block is empty, which would otherwise cause the awk to
  # mis-label the previous commit's files=count against the next sha.
  git log --since="$WINDOW_DAYS days ago" --no-merges \
    --pretty=format:'%h %s' --shortstat | awk '
      /^[0-9a-f]+ / { sha=$1; sub(/^[0-9a-f]+ /, ""); subj=$0; next }
      /file.* changed/ {
        n=$1+0
        flag=""
        if (n > '"$TINY_PR_FILE_CAP"') flag=" ⚠ TINY_PR_VIOLATION"
        printf "%s  files=%d%s  %s\n", sha, n, flag, subj
      }
    '

  cat <<EOF
\`\`\`

## 2. Doctrine-vs-filesystem cross-check (Ideal moment 6)

| Doctrine claim | File path | Exists? |
|---|---|---|
EOF

  check_exists() {
    # PR-D (workflow w0z1i9vcs C2/P6): the surrounding `cat <<EOF` heredoc
    # is unquoted so backslash-backtick survives as literal `\` + `` ` ``
    # in the rendered markdown table cells. Use bare backticks here; the
    # outer heredoc still expands $REPO + the printf vars correctly.
    local label="$1" path="$2"
    if [[ -e "$REPO/$path" ]]; then
      printf '| %s | `%s` | ✅ |\n' "$label" "$path"
    else
      printf '| %s | `%s` | ❌ MISSING |\n' "$label" "$path"
      log_gap "doctrine drift: $label expected $path missing"
    fi
  }

  check_exists "AGENTS.md senses: run_tests"  "tools/agent_senses/run_tests.sh"
  check_exists "AGENTS.md senses: tail_logs"  "tools/agent_senses/tail_logs.sh"
  check_exists "AGENTS.md senses: peek_metrics" "tools/agent_senses/peek_metrics.sh"
  check_exists "AGENTS.md hard rails: pre-commit" ".pre-commit-config.yaml"
  check_exists "AGENTS.md hard rails: secrets baseline" ".secrets.baseline"
  check_exists "EVAL.md GT: golden pareto"    "tests/golden/nvidia_pareto_expected.yaml"
  check_exists "EVAL.md GT: bridge smoke fixtures dir" "tests/fixtures/bridges"
  check_exists "EVAL.md GT: oracle calibration dir"   "packages/agentdex_engine/tests/oracle_calibration_fixtures"
  check_exists "CLAUDE.md TOC generator"      "scripts/sync_toc.sh"
  check_exists "Daily smoke cron"             "cron/expedition_smoke.sh"

  cat <<EOF

## 3. System shape (agent_senses peek_metrics)

\`\`\`
EOF
  if [[ -x "$REPO/tools/agent_senses/peek_metrics.sh" ]]; then
    "$REPO/tools/agent_senses/peek_metrics.sh" 2>&1 | head -60
  else
    echo "(peek_metrics.sh not executable — gap)"
    log_gap "tools/agent_senses/peek_metrics.sh not executable"
  fi
  echo '```'

  cat <<EOF

## 4. Test signal (run_tests)

\`\`\`
EOF
  if [[ -x "$REPO/tools/agent_senses/run_tests.sh" ]]; then
    "$REPO/tools/agent_senses/run_tests.sh" packages/ --slow 2>&1 | tail -6
  else
    echo "(run_tests.sh not executable — gap)"
    log_gap "tools/agent_senses/run_tests.sh not executable"
  fi
  echo '```'

  cat <<EOF

## 5. Action queue

The audit is a read-only signal. To act on a finding above:

1. **MISSING entries in §2** → ship a tiny PR per file (max 1 LOC concern
   per commit, per [tiny-PR-discipline](~/.claude/projects/-home-admin-gh-agentdex-cli/memory/feedback_tiny_pr_discipline.md)).
2. **TINY_PR_VIOLATION flags in §1** → already shipped; not actionable
   retroactively, but next sweep should show 0 violations.
3. **System-shape regressions in §3-4** → cross-check against
   \`tests/golden/nvidia_pareto_expected.yaml\` before reverting.

Per IDEAL_EXPERIENCE.md v2 Ideal moment 2: this audit IS the mechanism
that keeps Ideal moments 1, 3, 4 live. Skipping a week means doctrine
drift accumulates undetected.
EOF
} > "$OUT" 2> >(tee -a "$LOG" >&2)

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] weekly_harness_audit wrote $OUT" >> "$LOG"
exit 0
