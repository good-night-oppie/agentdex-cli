"""Tests for ``adx measure`` (M2 WU-5)."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from adx_frontier.candidate import FRONTIER_AXES
from agentdex_cli.cli import main

_ECHO_AGENT = textwrap.dedent(
    """\
    import json
    import sys

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if msg.get("type") == "observation":
            print(json.dumps({"type": "action", "action": "idle"}), flush=True)
    """
)


def _write_candidate(
    tmp_path: Path,
    *,
    ladders: list[str] | None = None,
    files: dict[str, bytes] | None = None,
    entrypoint: str | None = None,
    echo_agent: bool = False,
) -> Path:
    if files is None:
        files = {"src/noop.py": b"# noop\n"}
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    if echo_agent:
        script = tmp_path / "agent.py"
        script.write_text(_ECHO_AGENT, encoding="utf-8")
        entrypoint = f"{sys.executable} agent.py"
    elif entrypoint is None:
        agent = tmp_path / "agent.py"
        agent.write_text("print('ok')\n", encoding="utf-8")
        entrypoint = f"{sys.executable} agent.py"

    manifest = {
        "name": "measure-test-agent",
        "entrypoint": entrypoint,
        "mutable": ["src/**/*.py"],
        "base_model": "claude-sonnet-5",
        "budget": {"usd": 5.0, "wall_clock_min": 5.0},
        "ladders": ladders if ladders is not None else ["arc-agi-3", "tb2"],
    }
    (tmp_path / "candidate.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    return tmp_path


def test_gate_rejection_oversized_mutable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = {f"src/f{i}.py": b"x\n" for i in range(11)}
    root = _write_candidate(tmp_path, files=files)

    rc = main(["measure", "--agent", str(root), "--ladder", "tb2", "--engine-fake"])

    err = capsys.readouterr().err
    assert rc == 2
    assert "narrow your weco-mutable subset" in err


def test_happy_path_tb2_engine_fake(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _write_candidate(tmp_path, ladders=["tb2", "arc-agi-3"])
    out_path = tmp_path / "out.json"

    rc = main(
        [
            "measure",
            "--agent",
            str(root),
            "--ladder",
            "tb2",
            "--engine-fake",
            "--out",
            str(out_path),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0, f"stderr={captured.err!r}"
    payload = json.loads(captured.out)
    assert set(payload["scores"]) == set(FRONTIER_AXES)
    assert payload["receipt"]["kind"] == "fake_engine"
    assert payload["receipt"]["tier"] == "self_reported"
    assert payload["ladder_id"] == "tb2"
    assert payload["base_model"] == "claude-sonnet-5"
    assert "usd" in payload["budget"] and "wall_clock_min" in payload["budget"]
    assert "measured_at_utc" in payload
    assert out_path.is_file()
    assert json.loads(out_path.read_text(encoding="utf-8")) == payload


def test_happy_path_arc_agi3_engine_fake(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _write_candidate(
        tmp_path,
        ladders=["arc-agi-3", "tb2"],
        echo_agent=True,
    )

    rc = main(
        ["measure", "--agent", str(root), "--ladder", "arc-agi-3", "--engine-fake"]
    )

    captured = capsys.readouterr()
    assert rc == 0, f"stderr={captured.err!r}"
    payload = json.loads(captured.out)
    assert set(payload["scores"]) == set(FRONTIER_AXES)
    assert payload["receipt"]["kind"] == "fake_engine"
    assert payload["receipt"]["tier"] == "self_reported"
    assert payload["ladder_id"] == "arc-agi-3"
    assert payload["scores"]["quality"] == pytest.approx(0.42)


def test_unknown_ladder(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _write_candidate(tmp_path)

    rc = main(
        ["measure", "--agent", str(root), "--ladder", "not-a-ladder", "--engine-fake"]
    )

    err = capsys.readouterr().err
    assert rc != 0
    assert "unknown ladder" in err


def test_run_adapter_false_kaggle_exits_3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # kaggle is in KNOWN_LADDERS but run_adapter:false in the registry.
    root = _write_candidate(tmp_path, ladders=["kaggle", "tb2"])

    rc = main(["measure", "--agent", str(root), "--ladder", "kaggle", "--engine-fake"])

    err = capsys.readouterr().err
    assert rc == 3
    assert "run_adapter=false" in err or "run_adapter" in err
