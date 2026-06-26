#!/usr/bin/env python3
"""pr-cascade-breaker — POST-HOC review-comment gate for GitHub App reviewers.

We can't intercept the chatgpt-codex-connector / cursor-agent / agy GitHub App
PAYLOAD before it lands (they call the GitHub API directly). What we CAN do is
react on `pull_request_review_comment.created` events: fetch the comment, check
it against the reviewer_finding schema, and minimize off-spec comments with a
clear reason + a one-line link to the skill. This is the D2-aligned control
action that turns "detect-and-log" into "detect-and-mute".

Exempt: human comments, the warning the gate itself posts, and any comment with
the literal opt-out marker `[pr-cascade-breaker: skip <reason>]` on its own line.

CI surface: .github/workflows/pr-cascade-breaker-gate.yml fires on
pull_request_review_comment.created and pull_request_review.submitted, and runs:
  python3 scripts/pr_cascade_breaker_gate.py --repo "$REPO" --pr "$PR" --comment-id "$CID"
  python3 scripts/pr_cascade_breaker_gate.py --repo "$REPO" --pr "$PR" --review-id "$RID"
The workflow grep-verifies evidence_quote against a HEAD checkout (--repo-root
_pr_head), not the trusted base tree, so quotes of NEW/CHANGED lines verify.

Exit 0 even when minimizing — the gate is informational+protective, not a blocker.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any

# Reviewer GitHub App / bot logins this gate applies to.
BOT_LOGINS = {
    "chatgpt-codex-connector[bot]",
    "chatgpt-codex-connector",
    "codex[bot]",
    "codex",
    "cursor-agent[bot]",
    "cursor-agent",
    "agy[bot]",
}

REQUIRED_KEYS = {
    "kind",
    "priority",
    "blocking_verdict",
    "exploitability",
    "file",
    "evidence_quote",
    "fix_suggestion",
    "withdraw_condition",
}
ARCH_KINDS = {"architecture", "logic", "security"}
SKIP_MARKER_RE = re.compile(r"^\[pr-cascade-breaker:\s*skip\b.*\]\s*$", re.MULTILINE)
BLOCK_RE = re.compile(r"```reviewer_finding\s*\n(.*?)```", re.DOTALL)

GATE_BANNER = (
    "<!-- pr-cascade-breaker:gate-warning -->\n"
    "**pr-cascade-breaker gate** — this comment is missing the mandatory "
    "`reviewer_finding` YAML block (or it failed grep-verification of "
    "`evidence_quote`). The comment has been **minimised**. Re-post per the "
    'skill (`~/.claude/skills/pr-cascade-breaker/SKILL.md`) §"Reviewer-Finding '
    'format". Reason: `{reason}`.'
)


def gh(args: list[str], **kw: Any) -> str:
    return subprocess.check_output(["gh", *args], text=True, **kw)


def gh_api(path: str, *flags: str) -> dict:
    return json.loads(gh(["api", path, *flags]))


def gh_api_check(path: str, *flags: str) -> bool:
    try:
        gh(["api", path, *flags], stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False


def validate_body(body: str, repo_root: str) -> tuple[bool, str]:
    """Return (ok, reason). ok=True means the comment passes; reason is human-readable."""
    if SKIP_MARKER_RE.search(body):
        return True, "skip-marker"
    if "<!-- pr-cascade-breaker:gate-warning -->" in body:
        return True, "gate-own-warning"
    m = BLOCK_RE.search(body)
    if not m:
        return False, "no_reviewer_finding_block"
    try:
        import yaml
    except ImportError:
        # Fail CLOSED: without a YAML parser we cannot validate the schema, so
        # the finding is unverified → minimise rather than accept it (a missing
        # PyYAML on a runner must NOT silently disable every schema check).
        return False, "yaml-missing-fail-closed"
    try:
        d = yaml.safe_load(m.group(1)) or {}
    except Exception as e:
        return False, f"yaml_parse:{e}"
    if not isinstance(d, dict):
        return False, "reviewer_finding_not_a_mapping"
    missing = REQUIRED_KEYS - set(d.keys())
    if missing:
        return False, f"missing_keys:{sorted(missing)}"
    # Scalar-type guard: a non-scalar value (e.g. `kind: [logic]`) must not reach
    # the `in ARCH_KINDS` membership test, which would raise TypeError that the
    # workflow masks via `set +e`/exit 0, leaving the comment unminimised.
    kind = d.get("kind")
    if not isinstance(kind, str):
        return False, "kind_not_scalar"
    if kind in ARCH_KINDS and not d.get("citation"):
        return False, f"{kind}_without_citation"
    if d.get("exploitability") == "HIGH" and not d.get("exploit_demo"):
        return False, "HIGH_exploitability_without_exploit_demo"
    # A nonempty evidence_quote is mandatory: an empty/whitespace quote would skip
    # grep-verification entirely and let the finding through with no evidence.
    raw_quote = d.get("evidence_quote")
    if not isinstance(raw_quote, str) or not raw_quote.strip():
        return False, "evidence_quote_empty"
    quote = raw_quote.strip().split("\n", 1)[0]
    if d.get("file"):
        # Contain the attacker-influenced `file` field to the checkout tree: an
        # absolute path or `../` escape would otherwise grep an arbitrary runner
        # file and could force a false PASS. Reject escapes before touching disk.
        target = os.path.realpath(os.path.join(repo_root, d["file"]))
        root = os.path.realpath(repo_root)
        if target != root and not target.startswith(root + os.sep):
            return False, "evidence_quote_file_escapes_tree"
        try:
            # `--` ends grep option parsing so an evidence_quote whose first line
            # starts with `-`/`--` (YAML list items `- name:`, CLI flags like
            # `--repo-root`) is treated as the search pattern, not an option.
            # Without it grep exits rc=2 and a VALID finding is false-minimised.
            subprocess.check_output(
                ["grep", "-F", "--", quote, target],
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return False, "evidence_quote_grep_WITHDRAWN"
    return True, "ok"


def minimise_comment(node_id: str, reason: str) -> bool:
    """GraphQL minimizeComment with classifier OFF_TOPIC + post a sibling warning."""
    mut = (
        "mutation($id:ID!){ minimizeComment(input:{subjectId:$id,classifier:OFF_TOPIC})"
        "{ minimizedComment{ isMinimized minimizedReason } } }"
    )
    try:
        gh(
            ["api", "graphql", "-f", f"query={mut}", "-F", f"id={node_id}"],
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, help="owner/repo")
    p.add_argument("--pr", required=True, type=int)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--comment-id", help="REST comment id (review_comment)")
    src.add_argument(
        "--review-id",
        help="REST review id — validates the review BODY (pull_request_review)",
    )
    p.add_argument("--repo-root", default=".", help="path to a clean checkout for grep-verify")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    # Two surfaces: an inline review_comment, or a PR-level review body. Both
    # resolve to (body, node_id, target_id) and then share the validate/minimise
    # path. The review-body path closes the gap where a malformed review with no
    # inline comments would otherwise bypass the gate entirely.
    if a.review_id is not None:
        review = gh_api(f"repos/{a.repo}/pulls/{a.pr}/reviews/{a.review_id}")
        user = review.get("user", {}).get("login", "")
        if user not in BOT_LOGINS:
            print(f"::notice::skipping non-bot review by {user}")
            return 0
        body = review.get("body", "") or ""
        node = review.get("node_id")
        target_id = a.review_id
        if not body.strip():
            print(f"::notice::review {target_id} has empty body — nothing to validate")
            return 0
    else:
        comment = gh_api(f"repos/{a.repo}/pulls/comments/{a.comment_id}")
        user = comment.get("user", {}).get("login", "")
        if user not in BOT_LOGINS:
            print(f"::notice::skipping non-bot comment by {user}")
            return 0
        body = comment.get("body", "")
        node = comment.get("node_id")
        target_id = a.comment_id

    if not node:
        print("::warning::comment/review lacks node_id — cannot minimise")
        return 0

    ok, reason = validate_body(body, a.repo_root)
    print(f"::notice::pr-cascade-breaker: target={target_id} ok={ok} reason={reason}")
    if ok:
        return 0
    if a.dry_run:
        print(f"::notice::DRY — would minimise {target_id} (reason={reason})")
        return 0

    if minimise_comment(node, reason):
        print(f"::notice::minimised {target_id} via GraphQL")
        # Post a one-line warning on the PR (idempotent: only if not already there).
        # NOTE (fork/Dependabot): this REST POST can also 403 under a read-only
        # token; we run it check=False and surface failure visibly below rather
        # than masking it.
        existing = gh_api(f"repos/{a.repo}/issues/{a.pr}/comments")
        already = any("pr-cascade-breaker:gate-warning" in c.get("body", "") for c in existing)
        if not already:
            warning = GATE_BANNER.format(reason=reason)
            posted = subprocess.run(
                [
                    "gh",
                    "api",
                    f"repos/{a.repo}/issues/{a.pr}/comments",
                    "-X",
                    "POST",
                    "-f",
                    f"body={warning}",
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if posted.returncode != 0:
                # Read-only token (fork PR) — make the swallowed failure VISIBLE.
                print(
                    "::warning::minimised but FAILED to post gate-warning comment "
                    f"for {target_id} — likely a read-only GITHUB_TOKEN on a fork/"
                    "Dependabot PR. Off-spec finding is hidden but unannotated."
                )
    else:
        # On fork/Dependabot PRs review events can run with a read-only
        # GITHUB_TOKEN: minimizeComment 403s and the off-spec comment stays
        # VISIBLE. We have no privileged App/PAT secret to escalate to, so we
        # surface this as a loud warning annotation instead of exiting silently.
        print(
            f"::warning::FAILED to minimise {target_id} — read-only GITHUB_TOKEN "
            "(fork/Dependabot PR) or missing graphql:write. Off-spec finding "
            "remains VISIBLE; no privileged token available to escalate."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
