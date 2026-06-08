# Chart Sanity Rubric (Soft Oracle) — NVIDIA Q3 FY2026 Infographic

> Soft Oracle judge LLM scores infographic descriptions against this rubric. Per ADR-0008 §judge-as-profile MVP downgrade contract, the judge is invoked via `agentdex_observe.anthropic_client().messages.create(model="claude-haiku-4.5", ...)` in the same Python process; Langfuse auto-instruments the call as span `oracle.soft_judge` with parent = Expedition trace.

> Scoring range: 0.0 (fails rubric) → 1.0 (passes all items). Uncertainty score reported separately; uncertainty > 0.5 emits an `oracle_repair` mutation seed with `seed_provenance="structural"`.

## Rubric items

1. **Axis labels match source units** — Revenue values labeled in USD billions (not millions, not "B" without unit context). Quarter labels match fiscal calendar (Q3 FY2026, not "Q3 2026"). Failure mode: mislabeled axis amplifies numeric error perception.

2. **Comparison baseline is correctly named** — YoY comparisons explicitly cite the year-ago period (Q3 FY2025 = $18.15B total revenue). QoQ comparisons cite the prior quarter (Q2 FY2026). Failure mode: ambiguous "growth" claim without baseline = unfalsifiable.

3. **Segment breakdown sums to total** — Data Center + Gaming + ProViz + Auto + OEM/Other = Total revenue. If pie/bar chart presents segments, they must add up. Failure mode: segment math drift breaks Oracle hard-claim verification.

4. **Color choice aids comparison, doesn't mislead** — Use a sequential or categorical palette appropriate to the data. Avoid red-green only (accessibility). Highlight color (e.g., for the winning baseline metric) should be intentional, not arbitrary. Failure mode: misleading color encodes a verdict the data doesn't support.

5. **Guidance forward-looking statements clearly marked** — Q4 FY2026 guidance numbers (revenue $37.5B ± 2%) MUST be visually distinguished from actuals. Failure mode: presenting guidance as actual is materially misleading.

6. **China disclosure handled with appropriate context** — China revenue ($5.40B, 16% of total) requires context (export-control regime, compliant SKU mix). A bare China number without context is incomplete reporting.

7. **Blackwell + Rubin product narrative coherent** — Roadmap visual (Hopper end-of-life, Blackwell volume ramp, Rubin sampling H2 CY2026) is timeline-correct. Failure mode: product family overlap drift breaks the narrative arc and the boundary_annotations in EvolutionCard.

8. **No misleading scale or truncation** — Y-axis starts at zero for revenue/margin bar charts. Truncated axes (e.g., 73-75% gross margin range) must be explicit and labeled. Failure mode: visual exaggeration of small deltas is a known reward-hack pattern for "winning" infographics.

## Scoring guidance for LLM judge

For each rubric item, judge assigns:
- `pass: bool` — does the infographic description satisfy the item?
- `confidence: Literal["low", "med", "high"]` — judge confidence in its assessment
- `evidence: str` — quote from infographic description that anchors the verdict

Aggregate score = sum(pass) / 8. Uncertainty = mean(1.0 - confidence_numeric) where confidence_numeric ∈ {0.33, 0.66, 1.0}.

## Calibration backtest expectation

`oracle/calibration.py::calibrate(rubric=this_file, fixtures=...)` runs the judge against ≥10 hand-labeled (infographic_description, expected_pass_per_rubric) fixtures. CalibrationReport.accuracy ≥ 0.7 required for soft-Oracle path to gate M5. Below 0.7 → judge invocation still runs but verdict is downgraded to a `seed_provenance="structural"` repair seed; M5 gate falls back to hard-Oracle-only path.
