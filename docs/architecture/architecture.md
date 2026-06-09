---
title: agentdex-cli architecture
status: active
owner: etang
created: 2026-06-09
updated: 2026-06-09
type: architecture
scope: monorepo
layer: cross-cutting
cross_cutting: true
verifiable_claims:
  - id: VC-001
    claim: "7-package uv workspace assembles cleanly from pyproject.toml"
    verifier: "uv sync && python -c 'import agentdex_engine, adx_bridges, agentdex_observe, agentdex_cli, agentdex_plugin, helios_client, kaos'"
  - id: VC-002
    claim: "Three Cards schema round-trips through YAML"
    verifier: "uv run --no-sync pytest packages/agentdex_engine/tests/ -k 'card or schema'"
  - id: VC-003
    claim: "Pareto excludes failed (cost_dollar=None) baselines from verdict pool"
    verifier: "uv run --no-sync pytest packages/agentdex_engine/tests/test_pareto.py::test_failed_baseline_excluded_from_verdict_pool"
  - id: VC-004
    claim: "Hermes plugin discoverable via entry-points"
    verifier: "python -c 'from importlib.metadata import entry_points; assert any(ep.name == \"agentdex\" for ep in entry_points(group=\"hermes_agent.plugins\"))'"
invariants:
  - "ResultCard.cost_dollar is float|None; None only on failure path (MF5)"
  - "Seed.seed_provenance ∈ {structural, learned}; M5 = all structural"
  - "BLAKE3 source_bundle_hash freeze → same bundle → same Pareto shape"
  - "Single hermes gateway PID during a baseline-run window (ADR-0009)"
---

# Architecture — agentdex-cli

> Doc-lint baseline (DOC-LINT-025). Point-in-time view of the live shape;
> source of truth for component contracts is the ADR cascade at
> `docs/adr/` (esp. ADR-0009).

## Architecture

This document IS the architecture overview. The sections below cover
TOOLS / ARCH / CONTEXT / Invariants / Guardrails per DOC-LINT-003 +
DOC-LINT-040.

## TOOLS

The runtime tooling stack (mirrored from `AGENTS.md`):

- **uv** — workspace package manager. 7 packages assembled via
  `pyproject.toml` `[tool.uv.workspace] members`.
- **pytest** — `tools/agent_senses/run_tests.sh` is the canonical
  invocation; CI gate is `.github/workflows/lint.yml`.
- **pre-commit** — `.pre-commit-config.yaml` configures ruff, mypy
  (cards/ strict scope), detect-secrets, sync_toc local hook.
- **doc_lint.py** — vendored from `~/gh/harness-engineering` (63 rules,
  `scripts/doc_lint.py`).
- **Hermes gateway** — `hermes gateway --profile agentdex` (spawn-once
  per expedition via PID-file at `~/.hermes/profiles/agentdex/`).
- **KAOS** — vendored at `packages/kaos/` (24.6k LOC subtree). Provides
  per-agent SQLite VFS + lineage entries.

## ARCH

Component inventory (per DOC-LINT-012):

| Package | Role | Strict layer |
|---|---|---|
| `packages/agentdex_engine` | Three Cards schema + Oracle layer + Pareto + Expedition orchestrator | `cards/` mypy strict |
| `packages/adx_bridges` | 5 bridges: base + claude + codex + manus (camoufox|codex-web fallback) + gemini stub | runtime |
| `packages/agentdex_observe` | Langfuse wrap + llm_pool + subscription_judge | runtime |
| `packages/agentdex_cli` | CLI + orchestrator + gateway helper | runtime |
| `packages/agentdex_plugin` | Hermes plugin glue (`hermes_agent.plugins` entry-point) | runtime |
| `packages/helios_client` | Python client for the M6+ helios hot tier (Go daemon, external sibling) | spec-only |
| `packages/kaos` | Vendored substrate (git subtree) | upstream |

End-to-end call flow (per `cron/expedition_smoke.sh` exercise + live-003
evidence):

