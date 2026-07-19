"""Unit tests for LadderAdapter ABC + Receipt / MeasureResult contracts."""

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
from adx_ladders.base import LadderAdapter, LadderClass, MeasureResult, Receipt


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
        "ladders": ["tb2", "arc-agi-3"],
    }
    base.update(overrides)
    return base


def _valid_scores() -> dict[str, float]:
    return {axis: 1.0 for axis in FRONTIER_AXES}


class _StubAdapter(LadderAdapter):
    ladder_id = "tb2"
    ladder_class = LadderClass.STATIC

    def measure(self, candidate: AgentCandidate) -> MeasureResult:
        return MeasureResult(
            scores=_valid_scores(),
            receipt=Receipt(
                tier="self_reported",
                kind="raw_artifacts",
                ref="",
                artifacts=("eval.log",),
            ),
            ladder_id=self.ladder_id,
            base_model=candidate.base_model,
            budget_usd=candidate.budget.usd,
            budget_wall_clock_min=candidate.budget.wall_clock_min,
        )


def test_receipt_verified_without_ref_rejected() -> None:
    with pytest.raises(ValueError, match="verified.*non-empty ref"):
        Receipt(tier="verified", kind="arc_scorecard_id", ref="")


def test_receipt_self_reported_without_artifacts_rejected() -> None:
    with pytest.raises(ValueError, match="self_reported.*artifacts"):
        Receipt(tier="self_reported", kind="raw_artifacts", ref="", artifacts=())


def test_receipt_verified_ok() -> None:
    r = Receipt(tier="verified", kind="arc_scorecard_id", ref="sc-123")
    assert r.ref == "sc-123"
    assert r.artifacts == ()


def test_receipt_self_reported_ok() -> None:
    r = Receipt(
        tier="self_reported",
        kind="raw_artifacts",
        ref="",
        artifacts=("logs/run.json",),
    )
    assert r.artifacts == ("logs/run.json",)


def test_measure_result_wrong_keys_rejected() -> None:
    receipt = Receipt(tier="verified", kind="kaggle_submission_id", ref="sub-1")
    with pytest.raises(ValueError, match="scores keys must be exactly"):
        MeasureResult(
            scores={"quality": 1.0, "cost_dollar": 0.1},
            receipt=receipt,
            ladder_id="tb2",
            base_model="claude-sonnet-5",
            budget_usd=5.0,
            budget_wall_clock_min=60.0,
        )


def test_measure_result_extra_keys_rejected() -> None:
    receipt = Receipt(tier="verified", kind="pokeagent_rating", ref="1500")
    scores = {**_valid_scores(), "extra": 0.0}
    with pytest.raises(ValueError, match="scores keys must be exactly"):
        MeasureResult(
            scores=scores,
            receipt=receipt,
            ladder_id="pokeagent-gen1ou",
            base_model="claude-sonnet-5",
            budget_usd=5.0,
            budget_wall_clock_min=60.0,
        )


def test_measure_result_valid_axes() -> None:
    receipt = Receipt(tier="verified", kind="arc_scorecard_id", ref="sc-1")
    result = MeasureResult(
        scores=_valid_scores(),
        receipt=receipt,
        ladder_id="arc-agi-3",
        base_model="claude-sonnet-5",
        budget_usd=5.0,
        budget_wall_clock_min=60.0,
    )
    assert set(result.scores) == set(FRONTIER_AXES)
    # Default avoids accidental honesty when callers omit the flag.
    assert result.cost_is_measured is False


def test_measure_result_cost_is_measured_explicit() -> None:
    receipt = Receipt(tier="verified", kind="arc_scorecard_id", ref="sc-1")
    result = MeasureResult(
        scores=_valid_scores(),
        receipt=receipt,
        ladder_id="arc-agi-3",
        base_model="claude-sonnet-5",
        budget_usd=5.0,
        budget_wall_clock_min=60.0,
        cost_is_measured=True,
    )
    assert result.cost_is_measured is True


def test_measure_result_carries_measured_effective_ladder_class() -> None:
    result = MeasureResult(
        scores=_valid_scores(),
        receipt=Receipt(tier="verified", kind="pokeagent_rating", ref="1512"),
        ladder_id="pokeagent-gen1ou",
        base_model="claude-sonnet-5",
        budget_usd=5.0,
        budget_wall_clock_min=60.0,
        effective_ladder_class=LadderClass.STATIC,
    )
    assert result.effective_ladder_class is LadderClass.STATIC


