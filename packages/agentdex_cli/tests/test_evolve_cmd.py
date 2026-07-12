from __future__ import annotations

import json
import sys

import yaml
from agentdex_cli.cli import main


def _candidate(tmp_path):
    (tmp_path / "agent.py").write_text("pass\n")
    (tmp_path / "candidate.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "evolver",
                "entrypoint": f"{sys.executable} agent.py",
                "mutable": ["agent.py"],
                "base_model": "model",
                "budget": {"usd": 1, "wall_clock_min": 2},
                "ladders": ["pokeagent-gen1ou"],
            }
        )
    )
    return tmp_path


def test_evolve_requires_data_flow_consent(tmp_path, capsys) -> None:
    rc = main(["evolve", "--agent", str(_candidate(tmp_path)), "--ladder", "pokeagent-gen1ou"])
    captured = capsys.readouterr()
    assert rc == 2 and "DATA FLOW DISCLOSURE" in captured.err
    assert "--accept-data-flow" in captured.err


def test_evolve_dry_run_builds_exact_weco_start_claude_argv(tmp_path, capsys, monkeypatch) -> None:
    root = _candidate(tmp_path)
    monkeypatch.setattr("agentdex_cli.evolve_cmd.shutil.which", lambda _name: "/bin/weco")
    rc = main(
        [
            "evolve",
            "--agent",
            str(root),
            "--ladder",
            "pokeagent-gen1ou",
            "--accept-data-flow",
            "--billing",
            "claude",
            "--effort",
            "high",
            "--headless",
            "--allow-tools",
            "--inner-weco-run",
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 0 and payload["cwd"] == str(root.resolve())
    assert payload["argv"][:5] == ["weco", "start", "claude", "--billing", "claude"]
    assert "--headless" in payload["argv"] and "--allow-tools" in payload["argv"]
    assert "weco run" in payload["argv"][payload["argv"].index("--prompt") + 1]


def test_evolve_headless_requires_approval_bypass(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setattr("agentdex_cli.evolve_cmd.shutil.which", lambda _name: "/bin/weco")
    rc = main(
        [
            "evolve",
            "--agent",
            str(_candidate(tmp_path)),
            "--ladder",
            "pokeagent-gen1ou",
            "--accept-data-flow",
            "--headless",
            "--dry-run",
        ]
    )
    assert rc == 2 and "--headless requires --allow-tools" in capsys.readouterr().err
