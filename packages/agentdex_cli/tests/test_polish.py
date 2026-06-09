"""Phase-8 polish tests — error-case CLI handling + partial baseline failure."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[3]


def _adx_cmd(*args: str) -> list[str]:
    return [sys.executable, "-m", "agentdex_cli.cli", *args]


def test_missing_task_bundle_exits_2():
    proc = subprocess.run(
        _adx_cmd(
            "expedition",
            "--task",
            "nonexistent-task",
            "--baselines",
            "claude",
            "--output",
            "expeditions/_should_not_exist/",
            "--mocked",
        ),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=30,
    )
    assert proc.returncode == 2, f"expected exit 2, got {proc.returncode}; stderr={proc.stderr}"
    assert "task 'nonexistent-task' not found" in proc.stderr, (
        f"expected helpful stderr; got {proc.stderr!r}"
    )


def test_missing_api_key_exits_3():
    """Live (non-mocked) path with judge=claude-haiku-4.5 + ANTHROPIC_API_KEY unset → exit 3.

    Also strip CLIPROXY_BASE_URL / CLIPROXY_API_KEY because cli.py's
    `_missing_required_env` short-circuits to "no missing keys" when the pool
    is wired (cli.py:422-423). A developer shell with CLIPROXY env exported
    used to make this assertion non-deterministic.
    """
    env = os.environ.copy()
    for k in ("ANTHROPIC_API_KEY", "CLIPROXY_BASE_URL", "CLIPROXY_API_KEY"):
        env.pop(k, None)
    proc = subprocess.run(
        _adx_cmd(
            "expedition",
            "--task",
            "nvidia-earnings-infographic",
            "--baselines",
            "claude",
            "--judge",
            "claude-haiku-4.5",
            "--output",
            "expeditions/_should_not_exist/",
        ),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=30,
        env=env,
    )
    assert proc.returncode == 3, f"expected exit 3, got {proc.returncode}; stderr={proc.stderr}"
    assert "ANTHROPIC_API_KEY" in proc.stderr


def test_partial_baseline_failure_continues_with_other_baselines():
    """One bridge throws → expedition completes w/ degraded ResultCard for that baseline."""
    from agentdex_engine.cards import TaskCard
    from agentdex_engine.expedition import run_expedition_orchestrator
    from agentdex_engine.oracle.base import OracleVerdict

    class _OkBridge:
        def __init__(self, name):
            self.cfg = SimpleNamespace(name=name)

        async def send(self, prompt, *, session_id=None, extra=None):
            from adx_bridges import BridgeResponse

            return BridgeResponse(
                text="Revenue $35.08B, gross margin 74.6%.",
                langfuse_trace_id=None,
                cost_usd=None,
                tokens=None,
            )

    class _ExplodingBridge:
        def __init__(self, name):
            self.cfg = SimpleNamespace(name=name)

        async def send(self, prompt, *, session_id=None, extra=None):
            raise RuntimeError("simulated bridge crash")

    class _StubOracle:
        def evaluate(self, response, task_card):
            return {
                "hard.revenue": OracleVerdict(
                    kind="hard",
                    **{"pass": "revenue" in response.lower()},
                    score=1.0 if "revenue" in response.lower() else 0.0,
                    evidence="stub",
                ),
            }

    task_card = TaskCard(
        id="nvidia-earnings-infographic-q3-fy2026",
        source_bundle_hash="2f3bf8fee53690f76e4701a5097aabb3e19f5bb146a136fe95a2b8d7169c3346",  # pragma: allowlist secret
        environment_spec={"runtime": "test"},
        oracle_spec_ref="dummy.yaml",
        budget_token_cap=1000,
        budget_dollar_cap=1.0,
        expected_output_kind="infographic",
        version="0.1.0",
    )

    bridges = [_OkBridge("claude"), _ExplodingBridge("codex"), _OkBridge("manus")]
    result_cards, verdict, evolution_card, fairness_report = asyncio.run(
        run_expedition_orchestrator(
            task_card,
            bridges,
            _StubOracle(),
            judge_llm="claude-haiku-4.5",
            prompt_override="dummy",
        )
    )
    assert fairness_report is None, "no manifests passed → no fairness report"
    assert len(result_cards) == 3, "all 3 ResultCards present even on partial failure"
    by_id = {rc.agent_id: rc for rc in result_cards}
    assert by_id["claude"].pass_rate == 1.0
    assert by_id["manus"].pass_rate == 1.0
    assert by_id["codex"].pass_rate == 0.0
    assert by_id["codex"].failure_trace_path is not None
    assert "RuntimeError" in by_id["codex"].failure_trace_path
    assert "simulated bridge crash" in by_id["codex"].failure_trace_path
    # C5 regression (workflow w0z1i9vcs): the crashed baseline must be
    # labeled `excluded-failed`, not `dominated` — pareto_verdict never
    # compared it, it was just skipped.
    assert by_id["codex"].pareto_position == "excluded-failed", (
        f"failed baseline must be labeled excluded-failed; got {by_id['codex'].pareto_position!r}"
    )
    assert by_id["codex"].cost_dollar is None, "MF5 invariant: failed baseline cost_dollar is None"


def test_security_no_hardcoded_api_keys():
    """Repo security scan: no `sk-<20+chars>` literal in packages/ or tasks/."""
    import re

    pattern = re.compile(rb"sk-[a-zA-Z0-9]{20,}")
    suspect: list[str] = []
    for root in ("packages", "tasks"):
        for path in (REPO_ROOT / root).rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".yaml", ".yml", ".md", ".toml"}:
                continue
            if "/tests/" in str(path) or "fixture" in path.name.lower():
                continue
            if "/.venv/" in str(path) or "/__pycache__/" in str(path):
                continue
            try:
                blob = path.read_bytes()
            except OSError:
                continue
            if pattern.search(blob):
                suspect.append(str(path.relative_to(REPO_ROOT)))
    assert suspect == [], f"hard-coded secrets found: {suspect}"


def test_claude_md_has_six_doctrine_sections():
    body = (REPO_ROOT / "CLAUDE.md").read_text()
    required_h2 = [
        "## Why agentdex-cli is the Hermes retrofit",
        "## Why KAOS lives at `packages/kaos/`, not pip install",
        "## Why helios stays external",
        "## Why `~/gh/agentdex/` was archived",
        "## Two-tier substrate",
        "## Context-window discipline",
    ]
    missing = [h for h in required_h2 if h not in body]
    assert missing == [], f"missing H2 sections in CLAUDE.md: {missing}"


def test_readme_quickstart_section():
    body = (REPO_ROOT / "README.md").read_text()
    assert "## Quickstart" in body
    assert "uv run adx expedition" in body
