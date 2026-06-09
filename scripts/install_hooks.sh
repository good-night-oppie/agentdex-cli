#!/usr/bin/env bash
# scripts/install_hooks.sh — wire .pre-commit-config.yaml into .git/hooks
# so a fresh clone gets the rails AGENTS.md says exist (PR-C, workflow
# w0z1i9vcs H1 fix).
#
# Usage: bash scripts/install_hooks.sh
#
# Prereq: `uv sync --group dev` (installs pre-commit + ruff + mypy +
# detect-secrets per [dependency-groups] in pyproject.toml).

set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 0

if ! command -v pre-commit >/dev/null 2>&1; then
  if command -v uv >/dev/null 2>&1; then
    echo "pre-commit not on PATH — invoking via uv run"
    PRE_COMMIT=(uv run --no-sync pre-commit)
  else
    echo "FATAL: pre-commit not on PATH and uv not available either."
    echo "       Run: uv sync --group dev  (or: pip install pre-commit)"
    exit 1
  fi
else
  PRE_COMMIT=(pre-commit)
fi

"${PRE_COMMIT[@]}" install --hook-type pre-commit
echo "✓ pre-commit hooks installed at .git/hooks/pre-commit"

# Optional: also install commit-msg hooks if any are configured later.
if grep -q "commit-msg" .pre-commit-config.yaml 2>/dev/null; then
  "${PRE_COMMIT[@]}" install --hook-type commit-msg
  echo "✓ pre-commit commit-msg hook installed"
fi
