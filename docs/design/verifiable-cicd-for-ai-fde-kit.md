---
title: Verifiable CI/CD for AI — FDE Self-Improving System Kit
status: draft
owner: etang
created: 2026-06-29
updated: 2026-06-29
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

# Verifiable CI/CD for AI — FDE Self-Improving System Kit

> **What this is.** A domain-agnostic reference architecture that lets a Frontier Deployment
> Engineer (FDE) turn *"what a customer wants"* into a continuously-improving agent system whose
> complexity is **tangible** (a handful of named contracts), whose build friction is **low** (write a
> thin domain adapter, inherit the loop), and whose lineage a **successor can pick up** without
> archaeology. `agentdex-cli` is the reference *binding* (AI agents battle in Pokémon Showdown for a
> verifiable Glicko rating); the kit is the same machine with the domain adapter swapped out.
>
> **Provenance.** Synthesized from two multi-agent design panels + a `prisma_deep_plan`
> (gemini-3.1-pro deep-think) 6-expert adversarial review. This is doctrine, not yet a shipped system —
> §11 is honest about what exists vs. what's a gap.

---

## 0. TL;DR

1. **Sell the brakes, not the engine.** "Self-improving AI" gets blocked by InfoSec. The product is
   **Verifiable CI/CD for AI**: an out-of-band engine that proposes config changes, proves they
   dominate the baseline on a hash-locked replica of production data, and opens a **GitHub PR** with a
   cryptographic receipt. Humans review and merge. It never mutates in production.
2. **It's regression-CI, not RL.** With a realistic golden set (N≈30–50) you can honestly detect
   *capability leaps and catastrophic regressions*, not 2–5% micro-gains. Treat frozen fixtures as
   **regression tests** (goal: 100% baseline pass + solve newly-injected edge cases), not a gradient.
3. **Three contracts, not two.** `Genome` (input, Improver owns) → `Gym` (pure scorer) →
   `Cassette Ledger` + `Kill Gate` (immutable proof + verdict). The Gym is a blind, stateless,
   deterministic function; that's what makes the loop un-cheatable.
4. **Build the Null-Mutation Kill Gate first.** Before any candidate generation, prove an *identical*
   agent re-scores identically on a frozen cassette. If it doesn't, your Gym leaks variance and the
   whole loop is invalid.
5. **The eval is the product.** The hard part — and the first 1–2 months of any engagement — is
   excavating verifiable ground truth and calibrating the judge. If experts can't agree (inter-rater
   κ < 0.20), the domain is un-gym-able; don't fake a gate.

---

## 1. The core principle

> **Excavate the verifiable core of a fuzzy goal — don't invent a score for it.** A Gym is not "done"
> when `score()` returns a number; it is done when `score()` can **falsifiably distinguish a
> deliberately-degraded agent from the baseline.** (bene's law: *a gate that cannot kill the baseline
> is VOID.*)

Every "subjective" goal decomposes into a checkable substructure + a residue. Grade the substructure
for free; reach for judgment only on the residue; validate the judgment against reality on a separate, out-of-loop cadence.

---

## 2. Architecture — the three contracts

```
   GENOME ─────────▶  GYM  ─────────▶  CASSETTE LEDGER ─────────▶  KILL GATE
   (Input Contract)   f(Genome,        (Output Contract:           f(baseline_cassette,
   Improver owns      CassetteID)        immutable, hash-locked      candidate_cassette)
   — what may change) → CassetteLedger   FitnessVector+TranscriptHash)→ ACCEPT | REJECT | VOID

   IMPROVER:  f(historical_cassettes) → ProposedGenome   (reads proofs only; knows no business logic)
                          ▲                                            │ ACCEPT
                          └──────────── LINEAGE / BATON (KAOS + git tag) ◀── successor resumes here
```

**Pure-function signatures (the un-cheatable interface):**

