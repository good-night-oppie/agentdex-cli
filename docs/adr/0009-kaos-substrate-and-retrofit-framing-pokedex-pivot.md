# ADR-0009: KAOS substrate + Pokédex pivot + retrofit framing

**Date:** 2026-06-07
**Accepted:** 2026-06-07
**References:** ADR-0005, ADR-0007, ADR-0008
**Companion repos:** `~/gh/agentdex-cli` (primary), `~/gh/kaos` (substrate, vendored at `packages/kaos/` post-P4), `~/gh/helios` (mutation-seed CAS, external sibling, M6+), `~/gh/hermes-agent` (platform backbone, pip dep `>=0.15.1`)

## Status

Accepted (2026-06-07).
Amended 2026-06-08 with single-gateway embedded mode pivot (SessionRunner-vapor recon resolution) and §judge-as-profile MVP downgrade. See §Amendment-2026-06-08.

## Supersedes

`bene` as agentdex substrate. ADR-0007 mandated `bene.resources` (ResourceRecord, ResourceDelta, EvolutionCommit, ResourceRegistry) as the evolution substrate. The June recon pass surfaced KAOS (`~/gh/kaos`, 24.6k LOC, MIT) as a richer-shipped substrate covering: per-agent SQLite VFS, checkpoint/restore, MemoryStore, SkillStore, SharedLog, experiments journal, ideal_state artifacts, dream/consolidation, ideal-state tracking, eval probes, MCP server. Bene's spec page is good intent; KAOS is the shipping artifact. This ADR pivots agentdex's substrate from bene to KAOS.

## Amends

- ADR-0005 (Pokédex pivot — battle UX is now catalog + receipt + lineage; Pokémon Showdown stays as marketing analogy, Pokédex IS the product)
- ADR-0007 (bene→KAOS for ResourceRegistry; lineage flow helios→KAOS on mutation promotion)
- ADR-0008 (Boundary table flips 3 rows to KAOS, new mutation-seed CAS row for helios; Migration re-sequenced to M0–M10; SessionRunner-vapor pivot to single-gateway embedded mode — see ADR-0008 §Amendment-2026-06-08 in this same cascade)

## Context

Three forces converged on this ADR:

1. **Substrate readiness.** ADR-0007's bene-resources path is a spec; KAOS is a working 24.6k-LOC system. Switching the substrate eliminates 6+ months of bene-resources implementation.
2. **Product framing.** Internal review surfaced that "battle" framing (ADR-0005) front-loads the wrong UX. The Pokémon Showdown analogy is great marketing but bad spec. Users don't want to watch battles; they want a **Pokédex** — a catalog of agent encounters, each with a result card, a Pareto verdict, and an evolution receipt that links to the next attempt. The product is the catalog + receipt + lineage, not the battle replay.
3. **Helios rescope.** ADR-0008 assumed helios as the StopSignal CAS. Recon (F1, 2026-06-07) found `helios.go` ships only CGO bindings (`bindings/c/libhelios.a`, 49MB static), no gRPC server. Helios rescopes to: mutation-seed hot CAS (M6+ benchmark gates FFI vs add-gRPC). MVP M0–M5 ships zero helios integration.

The product is now: **agentdex-cli is a retrofit shell on top of Hermes (platform backbone) + KAOS (substrate) + Langfuse (observability) — producing a Pokédex of Expeditions where each Expedition is a 3-baseline run that yields 3 ResultCards + 1 ParetoVerdict + 1 EvolutionCard with mutation seeds.**

## Decision

Five sub-decisions:

### D1 — Substrate: KAOS, vendored subtree

KAOS becomes agentdex's evolution substrate. Vendored via `git subtree add --squash --prefix=packages/kaos kaos-upstream main`. Post-add cull of `docs/`, `demo_*/`, `blog/`, `image*.png`, `index.html`, `video_scripts/`, `seed_engagement.py` (≈145MB upstream noise not needed agent-side). Subtree justified by ACE-FCA principle: agent must read substrate source to extend it; submodule loses recursive grep + context recovery; pip-dep loses source-readability for the one thing agent genuinely reasons about. Upstream churn (quarterly) is acceptable maintenance cost.

