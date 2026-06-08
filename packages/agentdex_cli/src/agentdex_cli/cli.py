"""adx CLI shell — orchestrator entrypoint + subcommands.

Phase-5 scope: ``adx bridge probe --bridge <name> --task <id>`` — one-turn
probe through a baseline bridge.

Phase-7 scope: ``adx expedition --task <id> --baselines csv --judge <llm>
--output <dir>`` — full M5 MVP gate. Loads the task bundle, resolves bridges,
runs :func:`agentdex_engine.expedition.run_expedition_orchestrator`, writes 6
yaml artifacts + 3 trace jsonl per baseline under ``<output>/``, persists
lineage in KAOS, returns ``0`` on success / non-zero on a failed acceptance.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Optional


REPO_ROOT_ENV = "AGENTDEX_REPO_ROOT"


def _detect_repo_root() -> Path:
    if (env := os.environ.get(REPO_ROOT_ENV)):
        return Path(env)
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "tasks").is_dir() and (parent / "packages").is_dir():
            return parent
    return Path.cwd()


def _first_source_file(task_id: str, root: Path) -> Optional[Path]:
    task_dir = root / "tasks" / task_id
    if not task_dir.is_dir():
        return None
    sources = sorted((task_dir / "sources").glob("*.md")) if (task_dir / "sources").is_dir() else []
    return sources[0] if sources else None


def _load_prompt_for_task(task_id: str, root: Path) -> str:
    src = _first_source_file(task_id, root)
    if src is None:
        return (
            f"You are participating in the {task_id} expedition. Briefly describe "
            "what data you would need to produce an infographic, focusing on "
            "revenue and gross margin metrics."
        )
    body = src.read_text(encoding="utf-8")[:4000]
    return (
        f"Task: summarize the following source for an earnings infographic. "
        f"Focus on revenue and gross margin claims. Reply concisely.\n\n"
        f"=== {src.name} ===\n{body}\n"
    )


async def _run_probe(bridge_name: str, task_id: str, *, timeout: float) -> tuple[str, Optional[str], str]:
    """Returns ``(text, trace_id, used_bridge_name)``."""
    from adx_bridges import build_bridge

    root = _detect_repo_root()
    prompt = _load_prompt_for_task(task_id, root)
    bridge = build_bridge(bridge_name, workdir=str(root))
    try:
        coro = bridge.send(prompt, extra={"max_turns": 1})
        text, trace_id = await asyncio.wait_for(coro, timeout=timeout)
        return text, trace_id, bridge.cfg.name
    finally:
        try:
            await bridge._kill()  # type: ignore[attr-defined]
        except Exception:
            pass


def cmd_bridge_probe(args: argparse.Namespace) -> int:
    try:
        text, trace_id, used = asyncio.run(
            _run_probe(args.bridge, args.task, timeout=float(args.timeout))
        )
    except Exception as e:
        print(f"PROBE_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    print(f"--- bridge: {used} ---")
    print(f"--- task:   {args.task} ---")
    print(text or "<empty>")
    if trace_id:
        from agentdex_observe import current_trace_url
        url = current_trace_url() or f"<trace-id:{trace_id}>"
        print(f"langfuse_trace_url: {url}")
    else:
        print("langfuse_trace_url: trace disabled (LANGFUSE_PUBLIC_KEY unset)")

    return 0 if (text or "").strip() else 1


def _load_task_bundle(task_id: str, repo_root: Path):
    """Load tasks/<id>/bundle.yaml and validate against TaskCard."""
    import yaml

    from agentdex_engine.cards import TaskCard

    bundle_path = repo_root / "tasks" / task_id / "bundle.yaml"
    if not bundle_path.is_file():
        raise FileNotFoundError(f"task bundle not found: {bundle_path}")
    raw = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
    return TaskCard.model_validate(raw)


def _build_default_oracle_chain(
    task_id: str,
    repo_root: Path,
    judge_llm: str,
    *,
    mocked: bool = False,
):
    """Hard (number + provenance) + soft (LLM judge) Oracle chain."""
    from agentdex_engine.oracle.base import OracleChain
    from agentdex_engine.oracle.hard import NumberAccuracyOracle, ProvenanceOracle
    from agentdex_engine.oracle.soft import LlmJudgeOracle

    spec_path = repo_root / "tasks" / task_id / "oracle" / "spec.yaml"
    chart_sanity = repo_root / "tasks" / task_id / "oracle" / "chart_sanity.md"

    soft_client_factory = _make_stub_judge_client() if mocked else None
    oracles = {
        "number": NumberAccuracyOracle(spec_path),
        "prov": ProvenanceOracle(),
        "soft": LlmJudgeOracle(
            judge_llm=judge_llm,
            rubric_path=chart_sanity if chart_sanity.is_file() else None,
            client_factory=soft_client_factory,
        ),
    }
    return OracleChain(oracles)


def _make_stub_judge_client():
    """Offline judge that returns a fixed coherent verdict — used by --mocked.

    Returns a callable that produces a stub Anthropic-shaped client whose
    ``.messages.create(...)`` returns a single content-block message carrying a
    JSON verdict body. Used by the soft Oracle when the workspace has no
    Anthropic SDK / API key.
    """
    verdict_body = (
        '{"score": 0.78, "uncertainty": 0.35, "pass": true, '
        '"rationale": "Mocked judge: response covers revenue, gross margin, '
        'and provenance citations coherently."}'
    )

    class _StubMessage:
        def __init__(self):
            block = type("B", (), {"text": verdict_body})
            self.content = [block]

    class _StubMessages:
        def create(self, *, model, max_tokens, system, messages):
            return _StubMessage()

    class _StubClient:
        messages = _StubMessages()

    return lambda: _StubClient()


def _instantiate_bridges(names: list[str], workdir: str):
    from adx_bridges import build_bridge

    return [build_bridge(name.strip(), workdir=workdir) for name in names]


def _evolution_card_to_yaml_dict(card) -> dict:
    """Pydantic → plain-dict suitable for yaml.safe_dump (handles Seed alias)."""
    data = card.model_dump(by_alias=False)
    return data


def _write_yaml(path: Path, payload: dict) -> None:
    import yaml

    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_trace_jsonl(path: Path, expedition_id: str, result_card, response_text: str) -> None:
    """Best-effort per-bridge trace jsonl — one record per turn (M5 MVP shim).

    Phase-8 polish replaces this with the full Langfuse-exported span tree.
    """
    record = {
        "expedition_id": expedition_id,
        "agent_id": result_card.agent_id,
        "turn_idx": 1,
        "pass_rate": result_card.pass_rate,
        "speed_wall_clock_sec": result_card.speed_wall_clock_sec,
        "langfuse_trace_id": result_card.langfuse_trace_id,
        "response_excerpt": response_text[:2000],
    }
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")


async def _run_expedition(args: argparse.Namespace) -> int:
    from agentdex_engine.expedition import run_expedition_orchestrator
    from agentdex_engine.shared.kaos_adapter import log_expedition_lineage

    repo_root = _detect_repo_root()
    task_card = _load_task_bundle(args.task, repo_root)
    oracle_chain = _build_default_oracle_chain(
        args.task, repo_root, args.judge, mocked=args.mocked
    )

    baselines = [b.strip() for b in args.baselines.split(",") if b.strip()]
    if args.mocked:
        bridges = _make_mock_bridges(baselines, args.task, repo_root)
    else:
        bridges = _instantiate_bridges(baselines, str(repo_root))

    try:
        result_cards, verdict, evolution_card = await asyncio.wait_for(
            run_expedition_orchestrator(
                task_card,
                bridges,
                oracle_chain,
                args.judge,
                repo_root=repo_root,
            ),
            timeout=args.timeout * max(len(bridges), 1),
        )
    finally:
        for b in bridges:
            try:
                await b._kill()  # type: ignore[attr-defined]
            except Exception:
                pass

    output_dir = (repo_root / args.output) if not Path(args.output).is_absolute() else Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_dir = output_dir / "trace"
    trace_dir.mkdir(exist_ok=True)

    _write_yaml(output_dir / "task_card.yaml", task_card.model_dump())
    for rc in result_cards:
        agent_slug = rc.agent_id.replace("(", "_").replace(")", "").replace("/", "_")
        _write_yaml(output_dir / f"result_card_{agent_slug}.yaml", rc.model_dump())
    _write_yaml(output_dir / "pareto_verdict.yaml", verdict.model_dump())
    _write_yaml(output_dir / "evolution_card.yaml", _evolution_card_to_yaml_dict(evolution_card))

    # Trace jsonl per bridge — uses recorded response excerpt from mock path,
    # or empty when live bridges did not stash a transcript (P8 polish).
    for rc in result_cards:
        agent_slug = rc.agent_id.replace("(", "_").replace(")", "").replace("/", "_")
        excerpt = _MOCKED_RESPONSE_BY_AGENT.get(rc.agent_id, "")
        _write_trace_jsonl(
            trace_dir / f"{agent_slug}_full_trace.jsonl",
            evolution_card.expedition_id,
            rc,
            excerpt,
        )

    kaos_agent = log_expedition_lineage(
        args.kaos_db,
        evolution_card.expedition_id,
        _evolution_card_to_yaml_dict(evolution_card),
    )

    print(f"--- expedition: {evolution_card.expedition_id} ---")
    print(f"baselines: {[rc.agent_id for rc in result_cards]}")
    print(f"pareto verdict: {verdict.verdict_kind} winner={verdict.winner}")
    print(f"mutation_seed_categories: {sorted(evolution_card.mutation_seeds.keys())}")
    print(f"kaos_lineage_agent_id: {kaos_agent}")
    print(f"output_dir: {output_dir}")
    return 0


_MOCKED_RESPONSE_BY_AGENT: dict[str, str] = {}


def _make_mock_bridges(baselines: list[str], task_id: str, repo_root: Path):
    """Recorded mock bridges (deterministic + offline) for smoke tests."""
    global _MOCKED_RESPONSE_BY_AGENT

    common_body = (
        "- Revenue: $35.08 billion (source: nvidia-q3-fy2026-press-release.md:14)\n"
        "- Data Center: $30.77 billion, +112% YoY "
        "(source: nvidia-q3-fy2026-press-release.md:26)\n"
        "- GAAP gross margin: 74.6% (source: nvidia-q3-fy2026-press-release.md:42)\n"
        "- Q4 outlook: $37.5 billion ± 2% (source: nvidia-q3-fy2026-press-release.md:60)\n"
        "- China revenue $5.40 billion, 16% mix "
        "(source: nvidia-q3-fy2026-press-release.md:88)\n"
        "- Blackwell and Rubin product family driving Data Center growth "
        "(source: nvidia-q3-fy2026-earnings-call-transcript.md:32)\n"
    )

    per_agent = {
        "claude": common_body
        + "- Capex: $1.85 billion "
        "(source: nvidia-q3-fy2026-press-release.md:101)\n"
        "- Inventory rose 11% QoQ "
        "(source: nvidia-q3-fy2026-press-release.md:118)\n",
        "codex": common_body
        + "- Capex: $1.85 billion (source: nvidia-q3-fy2026-investor-deck-summary.md:14)\n",
        "manus": common_body,
        "codex-web": common_body,
        "gemini": common_body,
    }

    from types import SimpleNamespace

    class _MockBridge:
        def __init__(self, name: str, text: str):
            self.cfg = SimpleNamespace(name=name)
            self._text = text

        async def send(self, prompt, *, session_id=None, extra=None):
            return self._text, None

        async def _kill(self):
            return None

    _MOCKED_RESPONSE_BY_AGENT.clear()
    bridges = []
    for name in baselines:
        text = per_agent.get(name, common_body)
        _MOCKED_RESPONSE_BY_AGENT[name] = text
        bridges.append(_MockBridge(name, text))
    return bridges


def cmd_expedition(args: argparse.Namespace) -> int:
    # ----- pre-flight: task bundle exists ------------------------------------
    repo_root = _detect_repo_root()
    bundle_path = repo_root / "tasks" / args.task / "bundle.yaml"
    if not bundle_path.is_file():
        print(
            f"ERROR: task {args.task!r} not found at {bundle_path}\n"
            f"       (looked under {repo_root / 'tasks'})",
            file=sys.stderr,
        )
        return 2

    # ----- pre-flight: API keys present when judge is live (not mocked) ------
    if not args.mocked:
        missing = _missing_required_env(args.baselines, args.judge)
        if missing:
            print(
                f"ERROR: required env var(s) not set: {', '.join(missing)}\n"
                f"       Re-run with --mocked for offline acceptance gate, "
                f"or export the keys above.",
                file=sys.stderr,
            )
            return 3

    try:
        return asyncio.run(_run_expedition(args))
    except FileNotFoundError as e:
        print(f"EXPEDITION_ERROR: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"EXPEDITION_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


def _missing_required_env(baselines_csv: str, judge_llm: str) -> list[str]:
    """Return required env vars not set in os.environ.

    - Soft Oracle requires ANTHROPIC_API_KEY for live Anthropic SDK call
      (claude-* models). When the judge_llm starts with "claude-" we require
      ANTHROPIC_API_KEY; "gpt-"/"o1-" → OPENAI_API_KEY.
    - Subscription bridges (claude/codex/manus) authenticate through their
      respective CLIs' own auth, NOT env vars — so we don't gate on those.
    """
    needed: list[str] = []
    if judge_llm.startswith("claude-") and not os.environ.get("ANTHROPIC_API_KEY"):
        needed.append("ANTHROPIC_API_KEY")
    elif judge_llm.startswith(("gpt-", "o1-", "o3-", "o4-")) and not os.environ.get("OPENAI_API_KEY"):
        needed.append("OPENAI_API_KEY")
    return needed


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="adx",
        description="agentdex-cli — async co-opetition orchestrator over subscription baselines",
    )
    subs = p.add_subparsers(dest="cmd", required=True)

    bridge = subs.add_parser("bridge", help="bridge ops (probe, run, ...)")
    bridge_subs = bridge.add_subparsers(dest="bridge_cmd", required=True)

    probe = bridge_subs.add_parser(
        "probe",
        help="One-turn probe through a baseline bridge with a task's first source file.",
    )
    probe.add_argument("--bridge", required=True,
                       choices=["claude", "codex", "manus", "codex-web", "gemini"])
    probe.add_argument("--task", required=True, help="task id under tasks/<id>/")
    probe.add_argument("--timeout", default="60", help="seconds (default 60)")
    probe.set_defaults(func=cmd_bridge_probe)

    expedition = subs.add_parser(
        "expedition",
        help="Run a full M5 Expedition: 3 baselines → 3 ResultCards + Pareto + EvolutionCard.",
    )
    expedition.add_argument("--task", required=True, help="task id under tasks/<id>/")
    expedition.add_argument(
        "--baselines",
        default="claude,codex,manus",
        help="comma-separated bridge names (default: claude,codex,manus)",
    )
    expedition.add_argument(
        "--judge",
        default="claude-haiku-4.5",
        help="judge LLM model id (default: claude-haiku-4.5)",
    )
    expedition.add_argument(
        "--output",
        required=True,
        help="output directory under expeditions/<id>/",
    )
    expedition.add_argument(
        "--mocked",
        action="store_true",
        help="use recorded mock bridges (skip live subscription CLIs)",
    )
    expedition.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="per-baseline timeout in seconds (default 120)",
    )
    expedition.add_argument(
        "--kaos-db",
        default="kaos.db",
        help="path to KAOS sqlite DB for lineage persistence (default kaos.db)",
    )
    expedition.set_defaults(func=cmd_expedition)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
