"""test_release_integrity_skill_gate — nightly release integrity must not require a
date-stamped version reference inside the committed SKILL.md files.

Regression for the `release` workflow break at origin/main 5a2c98a3 (2026-07-09): the
nightly job began failing at "Verify release integrity" because check_skill_files
asserted the exact date-derived version (0.1.0.devYYYYMMDD) appears in
packages/agentdex_arena/.../SKILL.md + site/SKILL.md. Nothing stamps a nightly version
into the tree — prepare_release.py bumps only the pyproject files — so that assertion is
unsatisfiable-by-construction for a nightly. It stayed latent because prior nightlies had
should_release=false (the whole verify step was skipped); today's #650–#660 merges made
the first should_release=true nightly since the check landed. The fix mirrors
check_blog_presence: the version-reference assertion is stable-only, while SKILL.md
*existence* stays a hard invariant on every release.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "scripts" / "verify_release_integrity.py"
NIGHTLY = "0.1.0.dev20260709"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_release_integrity", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_skill_tree(root: Path, *, body: str) -> None:
    arena = root / "packages" / "agentdex_arena" / "src" / "agentdex_arena"
    site = root / "site"
    arena.mkdir(parents=True, exist_ok=True)
    site.mkdir(parents=True, exist_ok=True)
    (arena / "SKILL.md").write_text(body, encoding="utf-8")
    (site / "SKILL.md").write_text(body, encoding="utf-8")


def test_nightly_skips_version_reference(tmp_path, monkeypatch):
    """A nightly (is_stable=False) passes even when SKILL.md omits the date-version —
    the exact break that failed the release workflow on main."""
    mod = _load_module()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    _make_skill_tree(tmp_path, body="# arena skill\nno version string here\n")
    assert mod.check_skill_files(NIGHTLY, is_stable=False) is True


def test_stable_still_enforces_version_reference(tmp_path, monkeypatch):
    """A stable release fails when SKILL.md omits the version — the guard still bites."""
    mod = _load_module()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    _make_skill_tree(tmp_path, body="# arena skill\nno version string here\n")
    assert mod.check_skill_files(NIGHTLY, is_stable=True) is False


def test_stable_passes_when_version_referenced(tmp_path, monkeypatch):
    """When SKILL.md carries the stable version, the stable gate passes."""
    mod = _load_module()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    _make_skill_tree(tmp_path, body=f"# arena skill\nreleased as {NIGHTLY}\n")
    assert mod.check_skill_files(NIGHTLY, is_stable=True) is True


def test_missing_skill_file_fails_even_on_nightly(tmp_path, monkeypatch):
    """SKILL.md existence is a hard invariant on every release, nightly included."""
    mod = _load_module()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    # Create only the arena skill; site/SKILL.md is absent.
    arena = tmp_path / "packages" / "agentdex_arena" / "src" / "agentdex_arena"
    arena.mkdir(parents=True, exist_ok=True)
    (arena / "SKILL.md").write_text("# arena skill\n", encoding="utf-8")
    assert mod.check_skill_files(NIGHTLY, is_stable=False) is False
