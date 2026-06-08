#!/usr/bin/env bash
# Canonical test runner + concise parse. Agent reads exit code + last 20 lines.
set -uo pipefail
cd "$(dirname "$0")/../.."
uv run python -m pytest -v --tb=short 2>&1 | tee /tmp/agentdex-cli-test.log | tail -50
exit ${PIPESTATUS[0]}