```python
class Gym:        # domain-specific (the FDE writes the adapter)
    def evaluate(self, genome: Genome, cassette_id: str) -> CassetteLedger: ...
    # Deterministic by contract: same (genome, cassette_id) -> identical TranscriptHash, forever.
    # Never falls through to live data when a cassette_id is provided.

class Improver:   # domain-agnostic (reused unchanged across every business)
    def propose(self, history: list[CassetteLedger]) -> Genome: ...
    # read-only over history; fills the refiner=None gap; cannot touch the Gym.

class KillGate:   # the trust layer (owned by the Cassette Ledger)
    def gate(self, baseline: CassetteLedger, candidate: CassetteLedger) -> Receipt: ...
    # ACCEPT | REJECT | VOID. Only the gate issues a promotion receipt.
```

**The five seams an FDE implements (this is the tangible-complexity decomposition):**

| # | Seam | Contract | Reference binding in `agentdex-cli` |
|---|---|---|---|
| ① | `score()` → `FitnessVector` (re-simulable, hash-locked) | Gym | `selfplay/fitness.py:multi_dim_fitness` + `evolution.py:_rate` `input_log_blake2b16` |
| ② | `Genome` (what may change) | input | bene 5-component genome (memory/retrieval/context/tool/prompt); `HarnessWorkspace` stores |
| ③ | `propose()` (autogenesis) | Improver | the empty `evolution.py:293 refiner=None` slot |
| ④ | `gate()` ACCEPT/REJECT/VOID | Kill Gate | McNemar verdict → bene sha256-locked `Probe`/`promote()` |
| ⑤ | `run()` + autonomy (L0–L4) | continuous driver | `GenerationScheduler` + FIC baton + bene `AutonomyPolicy` |

---

## 3. Part 1 — Building a Gym for any business

### 3a. The layered oracle stack (manufacture the score)

| Tier | What it does | Role | agentdex binding |
|---|---|---|---|
| **HARD** | objective, zero-LLM checks (number to 0.1%, valid enum, JSON keys, exit 0, SQL rows, no-PII, disclosure present) | **inner gate** | `oracle/hard.py` (`NumberAccuracyOracle`, `ProvenanceOracle`) |
| **SOFT** | LLM-judge on a rubric, *only* for what hard can't reach; prefer **A-vs-B preference** over absolute | **inner gate** | `oracle/soft.py` (`LlmJudgeOracle`: nonce-delimited, uncertainty, retries) |
| **CALIBRATION** | quarantine the judge until κ ≥ 0.40 (≥ 0.60 subjective/regulated) vs human labels, ~20% fixtures in the 0.4–0.6 band | **admission / tiebreak** | `oracle/calibration.py` (`calibrate()` → `CalibrationReport`) |
| **OUTCOME** | weekly 10% live slice → real KPI (CSAT, reopen-rate, churn); proxy↔KPI divergence → promote failing cases into the golden set, recalibrate | **out-of-loop audit** | (new) the audit loop on top of KAOS receipts |

Numbers use hard match, never a judge. Most domains have *far* more verifiable core than engineers
assume — excavate it before writing a rubric.

### 3b. Re-simulability — and the Off-Manifold Trap

`score()` must be deterministic and re-auditable even when the real environment is live and
side-effectful. The mechanism is a **frozen golden dataset + a VCR cassette** (record/replay of all
environment I/O, matched by normalized request hash, **never** falling through to live).

**The trap (this narrows the "any business" claim):** VCR replay only works for **single-turn /
deterministic** tasks. In a multi-step agentic workflow, a *genuinely better* agent takes a *novel*
path → cassette cache-miss → the system **penalizes the innovation**. You'd have built a strict
regression enforcer, not an improver. So the *general* substrate is not VCR replay:

| Environment | Gym mechanism |
|---|---|
| single-turn / deterministic | VCR cassette replay |
| multi-step / stateful / latent-state (CRM, trading, live ops) | **shadow mode** (score `proposed_action.json`, never execute) + **Thompson-sampling bandit** on a 1% prod slice |

### 3c. The manufactured adversary

Most domains have no natural opponent, so the improvement signal has nothing to push against. Substitute
three things, together:
- **Champion self-play** — register the current best-ever Genome as a frozen anchor; candidates must
  Pareto-dominate it. (`ladder.py register(frozen=True)`)
- **Held-out hard-case split** — ~20% tagged `difficulty=hard`; a candidate that improves on easy but
  regresses on hard is rejected.
- **Coevolving failure-miner** — mine `pass=False` + high-uncertainty verdicts, synthesize adversarial
  variants (cap K/gen, SME-review), inject into the active set, retire solved cases. *Not optional —
  see §6.*

