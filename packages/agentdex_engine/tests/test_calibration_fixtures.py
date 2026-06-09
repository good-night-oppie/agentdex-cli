"""Calibration round-trip test (closes DEFERRED CALIB-FIXTURES partially:
the 13-row scaffold + the round-trip wiring; full κ ≥ 0.7 inter-rater gate
waits for a second labeler per EVAL.md self-judge guardrails).

Loads the YAML fixtures under oracle_calibration_fixtures/narrative_coherence/
into the (response, expected_score, expected_pass) tuple shape that
calibrate() consumes, runs a deterministic stub judge, and asserts the
CalibrationReport shape + that a well-calibrated stub crosses the 0.7
accuracy gate.

Anchor: EVAL.md row "Soft-Oracle judge calibration ≥ 0.7 accuracy on
≥10 labeled fixtures".
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from agentdex_engine.cards import TaskCard
from agentdex_engine.oracle.base import OracleVerdict
from agentdex_engine.oracle.calibration import CalibrationReport, calibrate

FIXTURES_DIR = Path(__file__).parent / "oracle_calibration_fixtures" / "narrative_coherence"

_CITATION_RE = re.compile(r"\bsource\s*:\s*[\w\-./]+\.md\s*:\s*\d+", re.IGNORECASE)
_BULLET_RE = re.compile(r"^[ \t]*(?:[-*•]|\d+[.)]|[a-z][.)])[ \t]+(.+)$", re.MULTILINE)
_NVIDIA_NUMBERS = ("$35.08", "$30.77", "74.6%", "$37.5", "$5.40", "$1.85")
_OFF_TOPIC_TOKENS = ("AMD", "Intel", "Tesla")


def _load_all_fixtures() -> list[tuple[str, float, bool, str]]:
    """Yield (response, expected_score, expected_pass, fixture_id).

    Skips the rater-2 sidecar (`labels_rater_2.yaml`) — that file carries
    a different schema (`labels:` not `fixtures:`) consumed by the inter-
    rater κ test, not the round-trip calibration test.
    """
    rows: list[tuple[str, float, bool, str]] = []
    for yaml_path in sorted(FIXTURES_DIR.glob("*.yaml")):
        if yaml_path.name.startswith("labels_rater_"):
            continue
        body = yaml.safe_load(yaml_path.read_text())
        for fix in body.get("fixtures", []):
            rows.append(
                (
                    fix["response"],
                    float(fix["expected_score"]),
                    bool(fix["expected_pass"]),
                    fix["id"],
                )
            )
    return rows


def _build_task_card() -> TaskCard:
    return TaskCard(
        id="nvidia-earnings-infographic-q3-fy2026",
        source_bundle_hash="9edcd1a12c51f1741d90fab7b733a2144f1831bf7d28a7ead3165052c66dc09c",  # pragma: allowlist secret
        environment_spec={"runtime": "calibration-test"},
        oracle_spec_ref="tasks/nvidia-earnings-infographic/oracle/spec.yaml",
        budget_token_cap=1000,
        budget_dollar_cap=1.0,
        expected_output_kind="infographic",
        version="0.1.0",
    )


class _DeterministicNvidiaJudge:
    """Mirror what a well-calibrated soft Oracle would do on these fixtures:
    score = blended (citation density × bullet structure × NVIDIA-number hit).
    Returns ``soft.narrative_coherence`` verdict per calibrate()'s default key.
    """

    def evaluate(self, response: str, task_card: TaskCard):
        if not response.strip():
            score, passed = 0.05, False
        elif any(tok in response for tok in _OFF_TOPIC_TOKENS):
            score, passed = 0.02, False
        elif "cannot help" in response.lower() or "more context" in response.lower():
            score, passed = 0.05, False
        else:
            bullets = _BULLET_RE.findall(response)
            citations = _CITATION_RE.findall(response)
            nvidia_hits = sum(1 for n in _NVIDIA_NUMBERS if n in response)
            citation_score = min(len(citations) / max(len(bullets), 1), 1.0)
            content_score = min(nvidia_hits / 4, 1.0)
            score = round(0.5 * citation_score + 0.5 * content_score, 2)
            passed = score >= 0.7
        return {
            "soft.narrative_coherence": OracleVerdict(
                kind="soft",
                **{"pass": passed},
                score=score,
                evidence=f"calibration stub: score={score} pass={passed}",
                uncertainty=0.2,
            )
        }


def test_fixture_dir_yields_at_least_ten_rows():
    """EVAL.md: ≥10 labeled fixtures gate."""
    rows = _load_all_fixtures()
    assert len(rows) >= 10, f"need ≥10 fixtures for calibration gate; have {len(rows)}"


def test_all_fixture_yamls_parse_to_calibrate_tuple_shape():
    """Every fixture YAML row maps cleanly to calibrate()'s
    (response, expected_score, expected_pass) signature."""
    rows = _load_all_fixtures()
    for resp, score, passed, fid in rows:
        assert isinstance(resp, str), f"{fid}: response must be str"
        assert isinstance(score, float) and 0.0 <= score <= 1.0, (
            f"{fid}: expected_score must be float in [0,1]; got {score}"
        )
        assert isinstance(passed, bool), f"{fid}: expected_pass must be bool"


def test_calibration_round_trip_passes_on_well_calibrated_judge():
    """A well-calibrated deterministic stub crosses the 0.7 accuracy gate."""
    rows = _load_all_fixtures()
    fixtures = [(r, s, p) for r, s, p, _ in rows]
    report = calibrate(
        judge=_DeterministicNvidiaJudge(),
        fixtures=fixtures,
        task_card=_build_task_card(),
        min_accuracy=0.7,
    )
    assert isinstance(report, CalibrationReport)
    assert report.n_samples == len(rows)
    assert report.passed_calibration is True, (
        f"stub judge should hit ≥0.7 accuracy on these fixtures; "
        f"got accuracy={report.accuracy:.2f}, kappa={report.kappa:.2f}"
    )
    # Confusion matrix sums to n_samples.
    assert sum(r.count for r in report.confusion_matrix_rows) == report.n_samples


def test_calibration_round_trip_fails_on_bad_judge():
    """A pathological judge (always-pass) MUST fail the 0.7 gate so the
    calibration gate has bite, not theater."""

    class _AlwaysPass:
        def evaluate(self, response, task_card):
            return {
                "soft.narrative_coherence": OracleVerdict(
                    kind="soft",
                    **{"pass": True},
                    score=0.95,
                    evidence="bad judge: always pass",
                    uncertainty=0.0,
                )
            }

    rows = _load_all_fixtures()
    fixtures = [(r, s, p) for r, s, p, _ in rows]
    report = calibrate(
        judge=_AlwaysPass(),
        fixtures=fixtures,
        task_card=_build_task_card(),
        min_accuracy=0.7,
    )
    assert report.passed_calibration is False, (
        "always-pass judge MUST fail calibration; otherwise gate is theater"
    )
