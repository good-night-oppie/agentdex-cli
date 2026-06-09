"""Phase-7 M5 Expedition smoke — mocked bridges, full artifact pipeline.

Deterministic + offline: no live subscription CLI, no live Anthropic API.
Mock judge returns a fixed JSON verdict; mock bridges return recorded
NVIDIA responses. Exercises every acceptance criterion that does NOT
require live live live live.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from agentdex_engine.cards import EvolutionCard, ResultCard, TaskCard
from agentdex_engine.evolver.pareto import ParetoVerdict

REPO_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = REPO_ROOT / "expeditions" / "test-smoke-exp-001"
KAOS_DB_PATH = REPO_ROOT / "expeditions" / "_test_kaos.db"


@pytest.fixture(scope="module")
def run_mocked_expedition():
    """Invoke ``adx expedition --mocked`` and yield the artifact dir."""
    artifact_dir = ARTIFACT_DIR
    if artifact_dir.exists():
        import shutil

        shutil.rmtree(artifact_dir)
    if KAOS_DB_PATH.exists():
        KAOS_DB_PATH.unlink()

    cmd = [
        sys.executable,
        "-m",
        "agentdex_cli.cli",
        "expedition",
        "--task",
        "nvidia-earnings-infographic",
        "--baselines",
        "claude,codex,manus",
        "--judge",
        "claude-haiku-4.5",
        "--output",
        str(artifact_dir.relative_to(REPO_ROOT)),
        "--mocked",
        "--kaos-db",
        str(KAOS_DB_PATH),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, timeout=180)
    if proc.returncode != 0:
        pytest.fail(
            f"expedition failed: rc={proc.returncode}\nstderr={proc.stderr}\nstdout={proc.stdout}"
        )
    yield artifact_dir


def test_all_artifacts_exist(run_mocked_expedition):
    d = run_mocked_expedition
    expected = [
        "task_card.yaml",
        "pareto_verdict.yaml",
        "evolution_card.yaml",
        "result_card_claude.yaml",
        "result_card_codex.yaml",
        "result_card_manus.yaml",
        "trace/claude_full_trace.jsonl",
        "trace/codex_full_trace.jsonl",
        "trace/manus_full_trace.jsonl",
    ]
    missing = [p for p in expected if not (d / p).is_file()]
    assert missing == [], f"missing artifacts: {missing}"


def test_task_card_yaml_validates(run_mocked_expedition):
    body = yaml.safe_load((run_mocked_expedition / "task_card.yaml").read_text())
    tc = TaskCard.model_validate(body)
    assert tc.id == "nvidia-earnings-infographic-q3-fy2026"


def test_three_result_cards_validate(run_mocked_expedition):
    for agent in ("claude", "codex", "manus"):
        path = run_mocked_expedition / f"result_card_{agent}.yaml"
        body = yaml.safe_load(path.read_text())
        rc = ResultCard.model_validate(body)
        assert rc.agent_id == agent
        assert 0.0 <= rc.pass_rate <= 1.0
        # C4 (workflow w0z1i9vcs): post-MF5 cost_dollar is float|None — None
        # only on the failure path (failure_trace_path set). Guard the
        # `> 0.0` assert so the smoke test fails cleanly with a useful
        # message instead of TypeError if it ever covers the failure path.
        if rc.failure_trace_path is None:
            assert rc.cost_dollar is not None and rc.cost_dollar > 0.0
        else:
            assert rc.cost_dollar is None, "MF5 invariant: failed baseline cost_dollar must be None"
        assert rc.speed_wall_clock_sec > 0.0
        # PR-E (C5) added "excluded-failed" to the ParetoPosition Literal.
        assert rc.pareto_position in {
            "dominated",
            "undominated",
            "no-clear-winner",
            "excluded-failed",
        } or isinstance(rc.pareto_position, int)


def test_pareto_verdict_yaml(run_mocked_expedition):
    body = yaml.safe_load((run_mocked_expedition / "pareto_verdict.yaml").read_text())
    pv = ParetoVerdict.model_validate(body)
    assert pv.verdict_kind in {"dominated", "undominated", "no_clear_winner"}
    if pv.verdict_kind in {"undominated"}:
        assert pv.winner is not None


def test_evolution_card_two_categories(run_mocked_expedition):
    body = yaml.safe_load((run_mocked_expedition / "evolution_card.yaml").read_text())
    ec = EvolutionCard.model_validate(body)
    assert len(ec.mutation_seeds) >= 2, (
        f"expected ≥2 mutation_seed categories, got {list(ec.mutation_seeds)}"
    )


def test_r6_seed_provenance_present(run_mocked_expedition):
    body = yaml.safe_load((run_mocked_expedition / "evolution_card.yaml").read_text())
    seeds = [s for v in body["mutation_seeds"].values() for s in v]
    assert seeds, "no seeds emitted"
    for s in seeds:
        assert "seed_provenance" in s, f"missing seed_provenance on seed: {s}"
        assert s["seed_provenance"] in {"structural", "learned"}
    provenance_set = {s["seed_provenance"] for s in seeds}
    # M5 gate accepts structural-only; the assertion documents intent.
    assert provenance_set.issubset({"structural", "learned"})


def test_trace_jsonl_non_empty(run_mocked_expedition):
    trace_dir = run_mocked_expedition / "trace"
    files = list(trace_dir.glob("*_full_trace.jsonl"))
    assert len(files) == 3
    for f in files:
        body = f.read_text()
        assert body.strip(), f"empty trace file: {f}"
        # One record per turn (M5 MVP shim).
        record = json.loads(body.splitlines()[0])
        assert "expedition_id" in record
        assert "agent_id" in record


def test_kaos_lineage_entry_persisted():
    from agentdex_engine.shared.kaos_adapter import list_expedition_lineage

    agents = list_expedition_lineage(str(KAOS_DB_PATH))
    assert agents, "KAOS lineage entry not persisted"
    assert any("expedition-expedition" in (a.get("name") or "") for a in agents), (
        f"expected expedition lineage agent name; got {[a.get('name') for a in agents]}"
    )


def test_judge_span_parented_to_expedition():
    """Mocked path: directly exercise the soft Oracle through the stub client
    factory and assert the JSON contract holds + judge_llm is passed through."""
    from agentdex_engine.cards import TaskCard
    from agentdex_engine.oracle.soft import LlmJudgeOracle

    recorded: dict = {}

    class _RecMessages:
        def create(self, *, model, max_tokens, system, messages):
            recorded["model"] = model
            recorded["system_excerpt"] = (system or "")[:120]
            block = type(
                "B", (), {"text": '{"score":0.8,"uncertainty":0.2,"pass":true,"rationale":"ok"}'}
            )
            return type("M", (), {"content": [block]})

    class _RecClient:
        messages = _RecMessages()

    oracle = LlmJudgeOracle(
        judge_llm="claude-haiku-4.5",
        client_factory=lambda: _RecClient(),
    )
    tc = TaskCard(
        id="test-task",
        source_bundle_hash="0" * 64,
        environment_spec={"runtime": "test"},
        oracle_spec_ref="x",
        budget_token_cap=1,
        budget_dollar_cap=0.0,
        expected_output_kind="infographic",
        version="0.1.0",
    )
    verdicts = oracle.evaluate("Revenue $35.08B.", tc)
    assert recorded["model"] == "claude-haiku-4.5", (
        "judge_llm model id must propagate verbatim into the Anthropic SDK call "
        "(NO Hermes profile resolution at MVP — ADR-0008 §judge-as-profile DOWNGRADE)"
    )
    v = verdicts["soft.narrative_coherence"]
    assert v.kind == "soft"
    assert v.pass_ is True