### 3d. The archetype playbook

| Archetype | Difficulty | Oracle strategy | Baseline / adversary | Example |
|---|---|---|---|---|
| **Objectively-checkable** | easy | HARD only — *don't* add a judge where ground truth is computable | existing human script / rule system | code-gen, SQL/ETL, reconciliation, IaC, figure extraction |
| **Process / outcome** | medium | oracles on the **outcome**, not the live call; transcript *is* the cassette; hard booleans (reopened? escalated? SLA?) + calibrated quality judge | current human agent's median outcome rates | support triage, ops runbooks, claims, incident response |
| **Subjective / generative** | hard | **pairwise preference** primary; mandatory calibration; anti-Goodhart blind-human review of 10% every ~5 gens or block | human content, else haiku zero-shot as the known-weak floor | marketing copy, research synthesis, exec summaries |
| **High-stakes / regulated** | frontier | judge **inadmissible as sole gate** — recorded human sign-off *is* the gate; hard=format only, soft=procedure only; autonomy capped L2 | human-expert error rate | legal review, medical triage, financial advice |

### 3e. The un-gym-able boundary + the shadow-mode rescue

A domain is *truly* un-gym-able only when several hold at once: irreversibly stateful with no dry-run,
**and** no post-hoc outcome signal, **and** expert inter-rater κ < 0.20, **and/or** feedback horizon
longer than the improvement cycle, **and/or** a Genome with zero degrees of freedom.

The rescue for *most* "irreversible" cases is **shadow mode**: don't let the agent act — have it emit a
`proposed_action.json`, score the **proposal**, never execute. This converts an irreversible problem
into a *subjective/generative* Gym, and the human's review of the proposal becomes the boolean hard
oracle. When even that fails, **do not fake a gate** — hold autonomy at L0/L1, use the out-of-loop outcome
audit alone, and mark the Gym **INCONCLUSIVE** rather than sell noise.

---

## 4. Part 2 — The Improver (reused unchanged across domains)

The "second half" is ~10 wiring components over existing seams, **not** new research systems.

**The closed loop:**
1. `GenerationScheduler` ticks → run a generation; `_rate` produces the Glicko-Δ + per-item
   `input_log_blake2b16`.
2. `FitnessAPI` → one `FitnessVector` (≥ 2 dims; always include cost + latency as minimize).
3. `ArenaKillGate` runs a sha256-locked bene `Probe` pre-registered against gen N-1's predicted fixes:
   McNemar EFFECTIVE → ACCEPT · HARMFUL → REJECT · INCONCLUSIVE/<2·RD → VOID.
4. **REJECT (unconditional):** `rollback_to_best_ever` + quarantine. **ACCEPT:** `AutonomyGate` checks
   the ladder; at L3+ `mark_best_ever` + `SkillPromoter` writes a tier-4 strategic engram +
   `mh_write_skill`. **VOID:** blocks promotion, surfaces to the FDE.
5. `ReplayDistiller` turns the trace into a tier-3 procedural engram.
6. `FiveLayerSeedRouter` reads the bottleneck dimension → ranked mutation targets across
   Skill/Code/Architecture/Algorithm/Oracle.
7. `HarnessRefiner` (fills `refiner=None`) → bene `ReflectiveEvolver` mutates Genome fields → gen N+1
   `ChangeManifest` with McNemar-measurable `predicted_fixes`.
8. `ParetoVectorBridge` maps the FitnessVector to bene's frontier; `CoevolutionOpponentPool` (late
   phase) evolves opponents on the same CRN seeds.
9. `gh_pr_publisher` emits the EvolutionCard to KAOS + opens a GitHub PR.
10. `GenerationScheduler` hits the FIC ceiling → `ContinuousHarnessBaton` writes `{gen index, KAOS
    root, best_ever git SHA, frontier, next target}`; a successor resumes from the committed gen-N tag,
    no history replay.

**Autonomy ladder:** L0 observe · L1 suggest · L2 act-in-sandbox · L3 act-on-shared-state · L4
autonomous-promote (human-only grant). It is a **dynamic GRC control**, not a preference — see §6.

---

