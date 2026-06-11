---
title: "EVAL — agentdex-cli"
status: active
owner: "@EdwardTang"
created: 2026-06-09
updated: 2026-06-11
type: reference
scope: .
layer: cross-cutting
cross_cutting: true
enforced_by:
  - "pytest golden gates (tests/golden/ + test_expedition_smoke.py; arena: tests/golden/arena/)"
  - "lint.yml CI required checks (pre-commit + doc-lint)"
  - "pydantic ConfigDict(extra='forbid', strict=True) at validate-time (Three Cards)"
  - "launch-blocking CI job on tests/redteam/injection_corpus.yaml (phase 8)"
---

# EVAL — agentdex-cli

> LangChain G13: eval signal design is the hardest part of harness engineering. Bad signal → automated optimization amplifies error. Every criterion below MUST trace to a line in `IDEAL_EXPERIENCE.md`.

## Ground-truth dataset

- **Location:** `tests/golden/`
- **Curation policy:** human-labeled, versioned, append-only. Each YAML row is hand-annotated against the source bundle at `tasks/<task-id>/sources/`.
- **Size target:** ≥1 case for MVP smoke (Q3 FY2026 NVIDIA, populated in P3); ≥10 for confidence (post-M5); ≥100 for autonomy-flip (per `AUTONOMY_THRESHOLD.md`).
- **Anchor file:** `tests/golden/nvidia_pareto_expected.yaml` — golden expected ParetoVerdict + EvolutionCard shape for the Q3 FY2026 NVIDIA bundle. Used by Phase 7 mocked smoke test to verify pipeline shape; live-run wins/losses can diverge but the verdict structure (winner|no_clear_winner + ≥2 mutation_seed categories with `seed_provenance` set) is invariant.

## Eval criteria

| Criterion | Anchor (IDEAL_EXPERIENCE.md line) | Signal | GT source |
|-----------|-----------------------------------|--------|-----------|
| Reproducible Expedition (same bundle → same Pareto shape) | "User feels: certain" + Failure mode #2 | `pareto_verdict.yaml` matches `tests/golden/nvidia_pareto_expected.yaml` structurally (winner present OR `no_clear_winner`; ≥2 mutation_seed categories) | `tests/golden/nvidia_pareto_expected.yaml` |
| Trace continuity (judge span parented OR per-baseline-root w/ cross-links) | "User feels: certain" + Failure mode #3 | Phase-4 R3 spike outcome doc states pass/fail; Phase-7 acceptance asserts trace_id presence on every ResultCard | Phase-4 spike test + Langfuse mock assertions in `test_expedition_smoke.py` |
| Seed-provenance typed honesty (every seed has non-null `seed_provenance ∈ {structural,learned}`) | Failure mode #4 + ADR-0009 §D5 M5 gate | `evolution_card.yaml`'s seeds all carry the field; `pydantic ConfigDict(extra="forbid", strict=True)` enforces at validate-time | Three Cards pydantic schema (`cards-mvp/evolution_card.py` Seed model) |
| Oracle hard-claim accuracy on NVIDIA Q3 FY2026 (≥7/9 numeric claims correct) | "User feels: certain" + Failure mode #1 (reward hack) | `pass_rate ≥ 0.78` on the hard-Oracle gate per `oracle/spec.yaml` | `tasks/nvidia-earnings-infographic/oracle/spec.yaml` + `expected_outputs/sample-claim-evidence-map.yaml` |
| Soft-Oracle judge calibration ≥ 0.7 accuracy on ≥10 labeled fixtures | Failure mode #1 + Phase-6 calibration spec | `oracle/calibration.py::calibrate()` CalibrationReport.accuracy ≥ 0.7 | Hand-labeled fixtures in `packages/agentdex_engine/tests/oracle_calibration_fixtures/` (P6) |
| Single-gateway invariant (1 hermes gateway PID during expedition) | "User runs / agentdex-cli does" lines | `ps -ef \| grep hermes.*gateway \| wc -l == 1` during live run | Process listing during `adx expedition` |
| Subscription-CLI bridge smoke probe passes at session start | Failure mode #5 | each bridge's `smoke()` returns `{ok: true, version: <str>}` before any turn | Recorded fixture (`tests/fixtures/bridges/{claude,codex,manus}_smoke.json`) |

## §Arena eval criteria (ADR-0010 — anchored to IDEAL_EXPERIENCE.md §Arena clauses)

