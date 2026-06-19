"""Durability + substrate-gated run of the FULL real-stack self-play meta-harness
e2e (``tasks/selfplay-metaharness/e2e_selfplay_metaharness.py``).

The first test is CI-runnable — it asserts the proof script stays committed + parses
(so it can never silently rot back into ``.scratch``). The real loop only runs when
the heavy substrate (bene + poke-env + a live PS server) is explicitly opted into.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import socket

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_E2E_SCRIPT = _REPO_ROOT / "tasks" / "selfplay-metaharness" / "e2e_selfplay_metaharness.py"


def _substrate_ready() -> bool:
    if os.environ.get("ADX_E2E_SELFPLAY") != "1":
        return False
    if not os.environ.get("BENE_LANEB"):
        return False
    try:
        import poke_env  # noqa: F401
    except ModuleNotFoundError:
        return False
    host = os.environ.get("ADX_PS_HOST", "127.0.0.1")
    port = int(os.environ.get("ADX_PS_PORT", "8000"))
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def test_committed_e2e_script_is_present_and_valid():
    # Durability: the proven real-bene full-stack e2e is version-controlled, not in
    # ephemeral .scratch. Parse it WITHOUT executing (exec would pull bene/poke-env)
    # and assert the public entrypoints exist.
    assert _E2E_SCRIPT.is_file(), f"missing committed e2e proof: {_E2E_SCRIPT}"
    src = _E2E_SCRIPT.read_text()
    compile(src, str(_E2E_SCRIPT), "exec")  # SyntaxError if it ever breaks
    assert "def run(" in src and "def main(" in src


@pytest.mark.skipif(
    not _substrate_ready(),
    reason="real e2e needs ADX_E2E_SELFPLAY=1 + BENE_LANEB + poke-env + a live PS server",
)
def test_real_e2e_meta_harness_loop_emits_done_json():
    spec = importlib.util.spec_from_file_location("e2e_selfplay_metaharness", _E2E_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    done = mod.run()
    assert done["DONE_JSON"] is True
    assert done["real_components"] == [
        "A1.run_vs_baselines",
        "A3.multi_dim_fitness",
        "B1.evolve_battle_harness",
    ]
    assert done["mocked_components"] == []
    # anti-vacuous: real battles were played AND at least one generation ran
    assert done["battles_played"] > 0
    assert done["gens_completed"] > 0
    assert done["anti_vacuous"]["battles_played_gt_0"] is True
    assert done["anti_vacuous"]["gens_gt_0"] is True
    # bene's kill-gate produced a real verdict (ACCEPT/REJECT) — not asserted to
    # ACCEPT here because the un-seeded PS server RNG makes a 2-battle uplift vary.
    assert done["killgate_report"]["verdict"] in ("ACCEPT", "REJECT")