## 5. The statistics — TDD, not RL

- **The N reality.** Detecting a 5% effect at 80% power / α=0.05 needs **N ≈ 385** paired discordant
  samples; an FDE freezes 30–50. At N=50, McNemar's minimum detectable effect is ~20%. Chasing 5% on
  50 tasks is a **Type II error factory** that occasionally promotes noise (Type I / Type S/M errors).
- **Reframe to regression-CI.** Goal = *zero regressions on baseline-solved cases + solve newly-mined
  failures*, not "climb 2%". `if baseline scores 40/50, candidate must score ≥ 48/50`.
- **SPRT** (sequential probability ratio test): replace fixed-N gates; resolve ACCEPT/REJECT/VOID early
  when the log-likelihood ratio crosses the boundary; only borderline candidates pull more tasks from a
  shadow queue.
- **Continuous proxies as control variates** (token efficiency, JSON validity, latency) cut variance
  vs. binary win/loss → much smaller N for significance.
- **Failure-anchored sampling.** Test on the baseline's *failures* (40) + a regression-guard set (10),
  not 50 random tasks. Solving 15 failures without regressing = a large signal at small N.

(Instruments already present: `modules/arena/power.py:battles_to_detect()`, `paired_eval` McNemar.)

---

## 6. Maintainability & anti-rot (why a successor can own it)

Lineage + baton track *what* happened, not that it was *good*. The failure modes are active, not passive:

- **The Goodhart Singularity.** Agent and judge share a latent space → the agent evolves to exploit the
  judge's biases (verbosity, sycophancy, formatting); FitnessVector ↑, real utility → 0; the baton
  becomes "a lineage of degradation." **Co-evolving failure mining must be the core engine** — a
  sliding window of maximum adversarial pressure (inject K champion-failures/gen, retire K solved).
  *If your benchmark isn't rotating, your agent isn't learning — it's cheating.*
- **Kappa-locked autonomy.** Continuously re-grade the judge vs blind human labels; rolling κ < 0.6 →
  **auto-demote to L2** and halt at the gate (which generates fresh calibration data to repair it).
- **Regression tripwire.** Periodically inject *known-broken genomes*; if the gate fails to REJECT them
  → **VOID + halt** the driver until an FDE repairs the oracle. A gate that can't kill is VOID.
- **The baton durability contract.** The VFS (SQLite) does not restore the git tree — the baton must
  carry **both** the workspace path **and** the best-ever git SHA, on a **persistent** volume, and the
  successor must verify both before resuming, or state corrupts silently.

The successor reads the *lineage* (KAOS EvolutionCards + git tags + ACCEPT/REJECT/VOID receipts), never
the conversation. The control surface (autonomy level + κ + receipts) is always inspectable.

---

## 7. Commercial framing — "Verifiable CI/CD for AI"

To a CISO, "autonomous self-improving AI" = uncontrolled runtime mutation = blocked before the POC.
**You sell the brakes.**

> "LLMs degrade silently as models update and data distributions shift. We deploy an out-of-band
> Continuous Alignment Engine. It generates AI updates offline, tests them against a cryptographic,
> hash-locked replica of your production data, proves ROI mathematically, and **opens a standard GitHub
> PR** with the diff + regression-test receipts. Your engineers review and merge. It never mutates in
> production."

The kicker: `agentdex-cli` **already has `gh_pr_publisher`** — "every generation = a PR" *is* the
enterprise-grade L2 control surface. What we have is exactly what makes it sellable.

**FDE lexicon (never use the left column in an enterprise room):**

| Internal | Customer-facing |
|---|---|
| autogenesis / self-improvement | Continuous Alignment Optimization |
| genome mutation / evolution | Parameterized Policy Versioning |
| arena / co-opetition battles | A/B/n Regression Testing |
| kill gate | Compliance Verification Gate |
| agentic refiner | Automated Proposal Generator |

**Phased engagement** (the fatal assumption is that the customer has stationary, codifiable ground
truth — if not, the gate permanently VOIDs in an infinite `PromotionBlocked` loop):
- **Phase 1 — Shadow-Mode Excavation (months 1–2):** autonomy L0; route human decisions into cassettes;
  force stakeholders to grade them; build the golden set; calibrate the judge to κ ≥ 0.6. *The product
  here is discovery.*
