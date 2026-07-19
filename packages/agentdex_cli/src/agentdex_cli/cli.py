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
import shutil
import sys
from pathlib import Path

REPO_ROOT_ENV = "AGENTDEX_REPO_ROOT"


def _detect_repo_root() -> Path:
    if env := os.environ.get(REPO_ROOT_ENV):
        return Path(env)
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "tasks").is_dir() and (parent / "packages").is_dir():
            return parent
    return Path.cwd()


def _first_source_file(task_id: str, root: Path) -> Path | None:
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


async def _run_probe(
    bridge_name: str, task_id: str, *, timeout: float
) -> tuple[str, str | None, str]:
    """Returns ``(text, trace_id, used_bridge_name)``."""
    from adx_bridges import build_bridge

    root = _detect_repo_root()
    prompt = _load_prompt_for_task(task_id, root)
    bridge = build_bridge(bridge_name, workdir=str(root))
    try:
        coro = bridge.send(prompt, extra={"max_turns": 1})
        resp = await asyncio.wait_for(coro, timeout=timeout)
        return resp.text, resp.langfuse_trace_id, bridge.cfg.name
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
    """Per-bridge trace EXCERPT — a single summary record (metrics + a truncated
    response excerpt + the langfuse_trace_id pointer), NOT a full span tree.

    The full Langfuse-exported span tree is an M6+ target and is not yet wired;
    until then this file is named ``*_trace_excerpt.jsonl`` so the artifact's name
    matches its contents (truth-in-advertising; agentdex-cli audit P1).
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
    oracle_chain = _build_default_oracle_chain(args.task, repo_root, args.judge, mocked=args.mocked)

    baselines = [b.strip() for b in args.baselines.split(",") if b.strip()]
    if args.mocked:
        bridges = _make_mock_bridges(baselines, args.task, repo_root)
    else:
        bridges = _instantiate_bridges(baselines, str(repo_root))

    # ----- pre-Expedition manifests + fairness gate -----
    from agentdex_engine.manifest import stock_manifest

    manifests = [stock_manifest(name) for name in baselines]

    output_dir = (
        (repo_root / args.output) if not Path(args.output).is_absolute() else Path(args.output)
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    def _on_fairness(report):
        _write_yaml(output_dir / "fairness_report.yaml", report.model_dump())
        print(
            f"fairness: overall={report.fairness_verdict} "
            f"(process={report.process.verdict} "
            f"resource={report.resource.verdict} "
            f"procedure={report.procedure.verdict})"
        )
        print(
            f"  envelope: ctx={report.balanced_constraints.context_window_tokens} "
            f"out={report.balanced_constraints.max_output_tokens} "
            f"tools={report.balanced_constraints.tool_allowlist[:5]}"
        )
        print(
            f"  resource_ratios: cost={report.resource.cost_ratio_max:.2f}x "
            f"ctx={report.resource.context_ratio_max:.2f}x "
            f"out={report.resource.output_ratio_max:.2f}x"
        )
        for note in report.advisory_notes:
            print(f"  advisory: {note}")

    try:
        result_cards, verdict, evolution_card, fairness_report = await asyncio.wait_for(
            run_expedition_orchestrator(
                task_card,
                bridges,
                oracle_chain,
                args.judge,
                repo_root=repo_root,
                manifests=manifests,
                fairness_tolerance=args.fairness_tolerance,
                on_fairness_report=_on_fairness,
            ),
            timeout=args.timeout * max(len(bridges), 1),
        )
    finally:
        for b in bridges:
            try:
                await b._kill()  # type: ignore[attr-defined]
            except Exception:
                pass

    if fairness_report is not None and fairness_report.fairness_verdict == "fail":
        print(
            f"\nEXPEDITION BLOCKED by 3-tier fairness gate.\n"
            f"  process:   {fairness_report.process.verdict}\n"
            f"  resource:  {fairness_report.resource.verdict}\n"
            f"  procedure: {fairness_report.procedure.verdict}\n"
            f"See fairness_report.yaml for advisories.",
            file=sys.stderr,
        )
        return 4

    trace_dir = output_dir / "trace"
    trace_dir.mkdir(exist_ok=True)
    # Remove pre-rename artifacts so a re-run into an existing dir does not leave
    # stale *_full_trace.jsonl alongside the *_trace_excerpt.jsonl this run writes
    # (the legacy name overstated the contents; PR #163 review #3423352058).
    for _legacy in trace_dir.glob("*_full_trace.jsonl"):
        _legacy.unlink()

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
            trace_dir / f"{agent_slug}_trace_excerpt.jsonl",
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
        "claude": common_body + "- Capex: $1.85 billion "
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
            from adx_bridges import BridgeResponse

            return BridgeResponse(
                text=self._text, langfuse_trace_id=None, cost_usd=None, tokens=None
            )

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
    if judge_llm.lower().startswith(("claude-code", "claude_code", "codex-exec", "codex_exec")):
        # Subscription-CLI routed; no API key needed.
        return []
    if os.environ.get("CLIPROXY_BASE_URL") and os.environ.get("CLIPROXY_API_KEY"):
        # LLM pool active; pool handles auth.
        return []
    if judge_llm.startswith("claude-") and not os.environ.get("ANTHROPIC_API_KEY"):
        needed.append("ANTHROPIC_API_KEY")
    elif judge_llm.startswith(("gpt-", "o1-", "o3-", "o4-")) and not os.environ.get(
        "OPENAI_API_KEY"
    ):
        needed.append("OPENAI_API_KEY")
    elif judge_llm.startswith("gemini-"):
        has_api = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        has_cli = shutil.which(os.environ.get("ANTIGRAVITY_BIN", "antigravity"))
        if not (has_api or has_cli):
            needed.append("GEMINI_API_KEY (or install `antigravity` CLI)")
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
    probe.add_argument(
        "--bridge", required=True, choices=["claude", "codex", "manus", "codex-web", "gemini"]
    )
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
        default="claude-haiku-4-5",
        help=(
            "judge LLM model id (default: claude-haiku-4-5 — matches "
            "tasks/nvidia-earnings-infographic/oracle/spec.yaml:judge_llm). "
            "Prior default `gemini-3.5-flash` is NOT a real Gemini model id "
            "and produced 502 'unknown provider' from CLIProxyAPI on every "
            "live expedition; PR #12 swaps to the spec-anchored Claude model."
        ),
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
    expedition.add_argument(
        "--no-langfuse",
        action="store_true",
        help="skip langfuse_stack.ensure() pre-flight (use existing env / no traces)",
    )
    expedition.add_argument(
        "--fairness-tolerance",
        type=int,
        default=5,
        help="max special-capability drop allowed before blocking the expedition "
        "(default 5). 0 = strict equality required.",
    )
    expedition.set_defaults(func=cmd_expedition)

    langfuse = subs.add_parser(
        "langfuse",
        help="Langfuse self-host lifecycle (scoped to Expedition window per ADR-0009).",
    )
    lf_subs = langfuse.add_subparsers(dest="langfuse_cmd", required=True)

    lf_up = lf_subs.add_parser("up", help="docker compose up the bundled Langfuse stack")
    lf_up.add_argument("--wait", type=int, default=180, help="max seconds to wait for healthy")
    lf_up.set_defaults(func=cmd_langfuse_up)

    lf_down = lf_subs.add_parser("down", help="docker compose down")
    lf_down.set_defaults(func=cmd_langfuse_down)

    lf_status = lf_subs.add_parser("status", help="probe /api/public/health + show creds path")
    lf_status.set_defaults(func=cmd_langfuse_status)

    lf_ensure = lf_subs.add_parser(
        "ensure",
        help="status; if down, up; wait healthy; export creds. Idempotent.",
    )
    lf_ensure.add_argument("--wait", type=int, default=180)
    lf_ensure.set_defaults(func=cmd_langfuse_ensure)

    # ---- llm-pool: unified LLM proxy (CLIProxyAPI) lifecycle ----
    pool = subs.add_parser(
        "llm-pool",
        help="Unified LLM proxy (CLIProxyAPI) — setup once, use everywhere.",
    )
    pool_subs = pool.add_subparsers(dest="pool_cmd", required=True)

    p_status = pool_subs.add_parser("status", help="show pool mode + base URL + key path")
    p_status.set_defaults(func=cmd_pool_status)

    p_verify = pool_subs.add_parser(
        "verify",
        help="run a small probe against one model: `adx llm-pool verify --model claude-haiku-4-5`",
    )
    p_verify.add_argument("--model", default="claude-haiku-4-5")
    p_verify.add_argument("--prompt", default="Reply with exactly: POOL_OK")
    p_verify.set_defaults(func=cmd_pool_verify)

    p_setenv = pool_subs.add_parser(
        "set-env",
        help="write ~/.adx/llm_pool.env (creates parent dirs)",
    )
    p_setenv.add_argument("--base-url", default="http://localhost:8118/v1")
    p_setenv.add_argument("--api-key", default="cliproxy-no-key")
    p_setenv.add_argument(
        "--mode",
        choices=["cliproxy", "direct", "hybrid"],
        default="hybrid",
    )
    p_setenv.set_defaults(func=cmd_pool_set_env)

    # ---- deploy: deploy entrypoint ----
    deploy = subs.add_parser(
        "deploy",
        help="Deploy the FastAPI service to the AI Builder platform",
    )
    deploy.add_argument(
        "--service-name",
        default="agentdex",
        help="Unique subdomain (default: agentdex)",
    )
    deploy.add_argument(
        "--repo-url",
        help="Public Git repository URL (auto-detected if not specified)",
    )
    deploy.add_argument(
        "--branch",
        help="Git branch to deploy (auto-detected if not specified)",
    )

    deploy.add_argument(
        "--env-vars",
        help="Comma-separated KEY=VALUE env vars",
    )
    deploy.add_argument(
        "--token",
        help="AI Builder API token (defaults to AI_BUILDER_TOKEN env var)",
    )
    deploy.add_argument(
        "--no-poll",
        action="store_true",
        help="Queue the deployment and exit without polling status",
    )
    deploy.add_argument(
        "--poll-interval",
        type=int,
        default=10,
        help="Status polling interval in seconds (default: 10)",
    )
    deploy.add_argument(
        "--poll-timeout",
        type=int,
        default=600,
        help="Status polling timeout in seconds (default: 600)",
    )
    deploy.set_defaults(func=cmd_deploy)

    # ---- arena: intentionally deferred (route to starter kit / MCP) ----
    # The arena surface (enroll / battle / evolution) is driven through the
    # starter kit or the MCP endpoint, NOT the adx package — wiring it here
    # would pull the arena client's httpx/cryptography/PoP-signing deps into
    # the orchestrator CLI for no MVP benefit. The stub exists so a visiting
    # agent typing `adx arena ...` gets actionable routing instead of a bare
    # argparse "invalid choice" error. REMAINDER swallows any sub-args so
    # `adx arena play`, `adx arena enroll --foo`, etc. all land cleanly.
    arena = subs.add_parser(
        "arena",
        help="(deferred) arena enroll/battle/evolution — use the starter kit or MCP surface",
    )
    arena.add_argument(
        "arena_args",
        nargs=argparse.REMAINDER,
        help="ignored; any `adx arena ...` invocation prints how to reach the arena",
    )
    arena.set_defaults(func=cmd_arena_defer)

    # ---- measure: AgentCandidate × ladder → MeasureResult JSON (M2 WU-5) ----
    from agentdex_cli.measure_cmd import register_measure_parser

    register_measure_parser(subs)

    # ---- evolve: Weco starts Claude; AgentDex supplies RSI contract ----
    from agentdex_cli.evolve_cmd import register_evolve_parser

    register_evolve_parser(subs)

    # ---- evolve-submit: measure JSON → Bene collaborative bridge → frontier.json ----
    from agentdex_cli.evolve_submit_cmd import register_evolve_submit_parser

    register_evolve_submit_parser(subs)

    # ---- interview: capture orchestration policy → .agentdex/orchestration.yaml ----
    from agentdex_cli.interview_cmd import register_interview_parser

    register_interview_parser(subs)

    # ---- run: allocate a task across the pool, gate, learn a seed ----
    from agentdex_cli.run_cmd import register_run_parser

    register_run_parser(subs)

    # ---- openbox: bind pool names to invokable backends (zero creds) ----
    from agentdex_cli.openbox_cmd import register_openbox_parser

    register_openbox_parser(subs)

    return p


def cmd_langfuse_status(args: argparse.Namespace) -> int:
    from agentdex_observe import langfuse_stack

    h = langfuse_stack.status()
    print(f"host: {h.host}")
    print(f"healthy: {h.healthy}")
    print(f"public_key: {'set' if h.public_key else '<unset>'}")
    print(f"secret_key: {'set' if h.secret_key else '<unset>'}")
    print("creds_file: ~/.adx/langfuse.env")
    return 0 if h.healthy else 1


def cmd_langfuse_up(args: argparse.Namespace) -> int:
    from agentdex_observe import langfuse_stack

    try:
        h = langfuse_stack.up(max_wait_seconds=args.wait)
    except Exception as e:
        print(f"LANGFUSE_UP_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(f"host: {h.host}  healthy={h.healthy}")
    if not (h.public_key and h.secret_key):
        print(
            "\nNEXT STEPS (first-run seed):\n"
            "  1. open http://localhost:3000 in browser\n"
            "  2. create org + project\n"
            "  3. Settings → API Keys → Create new keys\n"
            "  4. paste into ~/.adx/langfuse.env (template already created)\n"
            "  5. re-run `adx expedition`"
        )
    return 0 if h.healthy else 3


def cmd_langfuse_down(args: argparse.Namespace) -> int:
    from agentdex_observe import langfuse_stack

    langfuse_stack.down()
    print("langfuse stack: down")
    return 0


def cmd_pool_status(args: argparse.Namespace) -> int:
    from agentdex_observe.llm_pool import ensure_pool_env

    env = ensure_pool_env()
    print(f"mode:        {os.environ.get('ADX_LLM_POOL_MODE', 'hybrid')}")
    print(f"base_url:    {os.environ.get('CLIPROXY_BASE_URL', '<unset>')}")
    print(f"api_key:     {'set' if os.environ.get('CLIPROXY_API_KEY') else '<unset>'}")
    print(f"env_file:    ~/.adx/llm_pool.env  ({'present' if env else 'MISSING'})")
    return 0


def cmd_pool_verify(args: argparse.Namespace) -> int:
    from agentdex_observe.llm_pool import client_for, ensure_pool_env

    ensure_pool_env()
    try:
        client = client_for(args.model)
    except Exception as e:
        print(f"POOL_RESOLVE_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    try:
        if hasattr(client, "models") and hasattr(client.models, "generate_content"):
            resp = client.models.generate_content(model=args.model, contents=args.prompt)
            text = getattr(resp, "text", str(resp))
        else:
            msg = client.messages.create(
                model=args.model,
                max_tokens=120,
                system="Reply terse.",
                messages=[{"role": "user", "content": args.prompt}],
            )
            text = msg.content[0].text if hasattr(msg, "content") else str(msg)
        print(f"--- pool verify: {args.model} ---")
        print((text or "<empty>")[:500])
        return 0 if text else 1
    except Exception as e:
        print(f"POOL_INVOKE_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 3


def cmd_pool_set_env(args: argparse.Namespace) -> int:
    path = Path(os.path.expanduser("~/.adx/llm_pool.env"))
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "# adx LLM pool — managed by `adx llm-pool set-env`\n"
        f"ADX_LLM_POOL_MODE={args.mode}\n"
        f"CLIPROXY_BASE_URL={args.base_url}\n"
        f"CLIPROXY_API_KEY={args.api_key}\n"
    )
    path.write_text(body, encoding="utf-8")
    print(f"wrote {path}")
    print(body, end="")
    return 0


def cmd_deploy(args: argparse.Namespace) -> int:
    import subprocess
    import time

    import httpx

    # Determine token
    token = args.token or os.environ.get("AI_BUILDER_TOKEN")
    if not token:
        token = os.environ.get("AI_BUILDERS_KEY")
    if not token:
        print(
            "ERROR: AI_BUILDER_TOKEN (or AI_BUILDERS_KEY) not set in environment or passed via --token.",
            file=sys.stderr,
        )
        return 1

    # Base URL
    base_url = os.environ.get(
        "ADX_BUILDER_PROXY_URL", "https://space.ai-builders.com/backend/v1"
    ).rstrip("/")

    # Detect repo_url
    repo_url = args.repo_url
    if not repo_url:
        try:
            repo_url = subprocess.check_output(
                ["git", "config", "--get", "remote.origin.url"], text=True
            ).strip()
            if repo_url.startswith("git@"):
                parts = repo_url.split(":")
                if len(parts) == 2:
                    host = parts[0].split("@")[1]
                    path = parts[1]
                    if path.endswith(".git"):
                        path = path[:-4]
                    repo_url = f"https://{host}/{path}"
            elif repo_url.endswith(".git"):
                pass
        except Exception as e:
            print(
                f"ERROR: Could not auto-detect git remote origin URL ({e}). Please specify --repo-url.",
                file=sys.stderr,
            )
            return 1

    # Strip credentials from detected repo URLs (P2 PR #52 comment follow-up)
    from urllib.parse import urlparse, urlunparse

    try:
        parsed = urlparse(repo_url)
        if parsed.username or parsed.password:
            netloc = parsed.hostname
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            repo_url = urlunparse(parsed._replace(netloc=netloc))
    except Exception:
        pass

    # Detect branch
    branch = args.branch
    if not branch:
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True
            ).strip()
            # Treat detached HEAD as missing branch (P2 PR #52 comment follow-up)
            if branch == "HEAD":
                branch = "main"
        except Exception:
            branch = "main"

    # Env vars
    env_vars = {}
    # 1. Forward operator-facing config from the current environment. ARENA_*
    #    carries gateway config (signing/badge keys, max battles, owner webhook);
    #    ADX_SIDECAR_* carries the showdown sidecar scale knobs the server reads
    #    at boot — ADX_SIDECAR_POOL_SIZE (__main__.py), ADX_SIDECAR_MAX_OLD_SPACE_MB
    #    + ADX_SIDECAR_MAX_PROTOCOL_LINES/BYTES (sidecar.py). Without the second
    #    prefix a scaled deploy silently runs at the single-sidecar 96MB defaults
    #    (OPS-P1-forward-scale-envvars).
    _forward_prefixes = ("ARENA_", "ADX_SIDECAR_")
    for k, v in os.environ.items():
        if k.startswith(_forward_prefixes):
            env_vars[k] = v

    # 2. Add custom env vars from --env-vars
    if args.env_vars:
        for pair in args.env_vars.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                env_vars[k.strip()] = v.strip()
            else:
                print(
                    f"WARNING: Invalid env-var pair {pair!r}, expected KEY=VALUE. Skipping.",
                    file=sys.stderr,
                )

    # Let's do a sanity check on ARENA_SIGNING_KEY_HEX
    if "ARENA_SIGNING_KEY_HEX" not in env_vars:
        print(
            "WARNING: ARENA_SIGNING_KEY_HEX is not set in --env-vars or environment. Deployed service will generate an ephemeral key on each restart.",
            file=sys.stderr,
        )

    # Trigger deployment (unsupported port field dropped — P2 PR #52 comment follow-up)
    payload = {
        "repo_url": repo_url,
        "service_name": args.service_name,
        "branch": branch,
        "env_vars": env_vars,
    }

    print(f"Triggering deployment for service {args.service_name!r}...")
    print(f"  Repo URL: {repo_url}")
    print(f"  Branch:   {branch}")
    if env_vars:
        print(f"  Env Vars: {', '.join(f'{k}=***' for k in env_vars.keys())}")

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        resp = httpx.post(f"{base_url}/deployments", json=payload, headers=headers, timeout=120.0)
        if resp.status_code not in (200, 202):
            print(
                f"ERROR: Deployment failed to trigger. Status: {resp.status_code}", file=sys.stderr
            )
            print(resp.text, file=sys.stderr)
            return 1

        data = resp.json()
        status = data.get("status")
        message = data.get("message")
        public_url = data.get("public_url")
        print(f"Deployment queued. Status: {status}")
        print(f"Message: {message}")
        if data.get("streaming_logs"):
            print("\n--- Initial build logs ---")
            print(data.get("streaming_logs"))
            print("--------------------------\n")

        if args.no_poll:
            print("Not polling status. Check deployment status at:")
            print(f"  GET {base_url}/deployments/{args.service_name}")
            return 0

        # Start polling
        print("Polling deployment status...")
        start_time = time.time()
        last_status = None
        while time.time() - start_time < args.poll_timeout:
            poll_resp = httpx.get(
                f"{base_url}/deployments/{args.service_name}", headers=headers, timeout=30.0
            )
            if poll_resp.status_code == 200:
                poll_data = poll_resp.json()
                status = poll_data.get("status")
                message = poll_data.get("message")
                public_url = poll_data.get("public_url")

                if status != last_status:
                    print(f"[{time.strftime('%H:%M:%S')}] Status: {status} - {message}")
                    last_status = status

                if status == "HEALTHY":
                    print(f"\nSUCCESS: Service deployed successfully to: {public_url}")
                    return 0
                elif status in ("UNHEALTHY", "DEGRADED", "ERROR"):
                    print(f"\nFAILURE: Deployment failed with status: {status}")
                    # Try to fetch logs
                    try:
                        logs_resp = httpx.get(
                            f"{base_url}/deployments/{args.service_name}/logs",
                            params={"log_type": "build", "timeout": 10},
                            headers=headers,
                            timeout=30.0,
                        )
                        if logs_resp.status_code == 200:
                            print("\n--- Build Logs ---")
                            print(logs_resp.json().get("logs", ""))
                            print("-------------------\n")
                    except Exception as le:
                        print(f"Could not retrieve build logs: {le}", file=sys.stderr)
                    return 1
            else:
                print(
                    f"[{time.strftime('%H:%M:%S')}] Warning: GET /deployments/{args.service_name} returned status {poll_resp.status_code}"
                )

            time.sleep(args.poll_interval)

        print(f"\nTIMEOUT: Deployment polling timed out after {args.poll_timeout} seconds.")
        return 1

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


def cmd_langfuse_ensure(args: argparse.Namespace) -> int:
    from agentdex_observe import langfuse_stack

    try:
        h = langfuse_stack.ensure(max_wait_seconds=args.wait)
    except Exception as e:
        print(f"LANGFUSE_ENSURE_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(f"host: {h.host}  healthy={h.healthy}")
    print(
        f"creds: pk={'set' if h.public_key else '<unset>'}  sk={'set' if h.secret_key else '<unset>'}"
    )
    return 0 if h.healthy else 3


def cmd_arena_defer(args: argparse.Namespace) -> int:
    """`adx arena ...` is intentionally not implemented in the CLI (yet).

    Print actionable routing to the starter kit / MCP surface so a visiting
    agent gets a clear next step instead of a bare argparse error, then fail
    closed with rc=1 (the requested arena action did NOT run — this is a
    "not available here" signal, not a usage error, so it is 1 rather than
    argparse's 2).
    """
    print(
        "adx has no built-in 'arena' commands yet — the agentdex arena\n"
        "(enroll / battle / evolution) runs through the starter kit or MCP:\n"
        "\n"
        "  * Starter kit (HTTP):  examples/agent-starter-kit/\n"
        "      uv sync && OWNER_EMAIL=you@you.com AGENT_NAME=my-bot ./scripts/bootstrap.sh\n"
        "  * MCP surface:         https://agentdex.ai-builders.space/mcp/\n"
        "  * Agent protocol doc:  https://agentdex.ai-builders.space/skill.md\n"
        "\n"
        "See examples/agent-starter-kit/README.md for a 5-minute battle.",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    raw = sys.argv[1:] if argv is None else list(argv)
    # `adx arena ...` is intentionally deferred (routed to the starter kit / MCP).
    # Intercept it BEFORE argparse so the OPTION-first form (`adx arena --owner x`)
    # also reaches the defer stub: the subparser's nargs=REMAINDER exits 2 on a
    # leading `-` token instead of swallowing it (a known argparse quirk), which
    # re-introduced the very ADX-P2-001 footgun the stub was meant to close. There
    # are no global options before the subcommand, so the first token IS the
    # subcommand. The `arena` subparser is kept so `adx --help` still lists it.
    # PR #183 review 3426341132.
    if raw and raw[0] == "arena":
        # `adx arena play ...` IS implemented (the human terminal client); every
        # other arena verb still defers to the starter kit / MCP. Lazy import so
        # the defer path (and `adx --help`) never pulls in httpx / rich / crypto.
        if len(raw) >= 2 and raw[1] == "play":
            from agentdex_cli.arena_tui import cmd_arena_play

            return cmd_arena_play(raw[2:])
        return cmd_arena_defer(argparse.Namespace(arena_args=raw[1:]))
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
