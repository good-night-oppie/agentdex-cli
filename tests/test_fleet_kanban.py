from __future__ import annotations

import importlib.util
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
