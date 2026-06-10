"""Hermes tool — ``agentdex_run_expedition``.

Wraps the M5 sync-wrapper chain (``agentdex_cli.cli._run_expedition`` →
``run_expedition_orchestrator`` + ``log_expedition_lineage``) as an async
Hermes tool handler so ``hermes chat -t agentdex --yolo`` can drive a full
Expedition autonomously (HANDOFF.md phase-9 PR-B).

Design choice: delegate to the CLI's ``_run_expedition`` instead of
re-implementing the orchestrator chain. The CLI path is the load-bearing
M5 surface (IDEAL_EXPERIENCE.md §2.0) — duplicating its ~100 lines here
would fork fairness-gate / trace-emit / lineage behavior the moment either
copy drifts. The tool builds the same ``argparse.Namespace`` the CLI parser
would, awaits the coroutine, then reads back the YAML artifacts the run
wrote to ``output_dir``.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from pathlib import Path
from typing import Any

AGENTDEX_RUN_EXPEDITION_SCHEMA = {
    "name": "agentdex_run_expedition",
    "description": (
        "Run a full agentdex Expedition: baseline CLIs (claude/codex/manus) "
        "tackle the same frozen TaskCard, judged by a soft-Oracle LLM, "
        "producing per-baseline ResultCards + a Pareto verdict + an "
        "EvolutionCard with mutation seeds. Set mocked=true for the offline "
        "deterministic path (recorded bridges + mock judge)."
    ),
    "parameters": {
        "type": "object",
        "required": ["task"],
        "properties": {
            "task": {
                "type": "string",
                "description": "task id under tasks/<id>/ (e.g. nvidia-earnings-infographic)",
            },
            "baselines": {
                "type": "array",
                "items": {"type": "string"},
                "default": ["claude", "codex", "manus"],
            },
            "judge": {"type": "string", "default": "claude-haiku-4-5"},
            "output_dir": {
                "type": "string",
                "description": "artifact dir; defaults to expeditions/plugin-<task>-<rand8>/",
            },
            "mocked": {"type": "boolean", "default": False},
            "timeout_sec": {
                "type": "integer",
                "default": 120,
                "description": "per-baseline timeout seconds",
            },
            "kaos_db": {"type": "string", "default": "kaos.db"},
        },
    },
}


def _read_yaml(path: Path) -> Any:
    import yaml

    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


async def handle_run_expedition(args: dict) -> dict:
    """Async Hermes handler. Returns the full Three-Cards artifact bundle."""
    from agentdex_cli.cli import _detect_repo_root, _missing_required_env, _run_expedition

    task = args["task"]
    baselines = list(args.get("baselines") or ["claude", "codex", "manus"])
    mocked = bool(args.get("mocked", False))
    baselines_csv = ",".join(baselines)

    if not mocked:
        missing = _missing_required_env(baselines_csv, args.get("judge", "claude-haiku-4-5"))
        if missing:
            return {
                "ok": False,
                "error": f"required env var(s) not set: {', '.join(missing)}",
                "hint": "re-run with mocked=true for the offline path, or export the keys",
            }

    output_dir = args.get("output_dir") or f"expeditions/plugin-{task}-{uuid.uuid4().hex[:8]}"
    ns = argparse.Namespace(
        task=task,
        baselines=baselines_csv,
        judge=args.get("judge", "claude-haiku-4-5"),
        output=output_dir,
        mocked=mocked,
        timeout=int(args.get("timeout_sec", 120)),
        kaos_db=args.get("kaos_db", "kaos.db"),
        no_langfuse=True,  # host process owns observability init, not the tool
        fairness_tolerance=int(args.get("fairness_tolerance", 5)),
    )

    rc = await _run_expedition(ns)

    repo_root = _detect_repo_root()
    out = Path(output_dir)
    if not out.is_absolute():
        out = repo_root / out

    if rc != 0:
        fairness = out / "fairness_report.yaml"
        return {
            "ok": False,
            "error": f"expedition exited rc={rc}",
            "expedition_dir": str(out),
            "fairness_report": _read_yaml(fairness) if fairness.exists() else None,
        }

    evolution = _read_yaml(out / "evolution_card.yaml")
    result_cards = [_read_yaml(p) for p in sorted(out.glob("result_card_*.yaml"))]
    return {
        "ok": True,
        "expedition_id": (evolution or {}).get("expedition_id"),
        "expedition_dir": str(out),
        "task_card": _read_yaml(out / "task_card.yaml"),
        "result_cards": result_cards,
        "pareto_verdict": _read_yaml(out / "pareto_verdict.yaml"),
        "evolution_card": evolution,
        "langfuse_trace_urls": (evolution or {}).get("langfuse_trace_urls", []),
    }


def handle_run_expedition_sync(args: dict) -> dict:
    """Sync fallback for hosts that don't honor ``is_async=True``."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(handle_run_expedition(args))
    raise RuntimeError(
        "handle_run_expedition_sync called inside a running event loop; "
        "register with is_async=True and call handle_run_expedition instead"
    )


__all__ = [
    "AGENTDEX_RUN_EXPEDITION_SCHEMA",
    "handle_run_expedition",
    "handle_run_expedition_sync",
]
