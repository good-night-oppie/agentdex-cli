"""``adx interview`` — capture how the user wants agentdex to orchestrate models.

agentdex's job is to *know which model does a given job better*, dispatch to it,
and learn a seed that improves the next iteration. To do that it needs a policy:
what jobs the user runs, what "better" means to them, which models are in the
pool, how a result is graded, and how much to explore vs exploit. This command
runs a short, fixed interview and writes that policy to
``.agentdex/orchestration.yaml`` — the spec the allocator/ledger consumes.

Design notes
------------
- **Fixed, curated questions.** The MVP asks a deterministic set (no model call,
  no network, no heavy deps). A dynamic LLM-driven intake (à la ``kaos.intake``)
  is a deliberate later add-back, not part of the smallest thing that works.
- **stdlib only.** Independently importable and testable without the package
  graph. The output file is the contract; nothing here reaches the network.
- ``--non-interactive`` seeds every answer from its documented default so the
  path is demonstrable in CI and smoke tests without a TTY.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class Question:
    """One orchestration-policy question.

    ``key`` makes the captured answer machine-consumable in the YAML output
    (structured by key, not just raw prose), so the allocator can read it.
    """

    key: str
    question: str
    why: str = ""
    default: str = ""
    example: str = ""


# The policy agentdex needs, in the order a builder reasons about it:
# what jobs → what "better" means → the pool → how to grade → constraints →
# explore/exploit. Each answer maps to one field of the allocation policy.
ORCHESTRATION_QUESTIONS: list[Question] = [
    Question(
        key="job_types",
        question="What kinds of jobs will you send agentdex? (comma-separated)",
        why="Allocation is per job-type — the ledger learns a winner for each signature.",
        default="bugfix, refactor, codegen, code-review, research",
        example="bugfix/python, refactor/ts, sql-optimization",
    ),
    Question(
        key="objective",
        question="What does 'better' mean — rank correctness, cost, latency (most first)?",
        why="Sets the objective priority order (lexicographic), case-insensitive — not weights.",
        default="correctness, cost, latency",
        example="correctness, latency, cost",
    ),
    Question(
        key="pool",
        question="Which models/subscriptions are available? (comma-separated)",
        why="The candidate pool the allocator fans a task across.",
        default="claude-opus, claude-sonnet, codex-gpt-5.6, deepseek, sakana-fugu",
        example="claude-opus, codex-gpt-5.6, my-endpoint",
    ),
    Question(
        key="gate",
        question="How is a result graded? (a shell command, or: tests | exit-code | llm-judge | manual)",
        why="The deterministic verifier that scores candidates and gates the winner.",
        default="tests",
        example="pytest -q  |  ./verify.sh  |  llm-judge",
    ),
    Question(
        key="constraints",
        question="Any hard limits? (max $/task, latency ceiling, models to never use for a job)",
        why="Constraints prune the pool before allocation.",
        default="none",
        example="max $0.50/task; never claude-opus for lint",
    ),
    Question(
        key="explore_rate",
        question="Explore vs exploit — 0.0 always-known-best … 1.0 always-try-alternatives",
        why="Bandit rate: how often to try a non-incumbent model to keep learning.",
        default="0.2",
        example="0.1",
    ),
]


def _ask(questions: list[Question], *, non_interactive: bool) -> dict[str, str]:
    """Collect answers. ``non_interactive`` uses each question's default."""
    if non_interactive:
        return {q.key: q.default for q in questions}

    print("\nagentdex interview — how should I orchestrate your models?")
    print("(Enter accepts the [default] shown.)\n")
    answers: dict[str, str] = {}
    for i, q in enumerate(questions, 1):
        print(f"  {i}. {q.question}")
        if q.why:
            print(f"     why: {q.why}")
        if q.example:
            print(f"     e.g. {q.example}")
        try:
            raw = input(f"     [{q.default}] > ").strip()
        except EOFError:
            raw = ""
        answers[q.key] = raw or q.default
        print()
    return answers


