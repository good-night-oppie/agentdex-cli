"""Inter-rater κ ≥ 0.7 gate for the narrative_coherence calibration corpus.

Closes DEFERRED.md CALIB-FIXTURES. PR-U (553ebd4) landed the 13-row
rater-1 corpus + the round-trip test; this test closes the remaining
"≥ 2 raters required for κ ≥ 0.7 gate" requirement by loading the
rater-2 labels sidecar at
``oracle_calibration_fixtures/narrative_coherence/labels_rater_2.yaml``
and asserting Cohen's κ against the rater-1 ``expected_pass`` column.

Rater-2 is an AI (claude-opus-4.7) by design — see the sidecar's header
note for the rationale. The rater-2 sidecar is greppable so future
analysis can distinguish human-vs-AI agreement when a second human
labeler lands.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_FIXTURES_DIR = Path(__file__).parent / "oracle_calibration_fixtures" / "narrative_coherence"
_RATER_2_FILE = _FIXTURES_DIR / "labels_rater_2.yaml"
_KAPPA_GATE = 0.7


def _load_rater_1_labels() -> dict[str, bool]:
    rater_1: dict[str, bool] = {}
    for path in sorted(_FIXTURES_DIR.glob("*.yaml")):
        if path.name == "labels_rater_2.yaml":
            continue
        body = yaml.safe_load(path.read_text())
        for fix in body.get("fixtures", []):
            rater_1[fix["id"]] = bool(fix["expected_pass"])
    return rater_1


def _load_rater_2_labels() -> dict[str, bool]:
    body = yaml.safe_load(_RATER_2_FILE.read_text())
    return {row["id"]: bool(row["expected_pass_2"]) for row in body["labels"]}


def _cohen_kappa(a: list[bool], b: list[bool]) -> float:
    """Cohen's κ on two binary label sequences of equal length.

    κ = (po - pe) / (1 - pe) where po = observed agreement, pe = expected
    agreement by chance based on each rater's marginal pass-rate.
    """
    if len(a) != len(b) or not a:
        raise ValueError("equal-length non-empty sequences required")
    n = len(a)
    po = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    pa_true = sum(a) / n
    pb_true = sum(b) / n
    pe = pa_true * pb_true + (1 - pa_true) * (1 - pb_true)
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def test_rater_2_covers_every_rater_1_fixture():
    """Every rater-1 fixture id must appear in rater-2 sidecar — no silent drop."""
    r1 = _load_rater_1_labels()
    r2 = _load_rater_2_labels()
    missing = sorted(set(r1) - set(r2))
    assert not missing, f"rater-2 sidecar missing labels for {missing}"
    extra = sorted(set(r2) - set(r1))
    assert not extra, f"rater-2 sidecar has stray ids not in rater-1: {extra}"


def test_inter_rater_kappa_meets_gate():
    """Cohen's κ ≥ 0.7 between rater-1 (human) and rater-2 (AI) on narrative_coherence."""
    r1 = _load_rater_1_labels()
    r2 = _load_rater_2_labels()
    ids = sorted(r1)
    a = [r1[i] for i in ids]
    b = [r2[i] for i in ids]
    kappa = _cohen_kappa(a, b)
    assert kappa >= _KAPPA_GATE, (
        f"Cohen's κ = {kappa:.3f} below {_KAPPA_GATE} gate (n={len(ids)}); "
        "either re-label marginal fixtures or expand the corpus"
    )


def test_kappa_function_matches_reference_examples():
    """Sanity-check the κ helper against hand-computed examples."""
    # Perfect agreement → κ = 1.
    assert abs(_cohen_kappa([True, False, True], [True, False, True]) - 1.0) < 1e-9
    # Total disagreement on balanced ratings → κ = -1.
    k = _cohen_kappa([True, False], [False, True])
    assert abs(k - (-1.0)) < 1e-9
    # Balanced raters with chance-level agreement → κ = 0.
    # a=[T,T,F,F], b=[T,F,T,F]: agree 2/4 = 0.5; pe = 0.5*0.5 + 0.5*0.5 = 0.5.
    k = _cohen_kappa([True, True, False, False], [True, False, True, False])
    assert abs(k - 0.0) < 1e-9
