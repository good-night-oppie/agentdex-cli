#!/usr/bin/env bash
# scripts/install_doc_lint_precommit.sh — drop a .git/hooks/pre-commit that
# calls scripts/doc_lint.py --staged. Idempotent.
#
# Ported from ~/gh/harness-engineering/scripts/install_doc_lint_precommit.sh
# (autonomous-pipeline mirror, 2026-06-09). Paths already relative to repo
# root via `git rev-parse --show-toplevel`, so the body needs no rewriting —
# only the comment header is re-anchored.
#
# Doctrine: enforce doc-lint BEFORE the commit lands so a violation can't
# slip into history (DOC-LINT-005 / DOC-LINT-031 — gate at the earliest
# enforcement point, not in CI-only).
#
# Usage:
#   bash scripts/install_doc_lint_precommit.sh           # install (back up existing)
#   bash scripts/install_doc_lint_precommit.sh --force   # overwrite without backup
#   bash scripts/install_doc_lint_precommit.sh --uninstall
#
# Citations:
#   ep03 01-0142 "lint config at commit boundary"
#   ep05 02-5500 "CI doc_lint enforcement"
#   ep08 08-0346 "agent-authored commits gated by AGENTS.md surface"

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
  echo "[install_doc_lint_precommit] ERROR: not inside a git repo" >&2
  exit 2
fi

# The REAL hooks dir. NOT "$REPO_ROOT/.git/hooks": in a git worktree `.git` is a
# FILE ("gitdir: ..."), so that path is `Not a directory` and every hook op fails.
# This repo is developed out of worktrees, so the naive path is broken in the
# COMMON case. core.hooksPath wins if set; else $GIT_COMMON_DIR/hooks, which every
# worktree of the repo SHARES (install once, covered everywhere).
HOOKS_PATH_CFG="$(git config --get core.hooksPath || true)"
if [[ -n "$HOOKS_PATH_CFG" ]]; then
  HOOK_DIR="$HOOKS_PATH_CFG"
