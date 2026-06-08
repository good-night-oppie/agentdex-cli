"""Calibration harness for the soft Oracle judge.

Per phase-6 spec + ``.agents/skills/langfuse/references/judge-calibration.md``,
the LLM-as-judge failure mode (noisy judge → Pareto noise → EvolutionCard
noise per Superlinear §8) is mitigated by validating judge output against
labeled fixtures BEFORE trusting it in an Expedition.

Pipeline:
1. Caller provides labeled fixtures ``[(response, expected_score, expected_pass)]``.
2. ``calibrate(judge, fixtures, threshold)`` runs the judge on each, returns
   :class:`CalibrationReport` with accuracy / precision / recall / Cohen's
   kappa / confusion matrix.
3. If ``report.accuracy < calibration_min_accuracy`` (default 0.7), the
   Oracle layer emits a ``Seed(kind="oracle_repair",
   seed_provenance="structural")`` so the EvolutionCard surfaces the gap.
"""
from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from agentdex_engine.cards import TaskCard
from agentdex_engine.oracle.base import Oracle


class ConfusionMatrixRow(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    predicted: bool
    expected: bool
    count: int = Field(ge=0)


class CalibrationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    n_samples: int = Field(ge=0)
    accuracy: float = Field(ge=0.0, le=1.0)
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    kappa: float = Field(ge=-1.0, le=1.0)
    confusion_matrix_rows: list[ConfusionMatrixRow]
    passed_calibration: bool


def _cohen_kappa(yes_yes: int, yes_no: int, no_yes: int, no_no: int) -> float:
    n = yes_yes + yes_no + no_yes + no_no
    if n == 0:
        return 0.0
    po = (yes_yes + no_no) / n
    p_pred_yes = (yes_yes + yes_no) / n
    p_exp_yes = (yes_yes + no_yes) / n
    pe = p_pred_yes * p_exp_yes + (1 - p_pred_yes) * (1 - p_exp_yes)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1.0 - pe)


def calibrate(
    judge: Oracle,
    fixtures: Iterable[tuple[str, float, bool]],
    *,
    task_card: TaskCard,
    verdict_key: str = "soft.narrative_coherence",
    min_accuracy: float = 0.7,
) -> CalibrationReport:
    """Run ``judge.evaluate`` over fixtures + compare ``pass_`` against label.

    fixtures: iterable of ``(response_text, expected_score, expected_pass)``.
    """
    samples = list(fixtures)
    yes_yes = yes_no = no_yes = no_no = 0
    for response, _expected_score, expected_pass in samples:
        verdicts = judge.evaluate(response, task_card)
        verdict = verdicts.get(verdict_key)
        predicted_pass = bool(verdict.pass_) if verdict else False
        if predicted_pass and expected_pass:
            yes_yes += 1
        elif predicted_pass and not expected_pass:
            yes_no += 1
        elif not predicted_pass and expected_pass:
            no_yes += 1
        else:
            no_no += 1

    n = len(samples)
    accuracy = (yes_yes + no_no) / n if n else 0.0
    precision = yes_yes / (yes_yes + yes_no) if (yes_yes + yes_no) else 0.0
    recall = yes_yes / (yes_yes + no_yes) if (yes_yes + no_yes) else 0.0
    kappa = _cohen_kappa(yes_yes, yes_no, no_yes, no_no)
    return CalibrationReport(
        n_samples=n,
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        kappa=kappa,
        confusion_matrix_rows=[
            ConfusionMatrixRow(predicted=True, expected=True, count=yes_yes),
            ConfusionMatrixRow(predicted=True, expected=False, count=yes_no),
            ConfusionMatrixRow(predicted=False, expected=True, count=no_yes),
            ConfusionMatrixRow(predicted=False, expected=False, count=no_no),
        ],
        passed_calibration=accuracy >= min_accuracy,
    )