- **Phase 2 — Verifiable CI/CD (months 3–4):** L2; the engine generates candidates → GitHub PRs;
  humans click ACCEPT/REJECT.
- **Phase 3 — Autonomous Tuning (month 5+):** L3/L4 for low-risk sub-tasks only, once the oracle is
  Goodhart-resilient and SPRT validates ROI.

---

## 8. Build sequence

1. **Map the seams** — define the mutable Genome + action space.
2. **VCR core + Null-Mutation Kill Gate** — prove strict re-simulability (identical agent → identical
   TranscriptHash) *before anything else*.
3. **Shadow-Mode Excavation** — 50 real logs, humans grade, calibrate the soft oracle to κ ≥ 0.6.
4. **L2 autogenesis** — fill `refiner=None`; Improver generates candidates → GitHub PRs; humans review.
5. **Elevate to L3/L4** — only once the oracle is Goodhart-resilient and SPRT validates the ROI.

---

## 9. Concrete bindings (what exists vs. the gaps)

**`agentdex-cli` (the reference binding — most of Part 1 is built):**
- Oracle stack: `agentdex_engine/oracle/{base,hard,soft,repair,calibration}.py` + `OracleChain`.
- Co-opetition lane = "any frozen task" Gym: `modules/{tasks,battles,evolver}` + per-task `spec.yaml` →
  ResultCard/Pareto → KAOS lineage.
- Fitness + gate instruments: `selfplay/fitness.py:multi_dim_fitness`, `evolver/pareto.py:dominates`,
  `modules/arena/{power.py,paired_eval}`.
- Continuous skeleton (partial): `adx_showdown/evolution.py` `EvolutionLoop` — Glicko `_rate` +
  `input_log_blake2b16`, `mark_best_ever`/`rollback_to_best_ever` + quarantine, `gh_pr_publisher`.

**`bene` (the Improver engine):** engram ladder (tier-4 = strategic genomes), probes + sha256-locked
kill gates (ACCEPT/REJECT/VOID; VOID-if-can't-kill), 5-component genome + reflective mutation + Pareto
frontier + `promote()`/`PromotionBlocked`, autonomy ladder L0–L4 + trust, `mh_*` + `skill_*` MCP tools.

**`harness-engineering` (the continuous driver):** Research-Plan-Implement, Frequent Intentional
Compaction (FIC), the long-running serial-baton handoff (the same pattern that authored this doc).

**The honest gaps:**
- `evolution.py:293 refiner=None` — **nothing generates candidates today** (the single highest-value
  unlock). Until filled, the loop only ever re-runs the seed.
- bene's own SKILL.md: `mh_search → kill-gate` is **not wired end-to-end**; `genome_from_candidate` is a
  manual bridge.
- No `GenerationScheduler` / baton-relay continuous controller exists yet.
- The full 5-layer Meta-Harness (`recon-extras.md`) is explicitly deferred post-MVP.

---

## 10. Open questions / honest risks

- **Statistical power gap** (N≈385 needed vs 30–50 frozen) — close via SPRT + failure-mined augmentation
  + continuous proxies, or be honest the gate only catches *big* regressions. This is the real research
  surface, not the plumbing.
- **Off-manifold multi-step** — VCR replay penalizes innovation; shadow+bandit is the general answer but
  has its own credit-assignment and cost/safety costs.
- **Judge family drift** — a silently-upgraded judge model invalidates yesterday's calibration; needs a
  rotation/ensemble policy + κ tripwire.
- **Cassette staleness** — normalized-request replay drifts when the real API/schema changes; needs a
  refresh cadence + a `CassetteMatchError` budget.
- **Regulated ceiling** — when human sign-off *is* the gate, the Improver optimizes a triage filter, not
  the decision; how to measure improvement without collapsing to "deferral rate".
- **Deploy durability** — the baton is only as durable as its persistent volume; ephemeral containers
  break successor resume.

---

## Changelog
- 2026-06-29 — initial draft (harness-31). Synthesized from two design panels + `prisma_deep_plan`
  6-expert review. Brainstorm capture: `/tmp/20260629_FDE-kit-brainstorm-prisma.md`.