else
  COMMON_DIR="$(git rev-parse --git-common-dir)"
  [[ "$COMMON_DIR" = /* ]] || COMMON_DIR="$REPO_ROOT/$COMMON_DIR"
  HOOK_DIR="$COMMON_DIR/hooks"
fi
HOOK_PATH="$HOOK_DIR/pre-commit"
DOC_LINT="$REPO_ROOT/scripts/doc_lint.py"

if [[ ! -x "$DOC_LINT" ]]; then
  echo "[install_doc_lint_precommit] ERROR: $DOC_LINT not found or not executable" >&2
  echo "  expected scripts/doc_lint.py to exist and be chmod +x" >&2
  exit 2
fi

BEGIN_MARK='# >>> doc-lint+clean-state (managed by install_doc_lint_precommit.sh) >>>'
END_MARK='# <<< doc-lint+clean-state <<<'

case "${1:-}" in
  --uninstall)
    # Match the managed MARKER, not an invocation string: the template calls the
    # gates through variables ("$DOC_LINT"), so grepping for 'doc_lint.py --staged'
    # matched nothing and --uninstall was a permanent no-op that reported success.
    if [[ -f "$HOOK_PATH" ]] && grep -qF "$BEGIN_MARK" "$HOOK_PATH" 2>/dev/null; then
      rm -f "$HOOK_PATH"
      echo "[install_doc_lint_precommit] removed $HOOK_PATH"
    else
      echo "[install_doc_lint_precommit] no doc_lint pre-commit hook found at $HOOK_PATH"
    fi
    exit 0
    ;;
  --force)
    FORCE=1
    ;;
  "")
    FORCE=0
    ;;
  *)
    echo "[install_doc_lint_precommit] unknown arg: $1" >&2
    echo "  usage: $0 [--force|--uninstall]" >&2
    exit 2
    ;;
esac

mkdir -p "$HOOK_DIR"

# Serialize installers across worktrees/sessions. Without this, two concurrent
# runs interleave their read-modify-write of the SHARED hook and one silently
# loses (or corrupts) the other's gates.
LOCK="$HOOK_DIR/.clean-state-install.lock"
exec 9>"$LOCK"
if command -v flock >/dev/null 2>&1; then
  flock -w 30 9 || { echo "[install_doc_lint_precommit] ERROR: lock timeout on $LOCK" >&2; exit 2; }
fi

# Publish atomically: write a temp file in the SAME directory, then rename(2) it
# over the hook. rename is atomic within a filesystem, so a concurrent commit sees
# either the old hook or the new one — never a truncated one.
publish() {  # publish <src-tmp>
  chmod +x "$1"
  mv -f "$1" "$HOOK_PATH"
}

# --- managed block ------------------------------------------------------------
# The hook is assembled from a MANAGED BLOCK between the markers below, plus
# whatever other installers appended outside it (kanban-blast-radius appends its
# own `# >>> kanban-blast-radius >>>` region). Two failure modes this avoids:
#
#   1. `cat > "$HOOK_PATH"` clobbered the whole file, so --force silently DELETED
#      the appended blast-radius gate. A deleted gate looks exactly like a
#      passing one (feedback_gate_present_is_not_gate_running).
#   2. The old idempotency check (`grep doc_lint.py --staged` -> no-op) meant an
#      already-installed hook NEVER received a newly added gate. Every existing
#      dev would keep an outdated hook forever. We now key idempotency on the
#      managed-block CONTENT, so upgrades actually land.
read -r -d '' MANAGED <<'HOOK' || true
# >>> doc-lint+clean-state (managed by install_doc_lint_precommit.sh) >>>
# Do not edit between the markers — re-running the installer rewrites this region.
# Anything OUTSIDE the markers is preserved across re-installs.
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Gate 1 — clean state. No unignored untracked files.
# WHY FIRST: doc_lint globs the WORKING TREE while CI runs on a FRESH CLONE, so a
# single untracked .md under docs/ trips DOC-LINT-020 and blocks EVERY commit by
# EVERY session, while CI stays green and nobody can see why. That is not a lint
# failure, it is a congruence failure — and the rational response to a gate you
# cannot pass is --no-verify. Catch it here, with a message that says what to do.
CLEAN_STATE="$REPO_ROOT/scripts/clean_state.py"
if [[ -f "$CLEAN_STATE" ]]; then
  python3 "$CLEAN_STATE" --mode precommit
else
  # Loud, not silent. A gate that quietly no-ops when its script is missing (an
  # older branch, a bad rebase) is indistinguishable from a gate that passed.
  echo "[pre-commit] WARNING: $CLEAN_STATE missing; clean-state NOT enforced on this commit" >&2
fi

# Gate 2 — doc-lint over the staged set.
DOC_LINT="$REPO_ROOT/scripts/doc_lint.py"
# Neither `exec` nor an early `exit 0` here: other installers APPEND their own
# gates below this block. Replacing this shell — or exiting it when a script
# happens to be missing — silently disables every gate appended after us.
if [[ -x "$DOC_LINT" ]]; then
  "$DOC_LINT" --staged
else
  echo "[pre-commit] WARNING: $DOC_LINT missing; skipping doc-lint" >&2
fi
# <<< doc-lint+clean-state <<<
HOOK

if [[ ! -f "$HOOK_PATH" ]]; then
  TMP_HOOK="$(mktemp "$HOOK_DIR/.pre-commit.XXXXXX")"
  { printf '#!/usr/bin/env bash\n'
    printf '# pre-commit — see scripts/install_doc_lint_precommit.sh\n'
    printf '# Bypass once: git commit --no-verify   (avoid — defeats the point)\n'
    printf 'set -euo pipefail\n\n'
    printf '%s\n' "$MANAGED"
  } > "$TMP_HOOK"
  publish "$TMP_HOOK"
  echo "[install_doc_lint_precommit] installed fresh hook at $HOOK_PATH"
elif grep -qF "$BEGIN_MARK" "$HOOK_PATH"; then
  # Replace ONLY the managed region; preserve every appended gate outside it.
  # awk splice with the new block read from a file — no shell interpolation of
  # the block body, so quotes/backslashes inside it cannot corrupt the result.
  BACKUP="$HOOK_PATH.bak.$(date +%Y%m%d%H%M%S)"
  cp "$HOOK_PATH" "$BACKUP"
  MANAGED_FILE="$(mktemp)"
  printf '%s\n' "$MANAGED" > "$MANAGED_FILE"
  TMP_HOOK="$(mktemp "$HOOK_DIR/.pre-commit.XXXXXX")"
  awk -v begin="$BEGIN_MARK" -v end="$END_MARK" -v mf="$MANAGED_FILE" '
    index($0, begin) == 1 { inblk = 1; while ((getline line < mf) > 0) print line; next }
    inblk && index($0, end) == 1 { inblk = 0; next }
    !inblk { print }
  ' "$BACKUP" > "$TMP_HOOK"
  rm -f "$MANAGED_FILE"
  publish "$TMP_HOOK"
  echo "[install_doc_lint_precommit] refreshed managed block (appended gates preserved; backup $BACKUP)"
else
  # Pre-existing hook with no markers (e.g. the old clobbering layout). Preserve
  # its body verbatim and prepend the managed block above it.
  BACKUP="$HOOK_PATH.bak.$(date +%Y%m%d%H%M%S)"
  cp "$HOOK_PATH" "$BACKUP"
  EXISTING="$(grep -vE '^\s*(#!/usr/bin/env bash|set -euo pipefail)\s*$' "$HOOK_PATH" \
              | grep -vF 'doc_lint.py --staged' || true)"
  TMP_HOOK="$(mktemp "$HOOK_DIR/.pre-commit.XXXXXX")"
  { printf '#!/usr/bin/env bash\n'
    printf '# pre-commit — see scripts/install_doc_lint_precommit.sh\n'
    printf 'set -euo pipefail\n\n'
    printf '%s\n\n' "$MANAGED"
    printf '%s\n' "$EXISTING"
  } > "$TMP_HOOK"
  publish "$TMP_HOOK"
  echo "[install_doc_lint_precommit] adopted existing hook; managed block prepended (backup $BACKUP)"
fi

echo "  next commit runs: clean_state.py --mode precommit, then doc_lint.py --staged"
echo "  bypass once (discouraged): git commit --no-verify"
