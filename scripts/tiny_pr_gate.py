#!/usr/bin/env python3
"""tiny-pr-gate — deterministic LOC + Indivisible-Unit/Scope merge control.

TOTAL changed LOC = additions + deletions from ``git diff --numstat``.
<=50 passes with no exception. >50 (or binary/unparseable numstat) passes
ONLY with the exact case-sensitive PR-body contract:

    Indivisible-Unit: <substantive falsifiable reason>
    Indivisible-Scope: <space-separated exact repo-relative changed paths>

Reason quality (deterministic, fail-closed):
  - collapse internal whitespace (reject padding);
  - length >= 40 characters;
  - word count >= 6;
  - contains the standalone causal word ``because``;
  - contains >= 6 distinct non-placeholder content words;
  - not a listed placeholder / loose token.

Loose words (``indivisible``, ``bootstrap unit``, ``tiny-pr-exempt``,
``Local-review``) never bypass. Scope set must equal changed paths exactly
(no missing / extra / duplicate / unsafe paths). Fail-closed on binary or
unparseable numstat unless the exact exception + exact scope are present.

CI: ``.github/workflows/tiny-pr-gate.yml`` runs from the base-controlled
``pull_request_target`` workflow, checks out the trusted *base* commit, and
runs this script so a PR cannot weaken its own check. The first installation
PR is a manually reviewed control-plane change; candidate-head bootstrap is
intentionally forbidden. Job/check name: ``tiny-pr-gate``.

Exit 0 = pass; exit 1 = fail (merge-blocking).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Literal

LOC_LIMIT = 50
MIN_REASON_CHARS = 40
MIN_REASON_WORDS = 6
MIN_DISTINCT_REASON_WORDS = 6
BECAUSE_WORD = "because"

# Use [ \t] not \s — \s matches newlines and would let an empty Unit line
# swallow the following Scope line into the reason capture.
UNIT_RE = re.compile(r"^Indivisible-Unit:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
SCOPE_RE = re.compile(r"^Indivisible-Scope:[ \t]*(.+?)[ \t]*$", re.MULTILINE)

# Exact case-sensitive loose / placeholder reasons that never satisfy
# Indivisible-Unit (checked against whitespace-collapsed text).
LOOSE_REASONS = frozenset(
    {
        "indivisible",
        "bootstrap unit",
        "tiny-pr-exempt",
        "Local-review",
        "placeholder",
        "n/a",
        "N/A",
        "TODO",
        "TBD",
        "FIXME",
        "reason",
        "exception",
        "see description",
        "necessary",
        "required",
        "atomic",
        "cannot split",
        "indivisible unit",
        "generic reason",
    }
)

REASON_WORD_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")
GENERIC_REASON_WORDS = frozenset(
    {
        "and",
        "are",
        "atomic",
        "because",
        "bootstrap",
        "cannot",
        "description",
        "exception",
        "fixme",
        "for",
        "from",
        "generic",
        "have",
        "indivisible",
        "local-review",
        "must",
        "necessary",
        "placeholder",
        "reason",
        "required",
        "see",
        "split",
        "that",
        "the",
        "this",
        "tiny-pr-exempt",
        "todo",
        "tbd",
        "unit",
        "was",
        "were",
        "will",
        "with",
        "would",
    }
)

UNSAFE_PATH_RE = re.compile(r"(?:^|/)\.\.(?:/|$)")

ExecutionMode = Literal["trusted_base", "fail_closed_partial"]


@dataclass(frozen=True)
class NumstatRow:
    additions: int | None  # None = binary / unparseable counts
    deletions: int | None
    path: str
    binary: bool = False
    unparseable: bool = False


@dataclass(frozen=True)
class GateResult:
    ok: bool
    reason: str
    total_loc: int | None
    paths: tuple[str, ...]


def resolve_execution_mode(*, base_has_gate: bool, base_has_smoke: bool) -> ExecutionMode:
    """Trusted-base vs fail-closed selection (authoritative truth table).

    - Both base artifacts present → always execute base copies (PR cannot weaken).
    - Any artifact missing → fail closed (never fall back to candidate head).
    """
    if base_has_gate and base_has_smoke:
        return "trusted_base"
    return "fail_closed_partial"


def _collapse_ws(text: str) -> str:
    """Strip ends and collapse internal whitespace (rejects padding)."""
    return " ".join(text.split())


def _unit_reason_error(reason: str) -> str | None:
    """Return error token if reason fails substantive/falsifiable syntax."""
    collapsed = _collapse_ws(reason)
    if not collapsed:
        return "empty_unit_reason"
    if collapsed in LOOSE_REASONS or collapsed.startswith("Local-review:"):
        return f"loose_unit_reason:{collapsed}"
    if len(collapsed) < MIN_REASON_CHARS:
        return f"unit_reason_too_short:{len(collapsed)}"
    words = collapsed.split(" ")
    if len(words) < MIN_REASON_WORDS:
        return f"unit_reason_too_few_words:{len(words)}"
    if BECAUSE_WORD not in words:
        return "unit_reason_missing_because"
    # Reject reasons that are only placeholders glued around "because".
    without_because = _collapse_ws(" ".join(w for w in words if w != BECAUSE_WORD))
    if without_because in LOOSE_REASONS or without_because == "":
        return f"placeholder_unit_reason:{collapsed}"
    content_words = {
        word
        for word in REASON_WORD_RE.findall(collapsed.casefold())
        if len(word) >= 3 and word not in GENERIC_REASON_WORDS
    }
    if len(content_words) < MIN_DISTINCT_REASON_WORDS:
        return f"unit_reason_not_substantive:{len(content_words)}"
    return None


def _is_unsafe_path(path: str) -> bool:
    if path == "" or path != path.strip():
        return True
    if path.startswith("/") or path.startswith("~"):
        return True
    if "\\" in path or "\n" in path or "\r" in path or "\t" in path:
        return True
    if any(ord(ch) < 32 for ch in path):
        return True
    if UNSAFE_PATH_RE.search(path):
        return True
    parts = path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return True
    return False


def parse_numstat(text: str) -> tuple[list[NumstatRow], str | None]:
    """Parse ``git diff --numstat`` output.

    Returns (rows, fatal_error). fatal_error is set when a line cannot yield
    a deterministic path.
    """
    rows: list[NumstatRow] = []
    if text == "":
        return [], None
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            return [], f"unparseable_numstat_line:{line!r}"
        adds_s, dels_s, path = parts
        if path == "" or path != path.strip() or "\t" in path:
            return [], f"unsafe_path:{path!r}"
        if adds_s == "-" and dels_s == "-":
            rows.append(NumstatRow(None, None, path, binary=True))
            continue
        if adds_s.isdigit() and dels_s.isdigit():
            rows.append(NumstatRow(int(adds_s), int(dels_s), path))
            continue
        rows.append(NumstatRow(None, None, path, unparseable=True))
    return rows, None


def parse_exception(body: str) -> tuple[str | None, list[str] | None, str | None]:
    """Return (unit_reason, scope_paths, error).

    error is set when markers are present but malformed; None markers mean
    absent (not an error by itself — soft path may still apply).
    """
    unit_matches = UNIT_RE.findall(body or "")
    scope_matches = SCOPE_RE.findall(body or "")
    if not unit_matches and not scope_matches:
        return None, None, None
    if len(unit_matches) != 1 or len(scope_matches) != 1:
        return None, None, "exception_marker_count"
    reason_raw = unit_matches[0]
    reason_err = _unit_reason_error(reason_raw)
    if reason_err:
        return None, None, reason_err
    reason = _collapse_ws(reason_raw)
    scope_tokens = scope_matches[0].split()
    if not scope_tokens:
        return None, None, "empty_scope"
    if len(scope_tokens) != len(set(scope_tokens)):
        return None, None, "duplicate_scope_path"
    for p in scope_tokens:
        if _is_unsafe_path(p):
            return None, None, f"unsafe_scope_path:{p}"
    return reason, scope_tokens, None


def _scope_mismatch(scope: list[str], paths: tuple[str, ...]) -> str:
    scope_set = set(scope)
    path_set = set(paths)
    missing = sorted(path_set - scope_set)
    extra = sorted(scope_set - path_set)
    return f"scope_mismatch:missing={missing!r}:extra={extra!r}"


def evaluate(body: str, numstat_text: str) -> GateResult:
    rows, fatal = parse_numstat(numstat_text)
    if fatal:
        return GateResult(False, fatal, None, ())

    paths = tuple(r.path for r in rows)
    if len(paths) != len(set(paths)):
        return GateResult(False, "duplicate_numstat_path", None, paths)

    for p in paths:
        if _is_unsafe_path(p):
            return GateResult(False, f"unsafe_changed_path:{p}", None, paths)

    has_opaque = any(r.binary or r.unparseable for r in rows)
    total: int | None
    if has_opaque:
        total = None
    else:
        total = sum((r.additions or 0) + (r.deletions or 0) for r in rows)

    unit, scope, exc_err = parse_exception(body)
    has_exact_exception = unit is not None and scope is not None and exc_err is None

    if has_opaque:
        if exc_err:
            return GateResult(False, f"opaque_numstat:{exc_err}", total, paths)
        if not has_exact_exception:
            kind = "binary" if any(r.binary for r in rows) else "unparseable"
            return GateResult(
                False,
                f"opaque_numstat_requires_exception:{kind}",
                total,
                paths,
            )
        assert scope is not None
        if set(scope) != set(paths):
            return GateResult(False, _scope_mismatch(scope, paths), total, paths)
        return GateResult(True, "opaque_numstat_exception_ok", total, paths)

    assert total is not None
    if total <= LOC_LIMIT:
        return GateResult(True, f"within_limit:{total}", total, paths)

    if exc_err:
        return GateResult(False, f"over_limit:{total}:{exc_err}", total, paths)
    if not has_exact_exception:
        return GateResult(False, f"over_limit:{total}:missing_exception", total, paths)
    assert scope is not None
    if set(scope) != set(paths):
        return GateResult(
            False,
            f"over_limit:{total}:{_scope_mismatch(scope, paths)}",
            total,
            paths,
        )
    return GateResult(True, f"over_limit_exception_ok:{total}", total, paths)


def _load_body_from_event(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        event = json.load(f)
    body = (event.get("pull_request") or {}).get("body")
    return body if isinstance(body, str) else ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--body", help="PR body text")
    src.add_argument("--body-file", help="Path to PR body file")
    src.add_argument(
        "--event-path",
        help="GitHub event JSON path (reads pull_request.body)",
    )
    p.add_argument(
        "--numstat-file",
        required=True,
        help="Path to git diff --numstat output",
    )
    args = p.parse_args(argv)

    if args.body is not None:
        body = args.body
    elif args.body_file is not None:
        with open(args.body_file, encoding="utf-8") as f:
            body = f.read()
    else:
        event_path = args.event_path or os.environ.get("GITHUB_EVENT_PATH")
        if not event_path:
            print("ERROR: --event-path / GITHUB_EVENT_PATH required", file=sys.stderr)
            return 2
        body = _load_body_from_event(event_path)

    with open(args.numstat_file, encoding="utf-8") as f:
        numstat_text = f.read()

    result = evaluate(body, numstat_text)
    status = "PASS" if result.ok else "FAIL"
    print(
        f"tiny-pr-gate: {status} reason={result.reason} "
        f"total_loc={result.total_loc} paths={list(result.paths)}"
    )
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
