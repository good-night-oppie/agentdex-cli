"""PR-B — agentdex_run_expedition tool, mocked offline path.

Mirrors test_expedition_smoke.py's deterministic posture: recorded mock
bridges + mock judge, no live subscription CLI, no live Anthropic API.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = REPO_ROOT / "expeditions" / "test-plugin-tool-exp-001"
KAOS_DB_PATH = REPO_ROOT / "expeditions" / "_test_plugin_kaos.db"


def test_schema_shape() -> None:
    from agentdex_plugin.tools import AGENTDEX_RUN_EXPEDITION_SCHEMA as schema

    assert schema["name"] == "agentdex_run_expedition"
    assert schema["parameters"]["required"] == ["task"]
    props = schema["parameters"]["properties"]
    assert set(props) >= {"task", "baselines", "judge", "output_dir", "mocked"}


def test_plugin_manifest_lists_tool() -> None:
    from agentdex_plugin import register

    manifest = register(None)
    assert "agentdex_run_expedition" in manifest["tools"]


@pytest.fixture(scope="module")
def mocked_result():
    if ARTIFACT_DIR.exists():
        shutil.rmtree(ARTIFACT_DIR)
    if KAOS_DB_PATH.exists():
        KAOS_DB_PATH.unlink()

    from agentdex_plugin.tools import handle_run_expedition

    result = asyncio.run(
        handle_run_expedition(
            {
                "task": "nvidia-earnings-infographic",
                "baselines": ["claude", "codex", "manus"],
                "judge": "claude-haiku-4-5",
                "output_dir": str(ARTIFACT_DIR.relative_to(REPO_ROOT)),
                "mocked": True,
                "kaos_db": str(KAOS_DB_PATH),
            }
        )
    )
    yield result
    if ARTIFACT_DIR.exists():
        shutil.rmtree(ARTIFACT_DIR)
    if KAOS_DB_PATH.exists():
        KAOS_DB_PATH.unlink()


def test_mocked_expedition_ok(mocked_result) -> None:
    assert mocked_result["ok"] is True, mocked_result
    assert mocked_result["expedition_id"]
    assert Path(mocked_result["expedition_dir"]).is_dir()


def test_mocked_expedition_three_cards(mocked_result) -> None:
    assert mocked_result["task_card"]["id"].startswith("nvidia-earnings-infographic")
    assert len(mocked_result["result_cards"]) == 3
    assert {rc["agent_id"] for rc in mocked_result["result_cards"]} >= {"claude", "codex"}
    assert mocked_result["pareto_verdict"]["verdict_kind"] in {
        "dominated",
        "undominated",
        "no_clear_winner",
    }
    assert isinstance(mocked_result["evolution_card"]["mutation_seeds"], dict)


def test_mocked_expedition_artifacts_on_disk(mocked_result) -> None:
    out = Path(mocked_result["expedition_dir"])
    assert (out / "task_card.yaml").exists()
    assert (out / "pareto_verdict.yaml").exists()
    assert (out / "evolution_card.yaml").exists()
    assert len(list(out.glob("result_card_*.yaml"))) == 3
    assert (out / "trace").is_dir()
