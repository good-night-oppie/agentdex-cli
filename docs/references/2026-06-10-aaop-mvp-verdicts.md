---
title: "AAOP corpus → MVP verdicts (adversarial research run)"
status: active
owner: "@EdwardTang"
created: 2026-06-10
updated: 2026-06-10
type: reference
scope: .
layer: cross-cutting
cross_cutting: true
---

# AAOP corpus → MVP verdicts (2026-06-10)

Workflow run `wf_000c6bec-85f` (27 agents, ~1.9M tokens): digested the
16-paper agent-auto-opt-papers corpus (vendored at `vendor/aaop/`, wiki at
`harness-engineering/eddie-agi-kb/videos/agent-auto-opt-papers/`), generated
6 MVP candidates through 3 strategic lenses (mvp-first / moat-first /
imaginary-frontier), validated each against academic + industrial evidence
(web-sourced), then ran kill-by-default adversarial refutation.

**Result: 6/6 refuted. The refutations are the deliverable.** Full evidence
JSON with source URLs archived in the session transcript; this doc preserves
the verdicts + whitespace findings that survive.

## Autopsy table

| MVP | Kill-shot (one line) | Salvage |
|---|---|---|
| NightShift (doctrine-PR bot) | Verify-gate statistically unaffordable: ~+4.5pp doctrine effects vs huge agentic replay variance → ~775 runs/arm for 80% power; commodity OSS (claude-reflect, GEPA) + platform absorption | Trace-mining pipeline; Bayesian cross-patch aggregation un-stress-tested |
| SkillGate (skill registry+CI) | Differentiator factually false — Tessl Task Evals shipped the paired helpfulness probe + 2k-skill registry Jan 2026 ($125M, Snyk distribution) | Fleet-telemetry EMA utility attribution = real whitespace, feature-sized |
| Foundry (overnight harness breeder) | 60×30 = 1,800 episodes can't ride subscription rate-limits; best-of-60 on n=30 tasks = selection on noise (SE ~9pp > 5pp lift sold) | Meta-Harness method itself strong; valid as internal tool |
| Dojo (eval flywheel + league) | Own data shows 11/11 `no_clear_winner` — the disagreement signal never fired; Braintrust/Patronus/LMArena occupy every wedge | Disagreement-mining concept validated (LiveBench precedent) |
| Gene Mesh (federated seeds) | Anchor paper self-refutes: FedTextGrad found adding clients DEGRADES performance; CISO sales unreachable solo | Seeds-not-data privacy structure, single-tenant form |
| Composer (AlphaGo MCTS over move library) | Meta-Harness open-sourced framework + winning artifact → moat = `git clone`; Zenbase (DSPy founders) pivoted out of optimization-as-a-service | Replay-buffer value prior (Spearman ≥0.5 @200 rollouts) = unprecedented research bet; dogfood-only |

## Whitespace the lens set never generated (completeness critic)

1. **Sell the measurement problem, not the improvement.** 5/6 kill-shots
   were statistical power. The most validated market signal: nobody can
   affordably measure agentic deltas. Variance-reduction eval infra
   (paired-run CUPED, judge ensembling, sequential testing, replay-prefix
   caching, discriminative-task selection) was never proposed — the critic's
   weapon is itself the whitespace. adx's Pareto verdict + Oracle + frozen
   TaskCards are the natural substrate; positioning shift "compare
   baselines" → "measure deltas affordably".
2. **Vertical wedge** (SkillForge precedent — only paper with deployment
   economics). All 6 MVPs were horizontal; all named competitors are too.
3. **Services-first / forward-deployed** — paid harness audits accrue the
   distribution + corpus every refutation said we lack.
4. **Online adaptation** (Continual Harness) — in-session bandit shapes
   sidestep the frozen-replay power objection entirely.
5. **Static skill-lint** (Ctx2Skill) — predict helpfulness without episodes.
6. **Protocol play** (Autogenesis AGP) — be the commoditizing standard +
   hosted registry; "OSS commoditizes you" appeared 4× as kill condition.

## Confounds (uncalibrated parts of the run)

- 6/6 refuted under kill-by-default prompting = critic calibration vs
  generator weakness undiagnosed. ≥2 objections have soft spots (NightShift
  Bayesian aggregation; Foundry sequential-by-doctrine is an M5 choice, not
  physics).
- Cloudflare 525 via the third-party relay was triple-counted as refuting
  evidence (NightShift / Foundry / Composer). Cheapest single experiment:
  one clean live expedition — updates three refutations at once. Until
  then, "11/11 no_clear_winner" measures the relay, not the method.

### Confound resolved (2026-06-11 update)

Root cause was a missing `www.`: the apex `pure100.org` origin cert is
broken (525); `www.pure100.org` is healthy. Relay config fixed + container
restarted; judge path verified POOL_OK. The clean experiment ran
(`expeditions/exp-live-www-fix/`):

- **First discriminating verdict in project history**: winner =
  `manus(codex-web-fallback)` (`undominated`, sweeps all 3 axes),
  pass_rate 0.8 vs codex 0.4. Prior record was 11/11 `no_clear_winner`.
- Evidence impact: the "disagreement signal never fired" /
  "zero discriminating verdicts to date" clauses in the Dojo, NightShift
  and Foundry refutations are now stale. The structural objections
  (statistical power, incumbent density) stand — n=1 discriminates but
  does not power a champion/challenger gate.
- Honest caveats: n=1; "manus" ran as codex-web fallback, so the contrast
  is codex-CLI vs codex-web (same vendor, two harnesses — itself a clean
  harness-effect datapoint); claude baseline excluded-failed on a NEW
  bridge bug (DEFERRED CLAUDE-BRIDGE-LIVE-EOF), unrelated to the relay.

## Verdicts

- **Build now:** ① clean live expedition (un-confound, ~$5); ② Delta-Meter
  shape (variance-reduction eval infra on adx substrate); ③ Composer demoted
  to dogfood research bet — only the replay-buffer value-prior claim.
- **Reframe:** Foundry → internal tool + services entry; SkillGate → EMA
  utility attribution as a Delta-Meter feature.
- **Kill:** Gene Mesh, Dojo-as-company, NightShift-as-product.
- **Unmined:** SkillForge-shape vertical (requires picking a vertical —
  user decision).
