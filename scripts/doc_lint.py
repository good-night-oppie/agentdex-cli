#!/usr/bin/env python3
"""scripts/doc_lint.py — shim that defers to the upstream harness-engineering
doc_lint.py for 63-rule documentation linting.

Per the harness-2 "shared-rules" pattern (target eventual state =
`~/.claude/shared-rules/` with SkillClaw-pinned per-consumer versions),
adx-cli does NOT vendor a 1057-LOC copy of doc_lint.py — it shells out
to the upstream copy. This shim:

1. Resolves the upstream script location (default `~/gh/harness-engineering/
   scripts/doc_lint.py`; override via `$ADX_DOC_LINT_UPSTREAM`).
2. Verifies the upstream script exists + is executable.
3. exec()s it with the same args (`--staged` is the canonical
   pre-commit-hook invocation per scripts/install_doc_lint_precommit.sh).
4. Degrades gracefully when upstream is missing: prints a WARNING to
   stderr + exits 0 so the pre-commit hook does not block the commit.
   The 1h gap-log review (per feedback_gap_log_review memory) surfaces
   the missing dependency.

Drift policy: re-diff against upstream `doc_lint.py` SHA quarterly; pin
to a known-good upstream SHA via `$ADX_DOC_LINT_UPSTREAM_SHA` if drift
becomes a problem.

Doctrine anchor: DOC-LINT-005 / DOC-LINT-031 — gate at the earliest
enforcement point. The shim keeps the gate live without vendoring the
implementation.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

UPSTREAM_DEFAULT = "/home/admin/gh/harness-engineering/scripts/doc_lint.py"
GAP_LOG_DEFAULT = (
    Path.home() / ".cursor" / "projects" / "home-admin" / "heartbeat" / "monitor-gaps.md"
)


def _log_gap(msg: str) -> None:
    path = Path(os.environ.get("GAP_LOG", str(GAP_LOG_DEFAULT)))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"adx-cli doc_lint shim {msg}\n")
    except OSError:
        pass  # never block a commit on gap-log write failure


def main() -> int:
    upstream = Path(os.environ.get("ADX_DOC_LINT_UPSTREAM", UPSTREAM_DEFAULT))
    if not upstream.is_file() or not os.access(upstream, os.X_OK):
        msg = (
            f"WARNING: upstream {upstream} missing or not executable; "
            "skipping doc-lint. Install harness-engineering at the expected "
            "path OR set $ADX_DOC_LINT_UPSTREAM to a valid doc_lint.py."
        )
        print(msg, file=sys.stderr)
        _log_gap(msg)
        return 0
    # exec replaces the process; argv[0] = upstream path, argv[1:] = our args.
    os.execv(str(upstream), [str(upstream), *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
