from __future__ import annotations

import sys
from pathlib import Path

from adx_showdown.selfplay.entrypoint_agent import EntrypointAgent


def _script(tmp_path: Path, body: str) -> str:
    path = tmp_path / "agent.py"
    path.write_text(body, encoding="utf-8")
    return f"{sys.executable} {path.name}"


def test_entrypoint_agent_round_trips_jsonl_action(tmp_path: Path) -> None:
    command = _script(
        tmp_path,
        "import json, sys\n"
        "for line in sys.stdin:\n"
        " msg = json.loads(line)\n"
        " print(json.dumps({'type':'action','action':msg['battle']['available_moves'][0]['id']}), flush=True)\n",
    )
    with EntrypointAgent(command, cwd=tmp_path, timeout_sec=1.0) as agent:
        assert agent(None, {"available_moves": [{"id": "tackle"}]}) == "tackle"
        assert agent(None, {"available_moves": [{"id": "ember"}]}) == "ember"


def test_entrypoint_agent_abstains_and_stops_on_timeout(tmp_path: Path) -> None:
    command = _script(tmp_path, "import time\ntime.sleep(10)\n")
    agent = EntrypointAgent(command, cwd=tmp_path, timeout_sec=0.01)
    assert agent(None, {}) is None
    assert agent._proc.poll() is not None


def test_entrypoint_agent_abstains_on_malformed_reply(tmp_path: Path) -> None:
    command = _script(tmp_path, "print('not-json', flush=True)\n")
    with EntrypointAgent(command, cwd=tmp_path, timeout_sec=1.0) as agent:
        assert agent(None, {}) is None
