#!/usr/bin/env bash
# new_worktree.sh — open a worktree ONLY from a clean, green, fresh base.
#
#   bash scripts/new_worktree.sh <branch-name> [base]      # base defaults to main
#
# WHY THIS EXISTS
# ---------------
# Three failures this repo has actually taken, all of which start at worktree
# creation:
#
#  1. BRANCHING OFF A DIRTY TREE. The primary tree is SHARED across sessions. A
#     worktree cut while the source tree carries uncommitted WIP inherits a base
#     nobody can reproduce, and the WIP silently blocks siblings.
#
#  2. BRANCHING OFF A RED TREE. An untracked .md under docs/ makes doc_lint exit
#     1 for every commit in the new worktree too — you inherit the red gate and
#     discover it only when your first commit is refused.
#
#  3. REUSING A WORKTREE via `checkout main && reset --hard`. This silently fails
#     to reset in ways that are invisible until push time
#     (feedback_worktree_reset_silent_fail). The only safe construction is a
#     FRESH `git worktree add -b <branch> origin/<base>` — which is what this
#     script does, always, with no reuse path.
#
# Exit 0 = worktree created. Exit 1 = base rejected. Exit 2 = usage/internal.
set -uo pipefail

BRANCH="${1:-}"
BASE="${2:-main}"

if [[ -z "$BRANCH" ]]; then
  echo "usage: bash scripts/new_worktree.sh <branch-name> [base=main]" >&2
  exit 2
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
  echo "[new-worktree] error: not inside a git repository" >&2
  exit 2
fi
cd "$REPO_ROOT" || exit 2

CLEAN_STATE="$REPO_ROOT/scripts/clean_state.py"

echo "[new-worktree] branch=$BRANCH base=origin/$BASE"

# --- Gate 1: the SOURCE tree must be clean + green ----------------------------
#
# HONEST RATIONALE (an earlier draft of this script claimed the wrong one, and an
# adversarial review caught it): the new worktree is created from origin/<base>,
# so the source tree's dirty state CANNOT propagate into it. This gate does NOT
# protect the new worktree. It protects the tree you are LEAVING BEHIND:
#
#   - This tree is SHARED across agent sessions. Walking away from uncommitted WIP
#     silently blocks every sibling that tries to commit here.
#   - An untracked .md under docs/ red-lines doc_lint for every one of them, for a
#     reason none of them can see (CI stays green — see docs/runbooks/clean-state.md).
#   - "I'll come back to it" is how the harness-HA doc sat untracked for 3 days.
#
# So: finish or park what is here before you fork your attention elsewhere.
if [[ -f "$CLEAN_STATE" ]]; then
  if ! python3 "$CLEAN_STATE" --mode worktree; then
    cat >&2 <<'EOF'

[new-worktree] REFUSING to open a new worktree while THIS tree is unclean.
[new-worktree] The new worktree would be fine — it is cut from origin/<base>.
[new-worktree] The problem is what you are LEAVING: this tree is shared, and the
[new-worktree] findings above will block every sibling session that commits here.
[new-worktree] Commit it, gitignore it, or discard it. Override: CLEAN_STATE_OVERRIDE=1
EOF
    exit 1
  fi
fi

# --- Gate 2: the base must be FRESH -------------------------------------------
# Branching from a stale origin/<base> is how you rebase onto 24 surprise commits
# later. Fetch, then require the local ref to match the remote.
if ! git fetch --quiet origin "$BASE" 2>/dev/null; then
  echo "[new-worktree] error: cannot fetch origin/$BASE" >&2
  exit 1
fi
echo "[new-worktree] fetched origin/$BASE @ $(git rev-parse --short "origin/$BASE")"

# --- Create: FRESH worktree, never a reused/reset one -------------------------
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  echo "[new-worktree] error: branch '$BRANCH' already exists locally." >&2
  echo "  Pick a new name. This script never reuses or resets an existing branch —" >&2
  echo "  'checkout && reset --hard' fails silently and is banned here." >&2
  exit 1
fi

WT_PATH="${REPO_ROOT}-${BRANCH//\//-}"
if [[ -e "$WT_PATH" ]]; then
  echo "[new-worktree] error: $WT_PATH already exists — remove it or choose another name." >&2
  exit 1
fi

git worktree add -b "$BRANCH" "$WT_PATH" "origin/$BASE" || exit 1

# --- Bootstrap the gate --------------------------------------------------------
# NOTHING in this repo installed hooks. A fresh clone or worktree had no gate at
# all, while .pre-commit-config.yaml cheerfully declared one — declaration is not
# installation, and an uninstalled gate is indistinguishable from a passing one.
#
# Hooks live in $GIT_COMMON_DIR/hooks, which every worktree of this repo SHARES,
# so installing here covers the new worktree too. Idempotent.
if [[ -f "$WT_PATH/scripts/install_doc_lint_precommit.sh" ]]; then
  ( cd "$WT_PATH" && bash scripts/install_doc_lint_precommit.sh ) \
    || echo "[new-worktree] WARNING: hook install failed — run it by hand in $WT_PATH" >&2
fi

echo "[new-worktree] ✅ $WT_PATH  (branch $BRANCH from origin/$BASE)"
echo "[new-worktree] next: cd $WT_PATH && uv sync --all-packages"
