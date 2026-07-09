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

HOOK_DIR="$REPO_ROOT/.git/hooks"
HOOK_PATH="$HOOK_DIR/pre-commit"
DOC_LINT="$REPO_ROOT/scripts/doc_lint.py"

if [[ ! -x "$DOC_LINT" ]]; then
  echo "[install_doc_lint_precommit] ERROR: $DOC_LINT not found or not executable" >&2
  echo "  expected scripts/doc_lint.py to exist and be chmod +x" >&2
  exit 2
fi

case "${1:-}" in
  --uninstall)
    if [[ -f "$HOOK_PATH" ]] && grep -q 'doc_lint.py --staged' "$HOOK_PATH" 2>/dev/null; then
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

if [[ -f "$HOOK_PATH" && "$FORCE" -ne 1 ]]; then
  if grep -q 'doc_lint.py --staged' "$HOOK_PATH" 2>/dev/null; then
    echo "[install_doc_lint_precommit] hook already installed at $HOOK_PATH (no-op)"
    exit 0
  fi
  BACKUP="$HOOK_PATH.bak.$(date +%Y%m%d%H%M%S)"
  cp "$HOOK_PATH" "$BACKUP"
  echo "[install_doc_lint_precommit] existing hook backed up to $BACKUP"
fi

cat > "$HOOK_PATH" <<'HOOK'
#!/usr/bin/env bash
# pre-commit — installed by scripts/install_doc_lint_precommit.sh
# Runs scripts/doc_lint.py --staged. Exits non-zero on any BLOCK finding.
# Bypass once: git commit --no-verify   (avoid — defeats the point)

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
DOC_LINT="$REPO_ROOT/scripts/doc_lint.py"

# Neither `exec` nor an early `exit 0` here: other installers APPEND their own
# gates below this block (kanban-blast-radius does exactly that). Replacing this
# shell — or exiting it when doc_lint happens to be missing — silently disables
# every gate appended after us, and a disabled gate looks identical to a passing
# one. Run doc_lint as an ordinary command and let `set -e` do the blocking.
if [[ -x "$DOC_LINT" ]]; then
  # --staged is default but we pass it explicitly for clarity in `git config -l`-style audits.
  "$DOC_LINT" --staged
else
  echo "[pre-commit] WARNING: $DOC_LINT missing; skipping doc-lint" >&2
fi
HOOK

chmod +x "$HOOK_PATH"
echo "[install_doc_lint_precommit] installed at $HOOK_PATH"
echo "  next commit will run: $DOC_LINT --staged"
echo "  bypass once (discouraged): git commit --no-verify"
