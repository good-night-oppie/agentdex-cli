"""Phase-6 Oracle tests — hard (number / provenance), soft (mock LLM), repair flagger."""

from __future__ import annotations

import json
from pathlib import Path

from agentdex_engine.cards import (
    EvolutionCard,
    Seed,
    TaskCard,
)
from agentdex_engine.oracle.base import (
    OracleChain,
    OracleVerdict,
)
from agentdex_engine.oracle.calibration import CalibrationReport, calibrate
from agentdex_engine.oracle.hard import (
    NumberAccuracyOracle,
    ProvenanceOracle,
)
from agentdex_engine.oracle.repair import OracleRepairFlagger
from agentdex_engine.oracle.soft import LlmJudgeOracle

REPO_ROOT = Path(__file__).resolve().parents[3]
NVIDIA_SPEC = REPO_ROOT / "tasks" / "nvidia-earnings-infographic" / "oracle" / "spec.yaml"


def _build_task_card(task_id: str = "nvidia-earnings-infographic-q3-fy2026") -> TaskCard:
    return TaskCard(
        id=task_id,
        source_bundle_hash="2f3bf8fee53690f76e4701a5097aabb3e19f5bb146a136fe95a2b8d7169c3346",  # pragma: allowlist secret
        environment_spec={"runtime": "agentdex-cli >=0.1.0", "output_kind": "infographic"},
        oracle_spec_ref="tasks/nvidia-earnings-infographic/oracle/spec.yaml",
        budget_token_cap=200000,
        budget_dollar_cap=5.0,
        expected_output_kind="infographic",
        version="0.1.0",
    )


# ---------------------------------------------------------------------------
# Hard Oracle — NumberAccuracyOracle
# ---------------------------------------------------------------------------


def test_number_accuracy_pass():
    """Synthetic response with all correct numbers → hard pass-rate high."""
    oracle = NumberAccuracyOracle(NVIDIA_SPEC)
    response = (
        "Q3 FY2026 NVIDIA revenue was $35.08 billion, up substantially. "
        "Data Center revenue: $30.77 billion, up 112% YoY. "
        "GAAP gross margin: 74.6%. Q4 guidance: $37.5 billion ± 2%. "
        "Capex: $1.85 billion. Inventory rose 11% QoQ. "
        "China revenue $5.40 billion (16%). Blackwell and Rubin ramp continue."
    )
    verdicts = oracle.evaluate(response, _build_task_card())
    passed = [v for v in verdicts.values() if v.pass_]
    assert len(passed) >= 5, (
        f"expected ≥5 hard verdicts to pass, got {[(k, v.pass_) for k, v in verdicts.items()]}"
    )


def test_number_accuracy_fail_wrong_revenue():
    """Wrong revenue → hard verdict for revenue_total fails."""
    oracle = NumberAccuracyOracle(NVIDIA_SPEC)
    response = (
        "Q3 FY2026 NVIDIA revenue was $99.99 billion. "  # wrong on purpose
        "Data Center revenue: $30.77 billion. "
        "GAAP gross margin: 74.6%."
    )
    verdicts = oracle.evaluate(response, _build_task_card())
    rev = verdicts.get("hard.revenue_total")
    assert rev is not None, "revenue_total verdict missing"
    assert rev.pass_ is False, f"expected revenue_total to FAIL, got {rev!r}"
    assert "$35.08" in rev.evidence or "35.08" in rev.evidence


# ---------------------------------------------------------------------------
# Hard Oracle — ProvenanceOracle
# ---------------------------------------------------------------------------


def test_provenance_missing_fails():
    response = "- Revenue: $35.08 billion\n- Data Center: $30.77 billion\n- Gross margin: 74.6%\n"
    verdicts = ProvenanceOracle().evaluate(response, _build_task_card())
    v = verdicts["hard.provenance_required"]
    assert v.pass_ is False
    assert v.score == 0.0


def test_provenance_present_passes():
    response = (
        "- Revenue: $35.08 billion (source: nvidia-q3-fy2026-press-release.md:14)\n"
        "- Data Center: $30.77 billion (source: nvidia-q3-fy2026-press-release.md:26)\n"
        "- Gross margin: 74.6% (source: nvidia-q3-fy2026-press-release.md:42)\n"
    )
    verdicts = ProvenanceOracle().evaluate(response, _build_task_card())
    v = verdicts["hard.provenance_required"]
    assert v.pass_ is True
    assert v.score >= 0.9