def test_measure_result_rejects_non_finite_score() -> None:
    """P2-c: NaN/Inf score values must be rejected."""
    receipt = Receipt(tier="verified", kind="arc_scorecard_id", ref="sc-1")
    scores = {**_valid_scores(), "quality": float("nan")}
    with pytest.raises(ValueError, match="finite float"):
        MeasureResult(
            scores=scores,
            receipt=receipt,
            ladder_id="arc-agi-3",
            base_model="claude-sonnet-5",
            budget_usd=5.0,
            budget_wall_clock_min=60.0,
        )


@pytest.mark.parametrize("axis", ["cost_dollar", "wall_clock_sec"])
def test_measure_result_rejects_negative_minimized_axis(axis: str) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        MeasureResult(
            scores={**_valid_scores(), axis: -100.0},
            receipt=Receipt(tier="verified", kind="arc_scorecard_id", ref="sc-1"),
            ladder_id="arc-agi-3",
            base_model="claude-sonnet-5",
            budget_usd=5.0,
            budget_wall_clock_min=60.0,
        )


@pytest.mark.parametrize("field", ["budget_usd", "budget_wall_clock_min"])
def test_measure_result_rejects_nonpositive_budget(field: str) -> None:
    kwargs = {"budget_usd": 5.0, "budget_wall_clock_min": 60.0, field: 0.0}
    with pytest.raises(ValueError, match=f"{field} must be"):
        MeasureResult(
            scores=_valid_scores(),
            receipt=Receipt(tier="verified", kind="arc_scorecard_id", ref="sc-1"),
            ladder_id="arc-agi-3",
            base_model="claude-sonnet-5",
            **kwargs,
        )


def test_measure_result_rejects_non_float_score() -> None:
    """P2-c: non-numeric score values must be rejected."""
    receipt = Receipt(tier="verified", kind="arc_scorecard_id", ref="sc-1")
    scores = {**_valid_scores(), "quality": "eleven"}  # type: ignore[dict-item]
    with pytest.raises(ValueError, match="finite float"):
        MeasureResult(
            scores=scores,
            receipt=receipt,
            ladder_id="arc-agi-3",
            base_model="claude-sonnet-5",
            budget_usd=5.0,
            budget_wall_clock_min=60.0,
        )


def test_measure_result_scores_immutable_post_construction() -> None:
    """P2-c: scores mapping must not be mutable after construction."""
    receipt = Receipt(tier="verified", kind="arc_scorecard_id", ref="sc-1")
    result = MeasureResult(
        scores=_valid_scores(),
        receipt=receipt,
        ladder_id="arc-agi-3",
        base_model="claude-sonnet-5",
        budget_usd=5.0,
        budget_wall_clock_min=60.0,
    )
    with pytest.raises(TypeError):
        result.scores["quality"] = 0.0  # type: ignore[index]


def test_receipt_verified_whitespace_ref_rejected() -> None:
    """P2-d: whitespace-only verified ref must be rejected."""
    with pytest.raises(ValueError, match="verified.*non-empty ref"):
        Receipt(tier="verified", kind="arc_scorecard_id", ref="   ")


def test_receipt_self_reported_blank_artifacts_rejected() -> None:
    """P2-d: blank-only artifact strings must be rejected."""
    with pytest.raises(ValueError, match="self_reported.*artifacts"):
        Receipt(
            tier="self_reported",
            kind="raw_artifacts",
            ref="",
            artifacts=("  ", ""),
        )


def test_pre_run_check_invalid_candidate_rejected(tmp_path: Path) -> None:
    root = _write_candidate(
        tmp_path,
        _valid_manifest(name=""),
        files={"src/agent.py": b"print('ok')\n"},
    )
    candidate = load_candidate(root)
    adapter = _StubAdapter()
    with pytest.raises(CandidateValidationError):
        adapter.pre_run_check(candidate)


def test_pre_run_check_ladder_not_in_candidate_rejected(tmp_path: Path) -> None:
    root = _write_candidate(
        tmp_path,
        _valid_manifest(ladders=["arc-agi-3"]),
        files={"src/agent.py": b"print('ok')\n"},
    )
    candidate = load_candidate(root)
    adapter = _StubAdapter()  # ladder_id = tb2
    with pytest.raises(ValueError, match="not in candidate.ladders"):
        adapter.pre_run_check(candidate)


def test_pre_run_check_valid_passes(tmp_path: Path) -> None:
    root = _write_candidate(
        tmp_path,
        _valid_manifest(ladders=["tb2", "arc-agi-3"]),
        files={"src/agent.py": b"print('ok')\n"},
    )
    candidate = load_candidate(root)
    adapter = _StubAdapter()
    adapter.pre_run_check(candidate)  # must not raise
    result = adapter.measure(candidate)
    assert result.ladder_id == "tb2"
    assert result.receipt.tier == "self_reported"
