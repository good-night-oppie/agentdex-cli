"""``adx evolve`` — launch Weco's Claude dashboard bridge for an AgentCandidate."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

from adx_frontier.candidate import CandidateValidationError, load_candidate

DATA_FLOW_DISCLOSURE = """DATA FLOW DISCLOSURE
- Weco receives and streams the Claude conversation, reasoning, and tool events to its dashboard.
- `--billing claude` uses local Claude auth; `--billing weco` spends Weco wallet credits.
- If enabled, inner `weco run` sends the selected mutable source files and evaluation output to Weco.
- AgentDex coordinates locally and does not read or store Weco/Claude credentials.
"""


def _outer_prompt(candidate_name: str, ladder_id: str, *, inner_weco_run: bool) -> str:
    inner = (
        "You may use `weco run` as the optional inner single-metric mutation engine."
        if inner_weco_run
        else "Do not invoke `weco run`; drive mutations directly in this Claude session."
    )
    return (
        f"Run the AgentDex RSI outer loop for candidate {candidate_name!r} on ladder "
        f"{ladder_id!r}. Measure the real ladder objective before and after each mutation. "
        "Modify only the candidate.yaml mutable files and stay within its declared budget. "
        f"{inner} Submit each measured candidate through the collaborative Bene gate; "
        "only an ACCEPT verdict may be called promoted."
    )


def cmd_evolve(args: argparse.Namespace) -> int:
    print(DATA_FLOW_DISCLOSURE, file=sys.stderr, end="")
    if not args.accept_data_flow:
        print("refusing to connect without --accept-data-flow", file=sys.stderr)
        return 2
    try:
        candidate = load_candidate(args.agent)
        candidate.validate()
    except CandidateValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.ladder not in candidate.ladders:
        print(f"candidate does not declare ladder {args.ladder!r}", file=sys.stderr)
        return 2
    if args.headless and not args.allow_tools:
        print("--headless requires --allow-tools (no local approval modal)", file=sys.stderr)
        return 2
    if shutil.which("weco") is None:
        print("weco executable not found on PATH", file=sys.stderr)
        return 3
    prompt = args.prompt or _outer_prompt(
        candidate.name, args.ladder, inner_weco_run=args.inner_weco_run
    )
    argv = ["weco", "start", "claude", "--billing", args.billing, "--prompt", prompt]
    if args.effort:
        argv.extend(["--effort", args.effort])
    if args.headless:
        argv.append("--headless")
    if args.allow_tools:
        argv.append("--allow-tools")
    if args.dry_run:
        print(json.dumps({"cwd": str(candidate.root), "argv": argv}, indent=2))
        return 0
    return subprocess.run(argv, cwd=candidate.root, check=False).returncode


def register_evolve_parser(subs: argparse._SubParsersAction) -> None:
    evolve = subs.add_parser(
        "evolve", help="launch Weco-driven Claude RSI for a validated AgentCandidate"
    )
    evolve.add_argument("--agent", required=True, help="AgentCandidate directory")
    evolve.add_argument("--ladder", required=True, help="declared target ladder id")
    evolve.add_argument("--accept-data-flow", action="store_true")
    evolve.add_argument("--billing", choices=["claude", "weco"], default="claude")
    evolve.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    evolve.add_argument("--headless", action="store_true")
    evolve.add_argument("--allow-tools", action="store_true")
    evolve.add_argument("--inner-weco-run", action="store_true")
    evolve.add_argument("--prompt", default=None, help="override the seeded outer-loop prompt")
    evolve.add_argument("--dry-run", action="store_true", help="print launch JSON only")
    evolve.set_defaults(func=cmd_evolve)
