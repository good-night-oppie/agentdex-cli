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
# Content-scan coverage (H7 + AUDIT-OWNER-SCAN closure, PR-Z2):
#   - §2b past-due `Until:` rows in DEFERRED.md (PR-Q, earlier)
#   - §2c Owner=TODO drift across doctrine + DEFERRED rows (H7)
#   - §2d orphan doctrine anchors — files listed in §2 that exist but
#     are referenced nowhere else in the repo (H7) per G13 ep28
#     [28-0830] "eval集不能只增不删" — the DEAD-week bucket the earlier
#     TODO promised. M6 audit v2 will graduate this to per-rule fire
#     counters; the basename-grep heuristic is the MVP shape.
#
# Behavior contract:
#   1. Read 7-day window of commits, count files-per-commit (tiny-PR violation
#      detection per feedback_tiny_pr_discipline memory)
#   2. Re-grep doctrine anchors (AGENTS.md scripts, EVAL.md fixture dirs,
#      IDEAL_EXPERIENCE.md async primitives, CLAUDE.md sync_toc reference)
#      against current filesystem, plus 2b past-due Until: rows + 2c
#      Owner=TODO drift + 2d orphan-anchor scan
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

  # H7: collect the §2 path list so §2d can scan it for orphans.
  AUDIT_PATHS=()

  check_exists() {
    # PR-D (workflow w0z1i9vcs C2/P6): the surrounding `cat <<EOF` heredoc
    # is unquoted so backslash-backtick survives as literal `\` + `` ` ``
    # in the rendered markdown table cells. Use bare backticks here; the
    # outer heredoc still expands $REPO + the printf vars correctly.
    local label="$1" path="$2"
    AUDIT_PATHS+=("$path")
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
  check_exists "Phase-8 polish queue"         "DEFERRED.md"
  check_exists "Pre-commit installer"         "scripts/install_hooks.sh"
  check_exists "Lint CI gate"                 ".github/workflows/lint.yml"
  check_exists "Doc-lint upstream shim"       "scripts/doc_lint.py"
  check_exists "Doc-lint installer"           "scripts/install_doc_lint_precommit.sh"
  check_exists "Doc-template: architecture"   ".harness/doc-templates/architecture.md"
  check_exists "Doc-template: bugfix"         ".harness/doc-templates/bugfix.md"
  check_exists "Doc-template: feature"        ".harness/doc-templates/feature.md"

  cat <<EOF

## 2b. Past-due deferred items (PR-Q + H7 partial)

DEFERRED.md \`Until:\` rows where the date has passed. Empty = clean.

EOF

  # PR-Q (workflow w0z1i9vcs H7 partial closure): content-scan
  # DEFERRED.md for past-due rows. The audit converts from pure
  # file-presence to lightweight content-check on doctrine artifacts
  # the harness commits to keep current.
  if [[ -f "$REPO/DEFERRED.md" ]]; then
    today_epoch="$(date -u +%s)"
    overdue=0
    # Match `Until: YYYY-MM-DD` inside table rows.
    while IFS= read -r line; do
      iso="$(printf '%s' "$line" | grep -oE 'Until: 20[0-9]{2}-[0-9]{2}-[0-9]{2}' | head -1 | cut -d' ' -f2)"
      [ -z "$iso" ] && continue
      row_epoch="$(date -u -d "$iso" +%s 2>/dev/null || echo 0)"
      if [[ "$row_epoch" != "0" && "$row_epoch" -lt "$today_epoch" ]]; then
        id_cell="$(printf '%s' "$line" | awk -F'|' '{gsub(/^ +| +$/, "", $2); print $2}')"
        printf '⚠ OVERDUE %s — Until: %s\n' "$id_cell" "$iso"
        log_gap "DEFERRED.md row past Until: $id_cell ($iso)"
        overdue=$((overdue + 1))
      fi
    done < "$REPO/DEFERRED.md"
    [[ "$overdue" -eq 0 ]] && echo "✅ no past-due Until: rows"
  else
    echo "(DEFERRED.md missing — would be flagged in §2 above)"
  fi

  cat <<EOF

## 2c. Owner=TODO drift (H7)

Doctrine + DEFERRED rows where ownership is unresolved. Each row should
either land an owner or be re-scoped.

EOF

  # H7: scan for unresolved ownership across the doctrine surface.
  # Two patterns are accepted:
  #   (a) `Owner: TODO` — prose-form ownership tag, word-boundary on TODO
  #       so "Owner: TODO content drift" doesn't false-positive.
  #   (b) `| TODO |` — owner cell in a markdown table row, case-insensitive.
  # Lines with leading `>` (markdown blockquote) are filtered out so the
  # row template in DEFERRED.md§Format doesn't fire.
  todo_targets=(
    "DEFERRED.md"
    "AGENTS.md"
    "CLAUDE.md"
    ".supergoal/STATE.md"
  )
  todo_hits=0
  scan_owner_todo() {
    local file="$1" label="$2"
    grep -nE '(Owner:[[:space:]]*TODO\b|\|[[:space:]]*TODO[[:space:]]*\|)' "$file" 2>/dev/null \
      | grep -vE '^[0-9]+:[[:space:]]*>' || true
  }
  for tgt in "${todo_targets[@]}"; do
    [[ -f "$REPO/$tgt" ]] || continue
    while IFS=: read -r lineno body; do
      printf '⚠ %s:%s — %s\n' "$tgt" "$lineno" "$(printf '%s' "$body" | sed 's/^[[:space:]]*//' | cut -c1-120)"
      log_gap "Owner=TODO drift: $tgt:$lineno"
      todo_hits=$((todo_hits + 1))
    done < <(scan_owner_todo "$REPO/$tgt" "$tgt")
  done
  if [[ -d "$REPO/docs" ]]; then
    while IFS=: read -r path lineno body; do
      rel="${path#"$REPO"/}"
      printf '⚠ %s:%s — %s\n' "$rel" "$lineno" "$(printf '%s' "$body" | sed 's/^[[:space:]]*//' | cut -c1-120)"
      log_gap "Owner=TODO drift: $rel:$lineno"
      todo_hits=$((todo_hits + 1))
    done < <(grep -rnE --include='*.md' '(Owner:[[:space:]]*TODO\b|\|[[:space:]]*TODO[[:space:]]*\|)' "$REPO/docs" 2>/dev/null \
      | grep -vE ':[[:space:]]*>' || true)
  fi
  [[ "$todo_hits" -eq 0 ]] && echo "✅ no Owner=TODO rows"

  cat <<EOF

## 2d. Orphan doctrine anchors (H7 / G13 ep28)

Files listed in §2 that exist but appear referenced nowhere else in the
repo — candidate sunset bucket per "eval集不能只增不删".

EOF

  # H7: for each §2 path that exists, grep the repo for the file's
  # basename. The path itself counts as 1 hit; ≤ 1 means no other
  # doctrine file mentions it → orphan candidate. Vendored KAOS subtree
  # and the audit script's own output are excluded so they don't mask
  # a legitimate orphan.
  orphans=0
  for path in "${AUDIT_PATHS[@]}"; do
    [[ -e "$REPO/$path" ]] || continue
    base="$(basename "$path")"
    # `--include-dir=...` is not portable across grep impls; use the
    # broader -r with --exclude-dir filters.
    refs="$(grep -r --binary-files=without-match --exclude-dir=.git \
      --exclude-dir=packages/kaos --exclude-dir=node_modules \
      --exclude-dir=.venv --exclude-dir=__pycache__ \
      --exclude='*-weekly-harness-audit.md' --exclude='*.lock' \
      -l "$base" "$REPO" 2>/dev/null | wc -l)"
    if [[ "$refs" -le 1 ]]; then
      printf '⚠ orphan: `%s` referenced only by itself (refs=%s)\n' "$path" "$refs"
      log_gap "orphan doctrine anchor: $path (refs=$refs)"
      orphans=$((orphans + 1))
    fi
  done
  [[ "$orphans" -eq 0 ]] && echo "✅ no orphan doctrine anchors"

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
