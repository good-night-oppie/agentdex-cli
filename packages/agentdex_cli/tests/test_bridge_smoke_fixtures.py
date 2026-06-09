"""Bridge-smoke fixture schema validator (closes DEFERRED BRIDGE-SMOKE
partially: the schema lock, not the live captures themselves).

When `tests/fixtures/bridges/<bridge>_smoke.json` files land via
`tools/agent_senses/capture_bridge_smoke.sh`, these tests verify they
match the schema in `tests/fixtures/bridges/README.md`. If no fixture
is present yet, the tests SKIP (not FAIL) — the discipline is to
preserve a passing test suite while still asserting shape when
fixtures arrive.

Anchor: EVAL.md row "Subscription-CLI bridge smoke probe passes at
session start" — this file is the receiving end of that gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "bridges"

REQUIRED_TOP_LEVEL = {
    "bridge",
    "binary_version",
    "captured_at",
    "captured_with",
    "handshake",
    "one_turn_probe",
    "drift_detector",
}

REQUIRED_HANDSHAKE_FIELDS = {"ms_until_init_frame", "session_id_format"}
REQUIRED_PROBE_FIELDS = {"task_id", "max_ms", "max_cost_usd"}


@pytest.mark.parametrize("bridge", ["claude", "codex", "manus"])
def test_bridge_smoke_fixture_shape_when_present(bridge: str):
    fixture_path = FIXTURE_DIR / f"{bridge}_smoke.json"
    if not fixture_path.is_file():
        pytest.skip(
            f"{fixture_path} not yet captured — run "
            f"`tools/agent_senses/capture_bridge_smoke.sh {bridge}`"
        )
    data = json.loads(fixture_path.read_text())

    missing_top = REQUIRED_TOP_LEVEL - set(data.keys())
    assert not missing_top, f"{bridge}_smoke.json missing top-level fields: {sorted(missing_top)}"
    assert data["bridge"] == bridge, f"bridge field mismatch: {data['bridge']!r} != {bridge!r}"

    hs = data["handshake"]
    missing_hs = REQUIRED_HANDSHAKE_FIELDS - set(hs.keys())
    assert not missing_hs, f"{bridge} handshake missing: {sorted(missing_hs)}"

    probe = data["one_turn_probe"]
    missing_probe = REQUIRED_PROBE_FIELDS - set(probe.keys())
    assert not missing_probe, f"{bridge} one_turn_probe missing: {sorted(missing_probe)}"
    assert probe["task_id"], "task_id must be non-empty"

    drift = data["drift_detector"]
    assert isinstance(drift, dict) and drift, (
        f"{bridge} drift_detector must be a non-empty dict — at least one fields_required_in_* key"
    )


def test_fixture_dir_has_readme():
    """The schema lives in README.md; without it the fixture format is undefined."""
    readme = FIXTURE_DIR / "README.md"
    assert readme.is_file(), "tests/fixtures/bridges/README.md missing — schema un-anchored"
    body = readme.read_text()
    assert "bridge" in body and "drift_detector" in body, (
        "README.md must document the schema fields the validator checks"
    )