def test_provenance_per_bullet_citation_count_no_prose_inflation():
    """Regression (codereview C1): live LLM emits citations BOTH inside bullet
    claims AND in surrounding prose. Score must reflect per-bullet provenance
    fraction, not a global-citation-count / bullet ratio that would inflate
    past 1.0 and trip pydantic le=1. 4 bullets w/ citations + 4 prose citations
    → ratio=4/4=1.0; clamp must not be needed."""
    response = (
        "Summary: NVIDIA had a strong Q3 (source: a.md:1) with revenue growth (source: a.md:2).\n"
        "- Revenue: $35.08 billion (source: a.md:14)\n"
        "- Data Center: $30.77 billion (source: a.md:26)\n"
        "- Gross margin: 74.6% (source: a.md:42)\n"
        "- Guidance: $37.5 billion ± 2% (source: a.md:60)\n"
        "Additional context (source: a.md:88) — Blackwell ramp (source: a.md:92).\n"
    )
    verdicts = ProvenanceOracle().evaluate(response, _build_task_card())
    v = verdicts["hard.provenance_required"]
    assert 0.0 <= v.score <= 1.0, f"score {v.score} outside [0,1]"
    assert v.score == 1.0, f"all 4 bullets carry citations → ratio must be 1.0, got {v.score}"
    assert v.pass_ is True
    assert "4/4" in v.evidence, f"evidence should report per-bullet count, got {v.evidence!r}"


def test_provenance_partial_bullet_citation_fails():
    """Half of the bullets miss a citation → ratio=0.5 < 0.9 → fails. Verifies
    per-bullet count discriminates partial coverage."""
    response = (
        "- Revenue: $35.08 billion (source: a.md:14)\n"
        "- Data Center: $30.77 billion\n"
        "- Gross margin: 74.6% (source: a.md:42)\n"
        "- Guidance: $37.5 billion ± 2%\n"
    )
    verdicts = ProvenanceOracle().evaluate(response, _build_task_card())
    v = verdicts["hard.provenance_required"]
    assert v.pass_ is False
    assert 0.49 <= v.score <= 0.51, f"expected ratio≈0.5, got {v.score}"


def test_provenance_numbered_list_counts_as_claim_lines():
    """MF6 regression (harness-praxis tracer): LLM emits numbered enumeration
    (`1. `, `2) `, etc.) instead of bullet markers. Per-bullet count must
    treat these as claim lines too, else perfectly-cited numbered responses
    were forced to score=0.0/pass=False."""
    response = (
        "1. Revenue: $35.08 billion (source: nvidia-q3-fy2026-press-release.md:14)\n"
        "2. Data Center: $30.77 billion (source: nvidia-q3-fy2026-press-release.md:26)\n"
        "3) Gross margin: 74.6% (source: nvidia-q3-fy2026-press-release.md:42)\n"
        "4) Guidance: $37.5 billion ± 2% (source: nvidia-q3-fy2026-press-release.md:60)\n"
    )
    verdicts = ProvenanceOracle().evaluate(response, _build_task_card())
    v = verdicts["hard.provenance_required"]
    assert v.pass_ is True, f"expected pass on fully-cited numbered list; got {v}"
    assert v.score == 1.0, (
        f"all 4 numbered claims carry citations → ratio must be 1.0, got {v.score}"
    )
    assert "4/4" in v.evidence, f"evidence should report per-bullet count, got {v.evidence!r}"


def test_provenance_lettered_list_counts_as_claim_lines():
    """Lettered enumeration (`a. `, `b) `, `i. ` Roman) also counts. Without
    this, response styles common in legal / structured reporting fail the
    Oracle for purely-formatting reasons."""
    response = (
        "a. Revenue: $35.08 billion (source: a.md:14)\n"
        "b. Data Center: $30.77 billion (source: a.md:26)\n"
        "i. Gross margin: 74.6% (source: a.md:42)\n"
        "ii. Guidance: $37.5 billion (source: a.md:60)\n"
    )
    verdicts = ProvenanceOracle().evaluate(response, _build_task_card())
    v = verdicts["hard.provenance_required"]
    assert v.pass_ is True
    assert v.score == 1.0


