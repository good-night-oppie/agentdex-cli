---
title: "agentdex-redesign GOALS (orch-proj state)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
---

status: ACTIVE — M1 research + architecture design
project: agentdex-redesign-evolution-market
state_root_note: this .fleet-goal/ lives in the redesign worktree (branch redesign/evolution-market off origin/main); the harness-engineering .fleet-goal/ is a DIFFERENT project (EDITH continuation) — never cross-write.
parent_decision: supersedes the invited-user GA supergoal (.supergoal/ in this repo) per user decision 2026-07-11; EDITH-M7 fork esc-1335b26251 ACKED on that basis.

# GOALS — agentdex redesign: agent-evolution × ladder market × weco-driven RSI

## Objective (one sentence)

Redesign agentdex so its engine measures a self-evolving agent's **Pareto
frontier against a chosen task type**, its improvement loop applies
**meta-harness + Weco** iteratively, and its website is the **organic
combination of agent-evolution.com-style knowledge and a competition/ladder/
dataset market** (Kaggle, HuggingFace, ARC-AGI-3, SWE-Bench Pro,
TerminalBench2, WebArena) — with a "connect your Weco login and let Weco drive
Claude Code to recursively self-improve your agent against a task" hook.

## Requirements (user interview, 2026-07-11, answers verbatim)

1. **GA vs redesign:** "Redesign supersedes GA" — the redesign becomes the new
   north star; the 7 blocked adx-core GA tasks get re-scoped to serve the new
   product (auth/DNS/deploy still needed, Stripe maybe later). Old-GA push stops.
2. **MVP slice:** "Measure first: Pareto engine" — CLI/engine that measures a
   self-evolving agent's Pareto frontier against a chosen task type (using
   ladder adapters), THEN the weco/meta-harness improvement loop, THEN the
   website. Measurement is the moat; the site renders what the engine produces.
3. **Ladder depth:** "Hybrid: curate all, run 2-3" — read-only curated market
   for all six ladders (metadata, links, leaderboard snapshots) + real
   run-adapters for 2-3 where local execution is tractable; those power the
   Pareto engine.
4. **Execution locus:** "User's machine, BYO creds" — CLI runs locally with the
   user's own Weco + Claude Code subscriptions; agentdex is coordinator +
   ledger + leaderboard. No hosted-compute cost, no credential custody.
5. **Ladder taxonomy (user directive, 2026-07-11, verbatim):** "Recast
   HuggingFace to substrate, not a ladder — but don't settle at 5. Add
   pokeagentchallenge.com as a live-adversarial ladder. Final set:
   Live-adversarial ladders (agents ranked vs real opponents, adversarial
   refresh): Kaggle, ARC-AGI-3, pokeagentchallenge.com. Static benchmark
   leaderboards (fixed test set + ranking): SWE-Bench Pro, TerminalBench2,
   WebArena. Substrate (not a lane): HuggingFace — datasets / distribution /
   model-hosting that powers several of the above." Rationale (verbatim): "we
   land at 6 ladders by merit — swapping a non-ladder (HF) for a genuine one
   (pokeagentchallenge) — not by manufacturing a lane to hit a count. The
   number was never the requirement; 'high-quality live ladders + substrate
   services' is." **Gate semantics (verbatim):** "the mh kill-gate must treat
   the two classes differently: held-out / decontamination checks for the
   static three; adversarial-refresh is the built-in guard for the live
   three." Diligence gate on PokeAgent PASSED (active / persistent queryable
   ranking / programmatic Showdown-API path) — see
   `evidence/M1/research/pokeagent-diligence.md`.

## Design inputs (canonical set)

- Lilian Weng, "Harness Engineering for Self-Improvement" (2026-07-04) — the
  conceptual frame for recursive self-improvement loops.
- https://agent-evolution.com/ + github.com/Shiyao-Huang/awesome-agent-evolution
  — taxonomy + site structure to organically absorb.
- Weco: docs seed at `evidence/baseline/weco_docs/` (from
  ready-player-one/seeds/weco_docs_markdown.zip) + github.com/WecoAI/aideml.
- Benchmarks: Kaggle, HuggingFace, ARC-AGI-3, SWE-Bench Pro, TerminalBench2,
  WebArena.
- Existing assets: agentdex-cli ADR-0009..0014 (Pokédex expeditions, Three
  Cards + Pareto verdict + Evolution Card, poke-env substrate, BENE-gated
  evolution), bene meta-harness (mh_* search/coevolution), local `weco` skill.

## Constraints

- **Model routing (user directive 2026-07-11, verbatim): "please do not use
  fable to do coding， use mroute for coding."** Fable coordinates, designs,
  reviews, audits; ALL implementation/coding work is dispatched via
  **`mroute execute`** (grok→gemini→spark chain) — request-capsule pattern per
  the orch-proj mroute-broker addendum. Fable never writes product code.
- BYO-creds local execution; agentdex never holds user Weco/Anthropic creds.
- Reuse before rebuild: expedition/Pareto-verdict/Evolution-Card machinery and
  ADR-0014's eval-gated evolution loop are prior art to extend, not discard.