### D2 — Helios rescope to mutation-seed hot CAS, M6+ only

M2 ships `packages/helios_client/src/helios_client/adapter.py` as SQLite-backed stub implementing the CheckpointStore Protocol. MVP M0–M5 has zero helios integration. M6 benchmark gates FFI-via-libhelios.a vs add-a-gRPC-layer decision; meanwhile the SQLite stub satisfies all interface contracts.

### D3 — Retrofit framing: agentdex-cli sits ON TOP of Hermes 0.15.1

Per ADR-0008 §D library-boundary (source-fork stays rejected): `hermes-agent>=0.15.1` is a pip dependency. agentdex-cli supplies the brand+UX shell (`adx` CLI, `adx tui`), the agentdex_plugin loaded INTO the hermes gateway via entry-points group `hermes_agent.plugins`, the adx_bridges invoked AS plugin tools, the Card pipeline, and the KAOS-backed memory provider.

**Amendment-2026-06-08:** Original architecture referenced `hermes_cli.SessionRunner`. Recon caught vapor — that class does not exist in 0.15.1. Hermes ships gateway+plugins. Pivot: ONE long-lived `hermes gateway --profile agentdex` subprocess per expedition; orchestrator drives turns via gateway HTTP endpoint; plugin loaded once via entry-points. See ADR-0008 §Amendment-2026-06-08 for full contract. See `.supergoal/ARCHITECTURE.md` for amended mermaid diagrams.

### D4 — Vendoring mode: KAOS subtree, Langfuse pip, helios external

- **KAOS (substrate-we-extend)** → vendored subtree at `packages/kaos/`. Agent reads internals to write `kaos_adapter.py`.
- **Langfuse (service-we-call)** → pip dep `langfuse>=4.7,<5.0`. ACE-FCA test: agent doesn't reason about Langfuse SDK internals; reads `.agents/skills/langfuse/references/*.md` (7 files in tree). Subtree cost (~1MB SDK + weekly upstream churn + TypeScript server out-of-scope) buys zero reasoning capability we don't already have. Version pin is the cheaper hedge.
- **Hermes (platform-we-host-on)** → pip dep `hermes-agent>=0.15.1`. Same reasoning as Langfuse; source-fork rejected per ADR-0008 §A.
- **Helios (FFI-we-bench)** → external sibling repo `~/gh/helios/`, MVP M2 ships SQLite stub adapter only; M6+ benches.

### D5 — MVP sequencing: M0–M5 as the Pokédex gate, M6+ as evolution

| Milestone | Deliverable | Gate |
|---|---|---|
| M0 | ADR-0009 + Three Cards schemas | this ADR + pydantic strict |
| M1 | Frozen NVIDIA earnings infographic bundle | BLAKE3 hash of sorted sources |
| M2 | uv workspace + KAOS subtree + engine extract + Hermes plugin discoverable | `hermes plugins list ∋ agentdex` OR entry-points fallback |
| M3 | 3 baseline bridges (Claude Code / Codex / Manus) working | each runs NVIDIA task end-to-end |
| M4 | Oracle layer (hard/soft/repair) + Pareto judge | ResultCard from raw bridge run; Pareto winner OR "no clear winner" |
| M5 | Expedition end-to-end | 3 ResultCards + 1 Pareto + 1 EvolutionCard w/ mutation seeds in ≥2 of 5 categories |
| M6+ | Helios bench, Ladder/Elo, full MetaHarness 5-layer, Manus-vs-Codex official Expedition, hosted compute, web catalog polish, profile-as-judge resolution (M10) | post-MVP, scoped per-quarter |

M5 IS the Pokédex MVP gate. Pass M5 = Pokédex demo-ready.

## Data Model

The Three Cards live at `~/gh/agentdex-cli/cards-mvp/` during M0 (this phase) and move to `packages/agentdex_engine/src/agentdex_engine/cards/` at M2 (phase-4 workspace restructure).

