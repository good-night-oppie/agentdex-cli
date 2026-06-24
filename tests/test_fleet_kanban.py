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


def _board(card_id: str = "ADX-TEST-001"):
    return {
        "schema_version": 1,
        "updated_at": "2026-06-18T00:00:00Z",
        "cards": [
            {
                "id": card_id,
                "priority": "P2",
                "status": "todo",
                "assignee": "codex",
                "lane": "integrity",
                "title": "Test card",
                "impact": "test",
                "fix": "test",
                "evidence": [],
            }
        ],
        "events": [],
    }


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


def test_ktui_mirror_loads_explicit_adapter_path(tmp_path, monkeypatch):
    fleet_kanban = _load_fleet_kanban()
    marker = tmp_path / "mirrored.txt"
    adapter = tmp_path / "kanban_store.py"
    adapter.write_text(
        "from pathlib import Path\n"
        "def mirror_to_ktui(board):\n"
        f"    Path({str(marker)!r}).write_text(board['cards'][0]['id'])\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fleet_kanban, "KTUI_ADAPTER_PATH", adapter)

    fleet_kanban._try_mirror_to_ktui(_board("ADX-MIRROR-001"))

    assert marker.read_text(encoding="utf-8") == "ADX-MIRROR-001"


def test_ktui_mirror_ignores_rogue_sys_path_module(tmp_path, monkeypatch):
    fleet_kanban = _load_fleet_kanban()
    marker = tmp_path / "rogue.txt"
    rogue_dir = tmp_path / "rogue"
    rogue_dir.mkdir()
    (rogue_dir / "kanban_store.py").write_text(
        "from pathlib import Path\n"
        "def mirror_to_ktui(board):\n"
        f"    Path({str(marker)!r}).write_text('wrong store')\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(rogue_dir))
    monkeypatch.setattr(fleet_kanban, "KTUI_ADAPTER_PATH", tmp_path / "missing.py")

    fleet_kanban._try_mirror_to_ktui(_board())

    assert not marker.exists()


def test_write_board_mirrors_only_default_board_path(tmp_path, monkeypatch):
    fleet_kanban = _load_fleet_kanban()
    mirrored: list[str] = []
    monkeypatch.setattr(
        fleet_kanban,
        "_try_mirror_to_ktui",
        lambda board: mirrored.append(board["cards"][0]["id"]),
    )
    default_path = tmp_path / "canonical.json"
    monkeypatch.setattr(fleet_kanban, "DEFAULT_BOARD_PATH", default_path)

    fleet_kanban.write_board(tmp_path / "sandbox.json", _board("ADX-SANDBOX-001"))
    assert mirrored == []

    fleet_kanban.write_board(default_path, _board("ADX-CANONICAL-001"))
    assert mirrored == ["ADX-CANONICAL-001"]


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
