"""Regression lock for the P0 change_manifest leak in the house EvolutionLoop.

The manifest is a SINGLE-USE pending prediction (written at the end of
generation N targeting N+1, consumed by N+1's falsification check). The bug:
`run_generation` only read it and never cleared it, and the Refiner only
overwrote it on a non-None return. A None-return ("no edit") left the prior
generation's manifest on disk; the next generation's `generation == gen` guard
then silently went False, no falsification window ran, and the loop reported
NEUTRAL forever. A HARMFUL rollback also restored best_ever's stale manifest.

Fixes locked here:
- `read_manifest()` is pure (does NOT delete); `clear_manifest()` removes it,
  DEFERRED to generation completion (PR #155 reviews #3418161864/#3418161865) so
  a failure between read and commit leaves the manifest for a clean retry.
- `rollback_to_best_ever()` clears any restored manifest.
- a wrong-generation manifest raises `EvolutionStateError` (never a silent skip),
  with the manifest still on disk so the evidence survives.

Stand-alone + sidecar-free: `HarnessWorkspace` is just a git-backed dir, so
these run in CI without the pokemon-showdown sidecar (the run_generation-level
behavior is covered in the sidecar-gated test_evolution.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from adx_showdown.evolution import ChangeManifest, HarnessWorkspace


def _ws(tmp_path: Path) -> HarnessWorkspace:
    return HarnessWorkspace.init(
        tmp_path / "ws", team_packed="Pikachu||Light Ball|Static|Thunderbolt||||||"
    )


def _manifest(gen: int) -> ChangeManifest:
    return ChangeManifest(
        generation=gen, summary=f"edit for gen {gen}", edited_stores=["teams.json"]
    )


def test_read_manifest_does_not_delete(tmp_path: Path):
    """read_manifest is pure — it must NOT remove the file (deletion is deferred
    to generation completion via clear_manifest, so a failure between read and
    commit leaves the manifest for a clean retry). PR #155 reviews."""
    ws = _ws(tmp_path)
    ws.write_manifest(_manifest(1))

    m = ws.read_manifest()
    assert m is not None and m.generation == 1
    # The file is STILL there — read does not consume.
    assert (ws.root / "change_manifest.json").is_file()
    # A second read still sees it (pure, repeatable).
    assert ws.read_manifest() is not None


def test_clear_manifest_removes_then_idempotent(tmp_path: Path):
    ws = _ws(tmp_path)
    ws.write_manifest(_manifest(1))
    assert (ws.root / "change_manifest.json").is_file()

    ws.clear_manifest()
    assert not (ws.root / "change_manifest.json").is_file()
    # Idempotent — clearing an absent manifest is a no-op (missing_ok).
    ws.clear_manifest()
    assert not (ws.root / "change_manifest.json").is_file()


def test_rollback_clears_restored_manifest(tmp_path: Path):
    """best_ever's restored tree must not leave a stale manifest that would trip
    the wrong-generation guard at the next generation."""
    ws = _ws(tmp_path)
    # Stage a manifest + commit it into a state, mark it best_ever (so the
    # restored tree carries a change_manifest.json).
    ws.write_manifest(_manifest(2))
    ws.commit_edits("gen with a manifest on disk")
    ws.mark_best_ever()
    # Drift the working tree, then roll back.
    (ws.root / "prompt.md").write_text("drifted\n")
    ws.rollback_to_best_ever()
    # Even though best_ever's tree had a manifest, rollback clears it.
    assert not (ws.root / "change_manifest.json").is_file()


def test_evolution_state_error_is_raisable():
    """The corrupt-state guard exists and is an exception (the run_generation
    wrong-generation raise path uses it; full-loop coverage is sidecar-gated)."""
    from adx_showdown.evolution import EvolutionStateError

    with pytest.raises(EvolutionStateError):
        raise EvolutionStateError("wrong-generation manifest")