| Card | File | Fields (summary) |
|---|---|---|
| **TaskCard** | `cards-mvp/task_card.py` | id, source_bundle_hash (BLAKE3 hex), environment_spec, oracle_spec_ref, budget_token_cap, budget_dollar_cap, expected_output_kind, version |
| **ResultCard** | `cards-mvp/result_card.py` | expedition_id, task_id, agent_id, pass_rate, cost_dollar, cost_token, speed_wall_clock_sec, failure_trace_path, pareto_position, langfuse_trace_id, langfuse_trace_url |
| **EvolutionCard** | `cards-mvp/evolution_card.py` | expedition_id, parent_lineage_root, winning_pattern, losing_pattern, mutation_seeds (dict[category, list[Seed]]), boundary_annotations, langfuse_trace_urls (dict[agent_id, str]) |

All models use pydantic v2 `model_config = ConfigDict(extra="forbid", strict=True)`. Field-name stability is load-bearing for the Pareto judge.

The `Seed` sub-model carries `seed_provenance: Literal["structural","learned"]` per consensus blocker R6 (2026-06-08) — `structural` flags mechanical seeds emitted by repair/provenance Oracles; `learned` flags seeds from M7's seed_extractor analyzing failure patterns. M5 MVP gate accepts structural seeds explicitly; M7 raises bar to ≥1 learned seed per Expedition.

## Observability (NEW)

Triple-tier per ROADMAP A12:

| Tier | Tool | Granularity | Lifecycle | Repo mode |
|---|---|---|---|---|
| **Trace** | Langfuse | per turn, per tool call, per prompt | trajectory-level | pip dep `langfuse>=4.7,<5.0` |
| **Activity** | KAOS | per Expedition, per mutation-seed promotion | durable lineage | vendored subtree `packages/kaos/` |
| **CAS** | Helios | mutation-seed hot validation | volatile, M6+ | external sibling, SQLite stub at M2 |

Picked Langfuse over Opik (newer, smaller) and Braintrust (closed) on OSS maturity, Anthropic+OpenAI SDK auto-instrumentation (`langfuse.anthropic.Anthropic`, `langfuse.openai.OpenAI`), MIT license, self-hostable, ~11k★ GitHub community vitality.

EvolutionCard includes `langfuse_trace_urls: dict[agent_id, str]` so Pokédex viewers can drill into per-baseline reasoning trace. ResultCard has `langfuse_trace_id` + `langfuse_trace_url`.

R3 (trace propagation across orchestrator↔gateway HTTP boundary) addressed by Phase 4 spike: pass → headers always injected; fail → per-baseline-root traces with cross-trace links via `langfuse_trace_urls` (already dict-typed; failure mode is honest representation, not regression).

## Kill-switches

- **KAOS upstream breaks API** → freeze at vendored squash commit; defer upstream merge until breaking change reverted or migration window scheduled. Vendored subtree decouples our shipping from upstream cadence.
- **Helios mutation-seed RTT fails** at M6 bench → port the hot path to Python (slower but unblocked) OR move to in-process FFI via libhelios.a. The SQLite stub stays as fallback.
- **Hermes 0.15.x ships breaking change** in `hermes_cli.plugins` entry-point group or `PluginContext` API → pin to last-good version + delay M2/M3 until upstream stabilizes. Plugin contract is the load-bearing surface.
- **Langfuse SDK churns** through breaking changes between 4.x and 5.x → pin `<5.0` floor (already done). Migration window scheduled per `references/sdk-upgrade.md`.

## Open questions

- **Q1 (resolved 2026-06-07 recon F1)** — Helios access mode. Recon found no gRPC server in helios.go; M2 ships SQLite-backed stub adapter; FFI-via-libhelios.a vs added-gRPC-layer benchmarks at M6. MVP M0–M5 ships without helios.
- **Q4** — Hermes upstream PR shape under retrofit framing. Open: do we contribute the agentdex_plugin or related primitives upstream, or stay downstream? Defer to post-M5 — let MVP prove value first; upstream conversation cheaper once we have demo + traction.
- **Q5** — Oracle hard/soft boundary. Hard Oracle gates number correctness via regex + tolerance (per ADR-0009 §Q5 detail in phase-6.md spec). Soft Oracle scores narrative coherence via LLM judge. Boundary: anything quantitative ≥1 atomic claim → hard Oracle; anything multi-claim or qualitative → soft. Repair Oracle flags weak rubrics as `seed_provenance="structural"` seeds.

