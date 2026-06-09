---
title: Oracle calibration fixtures (G13 ground-truth)
status: active
owner: "@EdwardTang"
created: 2026-06-09
updated: 2026-06-09
type: reference
scope: packages/agentdex_engine/tests/oracle_calibration_fixtures
layer: cross-cutting
cross_cutting: true
---

# Oracle calibration fixtures (G13 ground-truth)

Referenced by `EVAL.md` row "Soft-Oracle judge calibration ≥ 0.7 accuracy on
≥10 labeled fixtures". Each row is a hand-labeled (response, expected_pass,
expected_score) triple that `oracle/calibration.py::calibrate()` reads to
produce a confusion-matrix-backed `CalibrationReport`.

## Why these files exist (now empty)

The harness-praxis tracer pass (2026-06-09) surfaced that `EVAL.md:20` named
this directory but the directory did not exist. Per harness-praxis §G13
"eval signal", a missing ground-truth dataset turns the calibration gate
into theater: the soft Oracle ships uncalibrated and any LLM-as-judge claim
about agentdex-cli is unverifiable. This README + the schema below convert
that gap into bounded debt with a typed shape.

## File layout

```
oracle_calibration_fixtures/
├── README.md                       # this file
├── narrative_coherence/
│   ├── pass_high_confidence.yaml   # 4 rows, score ≥ 0.85, hand-labeled pass
│   ├── pass_marginal.yaml          # 3 rows, score 0.70-0.80, hand-labeled pass
│   ├── fail_marginal.yaml          # 3 rows, score 0.40-0.55, hand-labeled fail
│   ├── fail_obvious.yaml           # 4 rows, score ≤ 0.20, hand-labeled fail
│   └── labels_rater_2.yaml         # AI rater-2 labels for the κ ≥ 0.7 gate
└── infographic_accuracy/           # post-M6 — second dimension once M5 lands
    └── (mirrored layout)
```

Total: 13 fixtures + a rater-2 sidecar = enough for the EVAL.md ≥ 10 rows
× 2 raters κ ≥ 0.7 inter-rater agreement gate enforced by
`test_inter_rater_kappa.py`.

Total ≥ 14 rows across the four narrative-coherence files = exceeds the
`EVAL.md` minimum of 10.

## Schema (per YAML file)

```yaml
# narrative_coherence/pass_high_confidence.yaml — example shape, NOT YET REAL
schema_version: 1
dimension: narrative_coherence
fixtures:
  - id: nvidia-q3-fy2026-clean-bullet-list
    task_id: nvidia-earnings-infographic-q3-fy2026
    response: |
      - Revenue: $35.08 billion (source: nvidia-q3-fy2026-press-release.md:14)
      - Data Center: $30.77 billion (source: nvidia-q3-fy2026-press-release.md:26)
      - Gross margin: 74.6% (source: nvidia-q3-fy2026-press-release.md:42)
      - Q4 outlook: $37.5 billion ± 2% (source: nvidia-q3-fy2026-press-release.md:60)
    expected_pass: true
    expected_score: 0.90               # single point — matches calibrate() Iterable[tuple[str, float, bool]]
    expected_uncertainty_max: 0.20     # advisory; calibrate() does not consume yet (post-M6 hook)
    label_author: eddie@oppie.xyz
    label_rationale: |
      All four required infographic claim categories present, every claim
      carries `source: <file>:<line>` provenance, narrative flow groups by
      revenue → margin → outlook in the order the IDEAL_EXPERIENCE.md
      reference infographic expects.
    captured_at: 2026-06-09
```

## How calibrate() consumes these

Per `packages/agentdex_engine/src/agentdex_engine/oracle/calibration.py`:

```python
report = calibrate(
    judge=LlmJudgeOracle(judge_llm="claude-haiku-4.5", rubric_path="..."),
    fixtures=[(row["response"], row["expected_score"], row["expected_pass"])
              for f in glob("narrative_coherence/*.yaml")
              for row in yaml.safe_load(open(f))["fixtures"]],
    task_card=task_card_for("nvidia-earnings-infographic-q3-fy2026"),
)
assert report.accuracy >= 0.7
```

The fixture row shape is a one-to-one match of the `calibrate()`
signature: `(response: str, expected_score: float, expected_pass: bool)`.
No band → point hand-mapping (H6 workflow-review fix 2026-06-09).

Inter-rater κ ≥ 0.7 (per `EVAL.md` self-judge guardrails) requires every
row to carry an independent second label before the calibration gate becomes
M5 → M7 promotion-eligible. The second label lives in a sibling
`secondary_label:` block on each fixture (post-M6 fixture flesh-out).

## Why these are NOT golden answers

The fixtures encode the EXPECTED JUDGE BEHAVIOR, not the EXPECTED MODEL
ANSWER. A fixture row says "given THIS response, the soft judge should grade
in THIS band". The judge is the system-under-test; the response is the
input; the band is the contract. This is the calibration distinction
Anthropic Prithvi G9 ablation talk uses to keep eval signal from collapsing
into reward-hacked LLM-judges-LLM circularity.

## Status

- 2026-06-09 — directory + schema scaffolded by the harness-praxis tracer
  follow-up (MF4 gap). Hand-labeled fixtures land with the Phase 6 soft
  Oracle calibration work.
