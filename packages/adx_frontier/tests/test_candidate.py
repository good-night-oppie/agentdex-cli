"""Unit tests for AgentCandidate load + pre-run validation gate."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from adx_frontier.candidate import (
    FRONTIER_AXES,
    AgentCandidate,
    CandidateValidationError,
    load_candidate,
)


def _write_candidate(tmp_path: Path, manifest: dict, files: dict[str, bytes] | None = None) -> Path:
    for rel, content in (files or {}).items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (tmp_path / "candidate.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    return tmp_path


def _valid_manifest(**overrides: object) -> dict:
    base: dict = {
        "name": "my-agent",
        "entrypoint": "python -m my_agent",
        "mutable": ["src/**/*.py"],
        "base_model": "claude-sonnet-5",
        "budget": {"usd": 5.0, "wall_clock_min": 60},
        "ladders": ["tb2", "arc-agi-3", "pokeagent-gen1ou"],
    }
    base.update(overrides)
    return base


def test_frontier_axes_constant() -> None:
    assert FRONTIER_AXES == ("quality", "cost_dollar", "wall_clock_sec")


def test_valid_manifest_accepted(tmp_path: Path) -> None:
    root = _write_candidate(
        tmp_path,
        _valid_manifest(),
        files={"src/agent.py": b"print('ok')\n", "src/util.py": b"x = 1\n"},
    )
    candidate = load_candidate(root)
    candidate.validate()  # must not raise
    assert isinstance(candidate, AgentCandidate)
    assert candidate.name == "my-agent"
    assert candidate.base_model == "claude-sonnet-5"
    assert candidate.budget.usd == 5.0
    assert len(candidate.expand_mutable()) == 2


def test_reject_too_many_mutable_files(tmp_path: Path) -> None:
    files = {f"src/f{i}.py": b"x\n" for i in range(11)}
    root = _write_candidate(tmp_path, _valid_manifest(), files=files)
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="narrow your weco-mutable subset"):
        candidate.validate()


def test_reject_oversize_file(tmp_path: Path) -> None:
    big = b"x" * (200 * 1024 + 1)
    root = _write_candidate(
        tmp_path,
        _valid_manifest(),
        files={"src/big.py": big},
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="narrow your weco-mutable subset"):
        candidate.validate()


def test_reject_oversize_total(tmp_path: Path) -> None:
    # 3 files × 200KB = 600KB total, each under the per-file cap
    chunk = b"y" * (200 * 1024)
    root = _write_candidate(
        tmp_path,
        _valid_manifest(),
        files={
            "src/a.py": chunk,
            "src/b.py": chunk,
            "src/c.py": chunk,
        },
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="narrow your weco-mutable subset"):
        candidate.validate()


def test_reject_missing_budget(tmp_path: Path) -> None:
    manifest = _valid_manifest()
    del manifest["budget"]
    root = _write_candidate(
        tmp_path,
        manifest,
        files={"src/a.py": b"x\n"},
    )
    with pytest.raises(CandidateValidationError, match="budget"):
        load_candidate(root)


def test_reject_zero_budget_usd(tmp_path: Path) -> None:
    root = _write_candidate(
        tmp_path,
        _valid_manifest(budget={"usd": 0, "wall_clock_min": 60}),
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="budget"):
        candidate.validate()


def test_reject_zero_budget_wall_clock(tmp_path: Path) -> None:
    root = _write_candidate(
        tmp_path,
        _valid_manifest(budget={"usd": 5.0, "wall_clock_min": 0}),
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="budget"):
        candidate.validate()


def test_reject_unknown_ladder(tmp_path: Path) -> None:
    root = _write_candidate(
        tmp_path,
        _valid_manifest(ladders=["tb2", "not-a-real-ladder"]),
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="unknown ladder"):
        candidate.validate()


def test_reject_empty_ladders(tmp_path: Path) -> None:
    root = _write_candidate(
        tmp_path,
        _valid_manifest(ladders=[]),
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="ladders"):
        candidate.validate()


def test_reject_missing_base_model(tmp_path: Path) -> None:
    root = _write_candidate(
        tmp_path,
        _valid_manifest(base_model=""),
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="base_model"):
        candidate.validate()


def test_reject_missing_entrypoint(tmp_path: Path) -> None:
    root = _write_candidate(
        tmp_path,
        _valid_manifest(entrypoint=""),
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="entrypoint"):
        candidate.validate()


def test_weco_limit_error_includes_counts(tmp_path: Path) -> None:
    files = {f"src/f{i}.py": b"x\n" for i in range(12)}
    root = _write_candidate(tmp_path, _valid_manifest(), files=files)
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError) as exc_info:
        candidate.validate()
    msg = str(exc_info.value)
    assert "narrow your weco-mutable subset" in msg
    assert "file_count=12" in msg


def test_reject_nan_budget(tmp_path: Path) -> None:
    """P1-1: NaN budget must not bypass the pre-run gate."""
    root = _write_candidate(
        tmp_path,
        _valid_manifest(budget={"usd": float("nan"), "wall_clock_min": 60}),
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="finite"):
        candidate.validate()


def test_reject_inf_budget(tmp_path: Path) -> None:
    """P1-1: Inf budget must not bypass the pre-run gate."""
    root = _write_candidate(
        tmp_path,
        _valid_manifest(budget={"usd": 5.0, "wall_clock_min": float("inf")}),
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="finite"):
        candidate.validate()


def test_reject_absolute_mutable_glob(tmp_path: Path) -> None:
    """P2-b: absolute mutable globs → CandidateValidationError, not raw raise."""
    outside = tmp_path / "outside.py"
    outside.write_text("x\n", encoding="utf-8")
    root = _write_candidate(
        tmp_path / "agent",
        _valid_manifest(mutable=[str(outside)]),
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="absolute|relative"):
        candidate.validate()


def test_reject_parent_escape_mutable_glob(tmp_path: Path) -> None:
    """P2-b: ``../`` mutable globs that leave root → CandidateValidationError."""
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    (sibling / "leak.py").write_text("x\n", encoding="utf-8")
    agent = tmp_path / "agent"
    root = _write_candidate(
        agent,
        _valid_manifest(mutable=["../sibling/*.py"]),
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="escapes candidate root"):
        candidate.validate()


def test_reject_out_of_root_symlink_mutable(tmp_path: Path) -> None:
    """P2-b: symlink under root pointing outside → CandidateValidationError."""
    outside = tmp_path / "outside_secret.py"
    outside.write_bytes(b"x" * 100)
    agent = tmp_path / "agent"
    root = _write_candidate(
        agent,
        _valid_manifest(mutable=["src/**/*.py"]),
        files={"src/a.py": b"x\n"},
    )
    (root / "src" / "leak.py").symlink_to(outside)
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="escapes candidate root"):
        candidate.validate()


def test_reject_empty_mutable_list(tmp_path: Path) -> None:
    """P3: mutable: [] must fail the pre-run gate (not expand to zero silently)."""
    root = _write_candidate(
        tmp_path,
        _valid_manifest(mutable=[]),
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="mutable must be a non-empty"):
        candidate.validate()


def test_reject_missing_mutable_key(tmp_path: Path) -> None:
    """P3: omitted mutable key normalizes to empty and must fail validate()."""
    manifest = _valid_manifest()
    del manifest["mutable"]
    root = _write_candidate(
        tmp_path,
        manifest,
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="mutable must be a non-empty"):
        candidate.validate()


def test_reject_zero_match_mutable_glob(tmp_path: Path) -> None:
    """P3: typo glob that matches zero files must name the offending pattern."""
    root = _write_candidate(
        tmp_path,
        _valid_manifest(mutable=["src/**/*.py", "typo_dir/**/*.py"]),
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match=r"typo_dir/\*\*/\*\.py") as exc_info:
        candidate.validate()
    assert "matched zero files" in str(exc_info.value)


def test_reject_sole_zero_match_mutable_glob(tmp_path: Path) -> None:
    """P3: a single typo glob (no other patterns) still fails closed."""
    root = _write_candidate(
        tmp_path,
        _valid_manifest(mutable=["does_not_exist/**/*.py"]),
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(
        CandidateValidationError,
        match=r"does_not_exist/\*\*/\*\.py.*matched zero files",
    ):
        candidate.validate()


def test_reject_name_with_zero_width_space(tmp_path: Path) -> None:
    """P3: U+200B in name must not pass as a non-empty visible name."""
    root = _write_candidate(
        tmp_path,
        _valid_manifest(name="my\u200bagent"),
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(
        CandidateValidationError,
        match="invisible Unicode format",
    ):
        candidate.validate()


def test_reject_name_that_is_only_zero_width_space(tmp_path: Path) -> None:
    """P3: name consisting solely of Cf chars is not a valid identity."""
    root = _write_candidate(
        tmp_path,
        _valid_manifest(name="\u200b"),
        files={"src/a.py": b"x\n"},
    )
    candidate = load_candidate(root)
    with pytest.raises(CandidateValidationError, match="name"):
        candidate.validate()