## Scope

**M0–M5 boundary (this ADR's contract):**
- ADR cascade landed
- Three Cards schemas frozen
- NVIDIA earnings task bundle (Q3 FY2026) BLAKE3-frozen
- uv workspace w/ 7 packages (`agentdex_cli`, `agentdex_engine`, `agentdex_plugin`, `adx_bridges`, `helios_client`, `agentdex_observe`, `kaos`)
- 3 bridges working
- Oracle+Pareto producing ResultCards + ParetoVerdict
- Expedition end-to-end producing EvolutionCard with mutation_seeds in ≥2 categories (M5 gate; structural seeds OK)
- Langfuse trace continuity (or honest fallback) per Phase 4 R3 spike outcome
- KAOS experiments.log persisting lineage

**Post-MVP (deferred):**
- Ladder/Elo math
- Full MetaHarness 5-layer (proposer → grader → trace-store → archive → cron)
- Manus-vs-Codex official Expedition
- Hosted compute (subscription CLI rate-limit handling at scale)
- Web catalog polish (Pokédex viewer UI)
- Profile-as-judge resolution (M10, requires Hermes ≥0.16 upstream)
- Helios FFI/gRPC bench + production wire
- Helios mutation-seed hot CAS (M6+)
- Learned seed extractor (M7)

## Consequences

**Wins.**
- Substrate ships immediately (KAOS works today; bene-resources was a 6-month spec).
- Product framing locks: Pokédex catalog + receipt + lineage is teachable.
- Helios deferral unblocks M0–M5 without speculative gRPC work.
- Triple-tier observability separates concerns cleanly.

**Tradeoffs.**
- Subtree vendoring costs ~24.6k LOC in tree + quarterly merge discipline. Justified by ACE-FCA agent-readability.
- Direct SDK judge call (vs profile-resolved) sacrifices cost-per-profile attribution. Mitigable via Langfuse tags; full fix at M10.
- Single-gateway embedded mode is sequential at M5. Concurrent baselines need async upgrade at M8 (localized to `expedition.py` loop + `GatewayHandle.post_turn`).

**Risks.**
- KAOS upstream cadence may surprise us; vendored squash gives us a freeze handle.
- Phase 4 R3 spike could fail; fallback path documented.
- Structural seeds passing M5 gate without learned seeds means M5 proves "code runs honestly," not "system discovers." `seed_provenance` field is the truth-in-advertising mechanism.

## Considered alternatives

- **bene-resources** as substrate (ADR-0007 default) — defer 6+ months while KAOS ships today. Rejected on cost.
- **Submodule for KAOS** — loses recursive grep + agent context recovery. Rejected on ACE-FCA.
- **Source-fork of Hermes** — re-rejected per ADR-0008 §A. Maintenance burden unjustified.
- **Drop M5 mutation-seed requirement** (gemini consensus alt) — over-cuts; `seed_provenance` typed honesty is the lighter touch.

## References

- `.supergoal/ROADMAP.md` (Phase map, 8 phases M0–M5 + polish)
- `.supergoal/ARCHITECTURE.md` (4 mermaid diagrams, amended 2026-06-08)
- `.supergoal/PROTOCOL.md` (supergoal harness execution loop)
- ADR-0005 (battle platform pivot, amended by this ADR)
- ADR-0007 (resource-commit evolution, amended by this ADR)
- ADR-0008 (Hermes TUI host, amended by this ADR; §Amendment-2026-06-08 covers SessionRunner pivot + judge-as-profile downgrade)
- `~/gh/kaos/` (substrate, vendored at M2)
- `~/gh/hermes-agent/hermes_cli/plugins.py` (platform plugin surface, lines 172 ENTRY_POINTS_GROUP + 289 PluginContext)
- `.agents/skills/langfuse/SKILL.md` (Langfuse integration glue, mandatory read before P4 `agentdex_observe` coding)
