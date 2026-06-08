#!/usr/bin/env bash
# Latest test counts, coverage, lint warnings — short summary, not full reports.
cd "$(dirname "$0")/../.."
echo "--- test count ---"
grep -cE '^(def test_|class Test)' tests/**/*.py 2>/dev/null | head -5
echo "--- coverage (if .coverage exists) ---"
[[ -f .coverage ]] && uv run coverage report --skip-empty 2>/dev/null | tail -5 || echo "no .coverage"
echo "--- ruff warnings ---"
uv run ruff check . 2>&1 | tail -3