def _as_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


#: Values safe to emit unquoted: a plain-scalar shape that cannot start a YAML
#: sequence/mapping/anchor/tag/block, cannot be read as a bool/null under YAML
#: 1.1, and contains no indicator character.
_PLAIN_SAFE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_ ./+=-]*$")
_YAML11_RESERVED = frozenset(
    {
        "y",
        "n",
        "yes",
        "no",
        "true",
        "false",
        "on",
        "off",
        "null",
        "none",
        "~",
    }
)


def _yaml_scalar(value: str) -> str:
    """Quote a scalar unless it matches a known-safe plain shape.

    Allowlist, not blocklist. The previous blocklist missed a leading ``-``,
    which is the failure a user hits by answering the constraints question in
    bullet style: ``- never opus`` emitted ``constraints: - never opus``, which
    PyYAML rejects ("sequence entries are not allowed here"), so ``interview``
    reported success and the next ``adx run`` died at load_policy. Inside a LIST
    field the same gap corrupted silently instead — ``- claude-opus, deepseek``
    became a nested sequence and reached the allocator as a pool member
    literally named ``"['claude-opus']"``, which was then dispatched as a model
    id. A blocklist cannot be audited against YAML's full indicator set; an
    allowlist fails closed (worst case: a needlessly quoted string).
    """
    if _PLAIN_SAFE_RE.match(value) is None:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if value.casefold() in _YAML11_RESERVED:
        # YAML 1.1 would coerce these to bool/null, silently changing the type
        # the run side reads back.
        return '"' + value + '"'
    return value


def render_policy_yaml(answers: dict[str, str]) -> str:
    """Serialize the captured answers as ``.agentdex/orchestration.yaml``.

    Hand-rolled emitter (stdlib-only, fixed known shape) so the MVP carries no
    YAML dependency. Emits list-valued fields as YAML sequences and keeps the
    raw answer alongside so nothing the user said is lost.
    """
    stamp = datetime.now(UTC).replace(microsecond=0).isoformat()
    lines = [
        "# agentdex orchestration policy — captured by `adx interview`.",
        "# Consumed by the allocator/ledger to decide which model runs each job.",
        "version: 1",
        f"generated: {stamp}",
        "",
    ]
    list_fields = {"job_types", "objective", "pool"}
    for q in ORCHESTRATION_QUESTIONS:
        ans = answers.get(q.key, q.default)
        lines.append(f"# {q.question}")
        if q.key in list_fields:
            items = _as_list(ans)
            if items:
                lines.append(f"{q.key}:")
                lines.extend(f"  - {_yaml_scalar(x)}" for x in items)
            else:
                lines.append(f"{q.key}: []")
        else:
            lines.append(f"{q.key}: {_yaml_scalar(ans)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def cmd_interview(args: argparse.Namespace) -> int:
    out = Path(args.out).expanduser()
    if out.exists() and not args.force:
        print(f"refusing to overwrite existing policy at {out} (pass --force)")
        return 2
    answers = _ask(ORCHESTRATION_QUESTIONS, non_interactive=args.non_interactive)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_policy_yaml(answers), encoding="utf-8")
    print(f"\nwrote orchestration policy → {out}")
    print("next: `adx run <task>` will dispatch per this policy and learn seeds.")
    return 0


def register_interview_parser(subs: argparse._SubParsersAction) -> None:
    p = subs.add_parser(
        "interview",
        help="capture how agentdex should orchestrate your models (writes .agentdex/orchestration.yaml)",
    )
    p.add_argument(
        "--out",
        default=".agentdex/orchestration.yaml",
        help="where to write the policy (default: .agentdex/orchestration.yaml)",
    )
    p.add_argument(
        "--non-interactive",
        action="store_true",
        help="use documented defaults for every answer (CI / smoke tests)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing policy file",
    )
    p.set_defaults(func=cmd_interview)