| Criterion | Anchor (IDEAL §Arena) | Signal | GT source |
|-----------|----------------------|--------|-----------|
| Deterministic battles (same seed → same winner; inputLog re-simulates identically) | A2 | golden fixtures pass in CI, no network | `tests/golden/arena/` (phase 3) |
| Sanitizer strips injection payloads at parse boundary | A6 | every `tests/redteam/injection_corpus.yaml` payload neutralized; launch-blocking CI job | injection corpus (phase 3/8) |
| Rated events carry re-simulable inputLog hash, server-matchmade only | A2, A3 | ladder rejects events without hash; `/challenge` asserted unrated in test | ladder unit tests (phase 5/8) |
| Anchor calibration: random < max-damage < heuristics, non-overlapping 2·RD in ≤200 battles | A4, A8 | calibration report committed; nightly self-test halts publication on ordering failure | scripted-bot battles (phase 5) |
| Ratings recompute byte-identically from the external event log | A8 | fresh-checkout recompute equals published state | `events.jsonl` + durable store (phase 5/9) |
| No published delta < 2·RD | A4 | API/page render asserts; unit test on boundary | ladder API tests (phase 5) |
| Flat per-turn context: turn-30 context == turn-3 context ±10% over 50+ turns | A7 | CI assertion on fixture battle; state renderer ≤2,500 tokens on corpus | renderer fixtures (phase 6) |
| Evolution verdicts computed only at the NEXT window (no self-certification); HARMFUL auto-rolls back | A5 | injected one-Pokémon nerf detected HARMFUL in ≤50 CRN paired battles; rollback chaos-drill transcript | CRN regression test (phase 7) |
| Enrollment requires human out-of-band action | A1 | agent-only enrollment attempt fails in test | consent flow tests (phase 8) |
| House LLM spend fail-closed | A7 | circuit-breaker test: budget exhausted → battles refused, not degraded | gateway tests (phase 8) |

## Self-judge guardrails (G13)

- **NO LLM-judges-LLM without ground-truth anchor.** Every soft-Oracle judge call is calibrated against hand-labeled fixtures (P6 `oracle/calibration.py`). If accuracy < 0.7 on backtest, judge cannot be used as M5 gate; it can still run as a `seed_provenance="structural"` signal for Phase-7's repair flagger.
- **Inter-rater agreement > 0.7 required before promoting eval to gate.** For MVP M5, only the structural-seed gate is a hard gate; learned-seed thresholds wait for M7's seed_extractor where κ measurement is meaningful.
- **No metric without anchor.** Any criterion proposed without an `IDEAL_EXPERIENCE.md` line reference is rejected at code review time.

## Eval gating

- PR cannot auto-merge if eval score drops on golden set (`tests/golden/`).
- See `agents/review/AGENTS.md` for merge policy (async gates per G2 ep5+7).
- For MVP M0–M5, the smoke test (`test_expedition_smoke.py`) is the gate; full scoring requires post-M5 fixture pool.

## Ablation evidence (G9 Anthropic Prithvi)

Every harness component must have ablation justification — "if we remove X, eval Y drops by Z." Components without ablation evidence are candidates for pruning.

| Component | Ablation hypothesis | Keep until proven? | Measurement plan |
|-----------|---------------------|---------------------|------------------|
| `agentdex_observe` Langfuse wrap | Removing it makes traces orphan-root; trace continuity criterion fails | Keep — directly anchors Failure mode #3 | Phase-4 R3 spike test toggles on/off |
| Hard Oracle (`oracle/hard.py`) | Removing it lets Pareto judge on soft-only verdicts; reward-hack risk spikes | Keep — anchors Failure mode #1 | Phase-7 manual ablation: run with soft-only chain, observe seed_provenance distribution |
| Soft Oracle calibration backtest (`oracle/calibration.py`) | Removing it ships uncalibrated judge → noise in Pareto → Evolution noise | Keep — Failure mode #1 mitigation | Phase-6 implements; backtest is the ablation |
| Pareto judge (`evolver/pareto.py`) | Removing it ships per-baseline ResultCards without verdict; M5 acceptance fails | Keep — IDEAL_EXPERIENCE "Pareto winner" line | Pareto absence test in `test_expedition_smoke.py` |
| Single-gateway invariant | Removing it lets per-baseline gateways spawn; trace topology fractures + resource cost spikes | Keep — Failure mode #5 prevention | Phase-7 `ps wc -l == 1` check is the ablation gate |
| KAOS lineage persistence (`Kaos(db).experiments.log`) | Removing it loses cross-Expedition lineage; Pokédex history breaks | Keep — Pokédex framing core | M7+ lineage tree depth measurement |
| Three Cards `extra="forbid", strict=True` | Removing it lets silent field-drift in Pareto downstream | Keep — Failure mode #4 mechanism | Phase-2 negative-fixture tests are the ablation evidence (already 3 fail-cases per Card) |
| Seed `seed_provenance` field | Removing it lets M5 gate pass on mechanical seeds without honesty label | Keep — Failure mode #4 mitigation | Phase-7 transcript asserts non-null on every seed |
