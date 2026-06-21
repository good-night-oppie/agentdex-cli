from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_fleet_kanban():
    path = Path(__file__).resolve().parents[1] / "tools" / "agent_senses" / "fleet_kanban.py"
    spec = importlib.util.spec_from_file_location("fleet_kanban", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_render_markdown_accepts_legacy_string_comments():
    fleet_kanban = _load_fleet_kanban()
    board = {
        "schema_version": 1,
        "updated_at": "2026-06-18T00:00:00Z",
        "cards": [
            {
                "id": "ADX-TEST-001",
                "priority": "P2",
                "status": "done",
                "assignee": "codex",
                "lane": "integrity",
                "title": "Legacy string comments render",
                "impact": "render should not crash",
                "fix": "support legacy comments",
                "evidence": ["unit"],
                "comments": [
                    "legacy comment",
                    {"author": "codex", "body": "structured comment"},
                ],
            }
        ],
        "events": [],
    }

    text = fleet_kanban.render_markdown(board)

    assert "legacy comment" in text
    assert "codex: structured comment" in text


def test_probe_gate_allows_ungated_card_without_calling_gate():
    fleet_kanban = _load_fleet_kanban()
    card = {"id": "C1", "status": "running"}  # no authored probe
    assert fleet_kanban._probe_gate_allows_done(card, "C1", Path("/tmp/b.json")) is None


def test_probe_gate_allows_done_when_gate_passes(tmp_path, monkeypatch):
    fleet_kanban = _load_fleet_kanban()
    gate = tmp_path / "gate_ok.py"
    gate.write_text("import sys\nsys.exit(0)\n")
    monkeypatch.setenv("KANBAN_PROBE_GATE", str(gate))
    monkeypatch.setenv("KANBAN_PROBE_GATE_RUN", sys.executable)
    card = {"id": "C2", "status": "running", "probes": {"probe": "kanban-card-C2-abc"}}
    assert fleet_kanban._probe_gate_allows_done(card, "C2", tmp_path / "b.json") is None


def test_probe_gate_blocks_done_when_gate_fails(tmp_path, monkeypatch):
    fleet_kanban = _load_fleet_kanban()
    gate = tmp_path / "gate_block.py"
    gate.write_text("import sys\nprint('BLOCK PROBE_REJECT')\nsys.exit(12)\n")
    monkeypatch.setenv("KANBAN_PROBE_GATE", str(gate))
    monkeypatch.setenv("KANBAN_PROBE_GATE_RUN", sys.executable)
    card = {"id": "C3", "status": "running", "probes": {"probe": "kanban-card-C3-abc"}}
    msg = fleet_kanban._probe_gate_allows_done(card, "C3", tmp_path / "b.json")
    assert msg is not None and "blocked by card-DONE gate" in msg