def test_provenance_capitalised_initials_in_prose_not_counted_as_claims():
    """C3 regression (workflow w0z1i9vcs): the MF6 regex allowed any single
    ASCII letter + `[.)]` which promoted prose lines like `J. Huang (CEO)
    said the quarter was strong.` and `I. saw the report.` to claim lines.
    Realistic NVIDIA-style response: 3 cited bullets + 2 prose initials →
    if J./I./M. count as claims, ratio = 3/5 = 0.6 → flips PASS to FAIL.
    The C3-tightened regex rejects capitalised letter + period."""
    response = (
        "J. Huang (CEO) said the quarter was strong.\n"
        "M. Smith (CFO) added that margins held up.\n"
        "- Revenue: $35.08 billion (source: nvidia-q3-fy2026-press-release.md:14)\n"
        "- Gross margin: 74.6% (source: nvidia-q3-fy2026-press-release.md:42)\n"
        "- Guidance: $37.5 billion (source: nvidia-q3-fy2026-press-release.md:60)\n"
        "I. saw the deck briefly.\n"
    )
    verdicts = ProvenanceOracle().evaluate(response, _build_task_card())
    v = verdicts["hard.provenance_required"]
    assert v.pass_ is True, (
        f"expected pass — 3 bullet claims all cited; prose initials must NOT "
        f"inflate denominator. Got verdict {v}"
    )
    assert v.score == 1.0, f"3 bullet claims, 3 citations → ratio 3/3 = 1.0; got {v.score}"
    assert "3/3" in v.evidence, f"evidence should report 3/3 bullet count, got {v.evidence!r}"


def test_provenance_prose_only_returns_indeterminate_evidence():
    """Response is all prose with citations but no bullets — Oracle cannot
    verify per-claim provenance. Returns pass=False with score=0 + evidence
    that distinguishes the prose-only case from the no-citation case so
    downstream Repair Oracle / human reviewer sees the structural mismatch."""
    response = (
        "NVIDIA Q3 FY2026 revenue was $35.08 billion "
        "(source: nvidia-q3-fy2026-press-release.md:14) with Data Center at "
        "$30.77 billion (source: nvidia-q3-fy2026-press-release.md:26) and "
        "gross margin 74.6% (source: nvidia-q3-fy2026-press-release.md:42)."
    )
    verdicts = ProvenanceOracle().evaluate(response, _build_task_card())
    v = verdicts["hard.provenance_required"]
    assert v.pass_ is False
    assert v.score == 0.0
    assert "indeterminate" in v.evidence.lower(), (
        f"prose-only evidence should be flagged indeterminate, got {v.evidence!r}"
    )


# ---------------------------------------------------------------------------
# Soft Oracle — LlmJudgeOracle with mocked client
# ---------------------------------------------------------------------------


class _MockAnthropicMessage:
    def __init__(self, text: str):
        block = type("B", (), {"text": text})
        self.content = [block]


class _MockAnthropicMessages:
    def __init__(self, response_text: str, recorder: dict):
        self._response = response_text
        self._recorder = recorder

    def create(self, *, model, max_tokens, system, messages):
        self._recorder.update(
            {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}
        )
        return _MockAnthropicMessage(self._response)


class _MockAnthropicClient:
    def __init__(self, judge_json: dict, recorder: dict):
        self.messages = _MockAnthropicMessages(json.dumps(judge_json), recorder)


def test_llm_judge_with_mock():
    recorder: dict = {}
    judge_json = {
        "score": 0.82,
        "uncertainty": 0.15,
        "pass": True,
        "rationale": "Response captures revenue + margin coherently.",
    }
    client = _MockAnthropicClient(judge_json, recorder)
    oracle = LlmJudgeOracle(
        judge_llm="claude-haiku-4.5",
        rubric_path=None,
        client_factory=lambda: client,
    )
    verdicts = oracle.evaluate(
        "Revenue $35.08B; gross margin 74.6%; data center $30.77B.",
        _build_task_card(),
    )
    v = verdicts["soft.narrative_coherence"]
    assert isinstance(v, OracleVerdict)
    assert v.kind == "soft"
    assert v.pass_ is True
    assert 0.0 <= v.score <= 1.0
    assert v.uncertainty is not None and 0.0 <= v.uncertainty <= 1.0
    assert recorder["model"] == "claude-haiku-4.5", (
        "judge_llm model id must be passed through verbatim"
    )


def test_llm_judge_handles_garbage_output():
    """Judge returns non-JSON → Oracle emits a low-confidence fail verdict."""
    recorder: dict = {}
    client = _MockAnthropicClient({}, recorder)
    client.messages = type(
        "Garbage",
        (),
        {"create": lambda self, **_kw: _MockAnthropicMessage("totally not json")},
    )()
    oracle = LlmJudgeOracle(
        judge_llm="claude-haiku-4.5",
        client_factory=lambda: client,
    )
    verdicts = oracle.evaluate("dummy", _build_task_card())
    v = verdicts["soft.narrative_coherence"]
    assert v.pass_ is False
    assert v.uncertainty == 1.0