```
adx expedition --task <id> --baselines <list> --judge <model>
  → cli.cmd_expedition
    → asyncio.run(_run_expedition)
      → run_expedition_orchestrator (engine)
        → ResourceBalancer.equalize → fairness_report
        → for each bridge SEQUENTIALLY:
            → bridge.send → bridge.chat
              → ensure_proc → handshake
              → _send_turn → result frame
              → returns (text, trace_id) + (last_cost_usd, last_tokens)
            → asyncio.to_thread(oracle.evaluate)
              → ProvenanceOracle + NumberAccuracyOracle + LlmJudgeOracle
                → _judge_observation Langfuse generation span
                → subscription_judge subprocess OR cliproxy OR direct SDK
            → ResultCard emit
        → pareto_verdict — excludes failed (cost_dollar=None) cards
        → OracleRepairFlagger.emit_seeds — structural seeds
        → _control_seed_from_response_variance
        → _build_evolution_card
    → _write_yaml × N artifacts under expeditions/<id>/
    → log_expedition_lineage → KAOS spawn + set_state + checkpoint
```

## CONTEXT

Why this architecture (per ADR-0009 framing):

- **Async co-opetition** not real-time battle (ADR-0009 §Amendment-2026-06-08).
- **Subscription CLIs** not API keys — bridges drive the user's existing
  Claude Code / Codex / Manus seats (Failure mode #5 in
  `IDEAL_EXPERIENCE.md`: subscription-CLI drift detection via
  `tests/fixtures/bridges/*_smoke.json` once captured).
- **KAOS vendored as subtree** (not pypi) for ACE-FCA context discipline
  (CLAUDE.md §Why KAOS lives at `packages/kaos/`, not pip install).
- **Pokédex (not Showdown)** product metaphor — Pareto + EvolutionCard
  catalog complementary strengths, no winner-take-all.

## Invariants

- ResultCard `cost_dollar: float | None` — None on failure path (MF5);
  pareto_verdict EXCLUDES None-cost cards from rankings.
- Seed `seed_provenance ∈ {structural, learned}` (R6 truth-in-
  advertising); M5 = all structural; M7 raises bar to ≥1 learned.
- BLAKE3 source-bundle hash freeze: same bundle hash → same Pareto
  verdict shape (Failure mode #2 reproducibility).
- Hermes plugin discoverable via `hermes_agent.plugins` entry-point;
  no custom Runner subclass (SessionRunner is documented vapor —
  STATE.md Notable event).

## Guardrails

Encoded enforcement (per DOC-LINT-040 — guardrails section required for
architecture docs):

| Guardrail | Enforced by | Tier |
|---|---|---|
| Three Cards `extra="forbid", strict=True` | pydantic v2 ConfigDict in `cards/`; mypy --strict on cards/ | unit-test + type |
| ResultCard.cost_dollar None-only on failure | pareto._is_failed filter + test_pareto MF5 tests | unit-test |
| BLAKE3 source_bundle_hash matches stored value | TaskCard validator regex `^[0-9a-f]{64}$` + bundle.yaml load | runtime |
| Seed.seed_provenance non-null | pydantic Literal — schema rejects null | unit-test |
| KAOS spawn + set_state + checkpoint on every Expedition | log_expedition_lineage call site inside run_expedition_orchestrator | integration |
| Bridge handshake protocol drift | tests/fixtures/bridges/*_smoke.json (post-capture) | integration (post-BRIDGE-SMOKE) |
| Doc / spec drift on src changes | scripts/doc_lint.py DOC-LINT-062 in lint.yml CI | CI |
| Tiny-PR discipline (≤10 files / commit) | cron/weekly_harness_audit.sh §1 TINY_PR_VIOLATION flag | audit |
| `Until:` dates in DEFERRED.md not past-due | cron/weekly_harness_audit.sh §2b past-due scanner | audit |
| Pre-commit hooks installed | .pre-commit-config.yaml + scripts/install_hooks.sh; .github/workflows/lint.yml gate | CI |

## Cross-references

- `docs/adr/0009-kaos-substrate-and-retrofit-framing-pokedex-pivot.md`
  — canonical architecture decision
- `IDEAL_EXPERIENCE.md` — success anchor (G14 Cursor pattern)
- `EVAL.md` — eval gates + ground-truth dataset (G13 LangChain pattern)
- `AGENTS.md` — operator surface (G2 ep3 modular index)
- `DEFERRED.md` — phase-8 polish queue w/ `Until:` dates
- `.supergoal/STATE.md` — phase progress + Notable events log