- Existing uv-workspace layout (9 packages — README's "7" is doc drift) +
  FastAPI arena app on Lightsail remain the substrate unless the design
  argues otherwise explicitly.
- Vendor pre-commit red-gate quirk in this repo: merge on real gates only.

## Non-goals (v1)

- Hosted multi-tenant execution of user loops (later paid tier at most).
- Run-adapters for all six ladders (only 2-3 in v1).
- Stripe/payments (deferred with old GA).
- RL-based evolution (ADR-0014 already chose meta-harness evolution over RL).

## Risks / unknowns

- agent-evolution.com direct fetch fails TLS (github.io cert) — research via
  the GitHub repo; site structure may need JS rendering to inspect.
- Weco product surface may have moved past the docs seed (2026-07-10 snapshot).
- Benchmark ToS/licensing for mirroring leaderboards into a "market" page.
- SWE-Bench Pro / TerminalBench2 local-run cost on user machines.
- "Weco starts Claude Code" hook: exact mechanism (weco CLI? aideml agent?)
  must be verified from primary sources, not assumed.

## Milestones

### M1 — Research + architecture design [ACTIVE]

Outcome: an evidence-grounded architecture design the user confirms — design
doc + draft ADR-0015 (redesign) + refreshed milestone roadmap (M2..MN) in this
file.

Scope (in): 6-lane research sweep (Weng blog / agent-evolution taxonomy / weco+
aideml / benchmark landscape / existing agentdex architecture / bene mh);
design synthesis with module boundaries, data model, Pareto measurement
contract, weco-hook mechanism, website composition; explicit reuse-vs-replace
verdicts per existing package.
Scope (out): any implementation; board re-scoping of the 7 GA tasks (follows
the confirmed design).

Evidence required (evidence/M1/):
1. Per-lane research briefs (four-field contract) with primary-source cites.
2. `DESIGN.md` — the architecture doc (tech-lead:design response format).
3. Draft `docs/adr/0015-*.md` in this worktree.
4. Refreshed M2..MN roadmap in this file.
5. Fresh-thread 5-question audit + review pass.
6. User confirmation of the design (recorded verbatim).

### M2 — Pareto measurement engine (MVP moat)

Outcome: `adx measure --agent <dir> --ladder <id>` works end-to-end for
ARC-AGI-3 + TB2 with axes-at-budget score dicts and receipts.
Scope: AgentCandidate manifest + validation; LadderAdapter ABC + registry;
arc_agi3 + tb2_harbor adapters (out-of-process); receipt capture. Spikes:
weco economics (BYO --api-key credit behavior + retention policy), WebArena
vs SWE-Bench Pro footprint, bene Benchmark.score() cost/latency axes, ToS
browser session (mirror vs link-out per ladder), arXiv citation pass.
Evidence: measured runs on both adapters w/ score JSON + receipts; spike
briefs; audit + review.

### M3 — PokeAgent adapter + frontier ledger

Outcome: pokeagent adapter (poke-env substrate, adx-bot-1 auth, Gen 1 OU) +
adx_frontier (mh_bridge, gates.py class-differentiated policies, two-tier
trust ledger, frontier/promotion JSON export).
Evidence: adx-bot-1 ladder battles recorded; a candidate promoted through an
ACCEPT gate **via the collaborative MCP path** (the explicit
genome_from_candidate bridge in mh_bridge.py — the collaborative path never
auto-promotes on its own, per the P1 review finding); exported frontier.json;
audit + review.

### M4 — `adx evolve` 3-layer RSI loop

Outcome: `adx evolve` wraps `weco start claude` with the agentdex skill;
inner `weco run` optional; candidates flow to mh; kill-gated promotion;
data-flow disclosure at connect time.
Evidence: one full RSI session improving a candidate on a v1 ladder with
frontier movement + steering demo; audit + review.

### M5 — Website: knowledge × market × leaderboard

Outcome: agentdex_arena repurposed — taxonomy absorption (CC BY attribution,
claim-status labels), curated market (6 ladders + HF substrate, link-out),
leaderboard rendering frontier exports, one navigation spine.
Evidence: site builds + serves locally; taxonomy attribution verified; audit
+ review.

### M6 — Deploy + GA-blocker re-scope

Outcome: auth/DNS/deploy tasks from the old GA re-scoped to serve the new
site; deployed on the Lightsail box; old-GA board cards dispositioned.
Evidence: live site probe; board re-scope record; audit + review.

## Decisions log (append-only)

- 2026-07-11: project bootstrapped; supersession decision recorded (see
  parent_decision header); MVP order = engine → loop → site; ladder depth =
  curate 6 / run 2-3; execution locus = user-local BYO creds.
- 2026-07-11 (post-research): 6-lane research sweep + gap critic landed
  (`evidence/M1/research/`). User supplied
  docs.weco.ai/using-weco/claude-in-dashboard: **`weco start claude` verifies
  the hook** — Weco wrapper starts Claude Code locally (default local Claude
  auth; optional `--billing weco` proxy), conversation streams to the dashboard
  for live steering. The research lane's "inversion" finding was stale w.r.t.
  this feature; both integration directions exist (`weco setup claude-code`
  skill AND `weco start claude` wrapper).
- 2026-07-11 (taxonomy): two-class ladder taxonomy adopted (requirement 5) —
  3 live-adversarial + 3 static + HF-as-substrate; class-differentiated
  kill-gate semantics; PokeAgent diligence PASS.
- 2026-07-11 (loop + adapters, user answers verbatim): loop composition =
  "3-layer: weco drives, mh gates" — `adx evolve` wraps `weco start claude`;
  Claude Code runs the outer RSI session with an agentdex skill, calls
  `weco run` for inner-loop code mutations, submits candidates to the bene mh
  frontier; kill-gated promotion decides leaderboard entry. v1 run-adapters =
  "ARC-AGI-3 + TB2 + PokeAgent" — two live-adversarial + one static, covering
  both gate classes; WebArena vs SWE-Bench Pro slot decided by M2 footprint
  spike.