# ---------------------------------------------------------------------------
# Repair Oracle — R6 truth-in-advertising assertion
# ---------------------------------------------------------------------------


def test_repair_flagger_emits_structural_seed_for_uncertain_soft():
    verdicts = {
        "soft.narrative_coherence": OracleVerdict(
            kind="soft",
            **{"pass": False},
            score=0.4,
            evidence="judge disagreed with itself across reruns",
            uncertainty=0.75,
        ),
    }
    seeds = OracleRepairFlagger().emit_seeds(verdicts)
    assert "harness" in seeds, f"expected harness category, got keys={list(seeds)}"
    seed: Seed = seeds["harness"][0]
    assert seed.seed_provenance == "structural", (
        "R6 truth-in-advertising: repair seeds must carry "
        "seed_provenance='structural' (M7 raises bar to 'learned')"
    )
    assert seed.kind == "oracle_repair"
    assert seed.confidence == "high"


def test_repair_flagger_emits_provenance_seed():
    verdicts = {
        "hard.provenance_required": OracleVerdict(
            kind="hard",
            **{"pass": False},
            score=0.0,
            evidence="0/5 claim lines carry source annotation",
        ),
    }
    seeds = OracleRepairFlagger().emit_seeds(verdicts)
    assert "source" in seeds
    seed: Seed = seeds["source"][0]
    assert seed.kind == "provenance_required"
    assert seed.seed_provenance == "structural"


def test_repair_flagger_evolution_card_two_categories():
    """M5 gate: ≥2 mutation seed categories satisfied by structural seeds alone."""
    verdicts = {
        "soft.narrative_coherence": OracleVerdict(
            kind="soft",
            **{"pass": False},
            score=0.5,
            evidence="noisy judge",
            uncertainty=0.7,
        ),
        "hard.provenance_required": OracleVerdict(
            kind="hard",
            **{"pass": False},
            score=0.2,
            evidence="provenance gap",
        ),
    }
    seeds = OracleRepairFlagger().emit_seeds(verdicts)
    assert len(seeds) >= 2, f"expected ≥2 seed categories, got {list(seeds)}"
    card = EvolutionCard(
        expedition_id="test-expedition",
        parent_lineage_root=None,
        winning_pattern="dummy",
        losing_pattern="dummy",
        mutation_seeds=seeds,
        boundary_annotations=[],
        langfuse_trace_urls={},
    )
    assert len(card.mutation_seeds) >= 2


# ---------------------------------------------------------------------------
# Oracle chain composition
# ---------------------------------------------------------------------------


def test_oracle_chain_namespaces_keys():
    response = (
        "- Revenue: $35.08 billion (source: nvidia-q3-fy2026-press-release.md:14)\n"
        "- Gross margin: 74.6% (source: nvidia-q3-fy2026-press-release.md:42)\n"
    )
    chain = OracleChain({"number": NumberAccuracyOracle(NVIDIA_SPEC), "prov": ProvenanceOracle()})
    verdicts = chain.evaluate(response, _build_task_card())
    assert any(k.startswith("number.") for k in verdicts)
    assert any(k.startswith("prov.") for k in verdicts)


# ---------------------------------------------------------------------------
# Calibration harness — confusion matrix + accuracy gate
# ---------------------------------------------------------------------------


class _DeterministicJudge:
    """Stub Oracle that returns a fixed verdict per response keyword."""

    def __init__(self, keyword: str, base_score: float):
        self._kw = keyword
        self._score = base_score

    def evaluate(self, response: str, task_card: TaskCard):
        hit = self._kw in response
        return {
            "soft.narrative_coherence": OracleVerdict(
                kind="soft",
                **{"pass": hit},
                score=self._score if hit else 0.0,
                evidence=f"keyword={self._kw} hit={hit}",
                uncertainty=0.1,
            )
        }


def test_calibrate_returns_report():
    judge = _DeterministicJudge(keyword="revenue", base_score=0.85)
    fixtures = [
        ("revenue is up", 0.9, True),
        ("revenue is down but solid", 0.85, True),
        ("no relevant content", 0.1, False),
        ("revenue dominant theme", 0.9, True),
        ("blank report", 0.05, False),
    ]
    report = calibrate(judge, fixtures, task_card=_build_task_card())
    assert isinstance(report, CalibrationReport)
    assert report.n_samples == 5
    assert report.accuracy == 1.0
    assert report.passed_calibration is True
    assert sum(r.count for r in report.confusion_matrix_rows) == 5
