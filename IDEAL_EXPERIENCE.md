---
title: "IDEAL_EXPERIENCE — agentdex-cli"
status: active
owner: "@EdwardTang"
created: 2026-06-09
updated: 2026-06-09
type: reference
scope: .
layer: cross-cutting
cross_cutting: true
---

# IDEAL_EXPERIENCE — agentdex-cli

> Cursor G14: define what success looks like BEFORE choosing metrics. Evals derive from this; the doc is the anchor.

## Who is agentdex-cli for?

A developer or researcher evaluating multiple agentic coding/research subscriptions (Claude Code, Codex, Manus) against the SAME task and wanting a reproducible, comparable verdict — not vibes-based "I think Claude was better." They run subscription CLIs they already pay for; agentdex-cli orchestrates them, scores them, and persists the receipt.

## The ideal session looks like (async co-opetition — per ADR-0009 §Amendment-2026-06-08)

### Synchronous wrapper (MVP M5 — the shipped, load-bearing path)

- **User runs:** `adx expedition --task nvidia-earnings-infographic --baselines claude,codex,manus --judge claude-haiku-4-5`
- **agentdex-cli does:** in one process, drives each baseline sequentially through its bridge (the pre-0.16 `hermes gateway --profile agentdex` spawn-once framing was vapor — ADR-0009 §Amendment-2026-06-10; the Hermes integration surface is the plugin toolset via `hermes chat -t agentdex`), writes `expeditions/<id>/result_card_<baseline>.yaml` + `trace/<baseline>_full_trace.jsonl` per baseline, runs soft Oracle judge via `agentdex_observe.anthropic_client()` (Langfuse-wrapped, span explicit per the codereview-fix-1 `_judge_observation` context manager), Pareto judge produces `winner` OR `no_clear_winner`, EvolutionCard aggregates mutation seeds with `seed_provenance ∈ {structural, learned}`, KAOS persists the lineage entry.

> **Doctrine note (harness-praxis tracer follow-up, 2026-06-09):** this sync
> wrapper is the ONLY path the CLI ships at M5. Earlier revisions of this doc
> called the async primitives below "load-bearing" while only the sync
> wrapper had landed; that was G14 drift (ideal-experience anchor named one
> thing, code shipped another). The async primitives are the M6+ target
> shape, NOT a shipped surface — see the next section.

### Async primitives (M6+ TARGET — not shipped yet)

These commands are the POST-M5 surface, motivated by users whose baseline
runs are naturally hours or days apart (subscription rate-limits, daily
quotas, Camofox availability windows). They are NOT in `cli.py` today; the
sync wrapper above must be used until M6 lands these subcommands.

```
adx expedition init    --task nvidia-earnings-infographic --baselines claude,codex,manus
adx expedition run     --expedition <id> --baseline claude       # today
adx expedition run     --expedition <id> --baseline codex        # tomorrow morning
adx expedition run     --expedition <id> --baseline manus        # whenever Camofox cooperates
adx expedition finalize --expedition <id> --judge claude-haiku-4-5
```

When shipped (M6+ migration), each `run` invocation will be a unit of work
that ensures the Hermes gateway is live, drives ONE baseline, writes that
baseline's ResultCard + trace, and exits. `finalize` then aggregates all
required ResultCards and produces the Pareto verdict + EvolutionCard +
KAOS lineage entry. No coordination between baselines required; the
orchestrator becomes a state machine over ResultCards.

### User feels

**certain.** The same NVIDIA bundle frozen by BLAKE3 hash produces the same Pareto verdict tomorrow (or three days later when the last baseline finally runs). The Pokédex entry has 3 ResultCards + 1 Pareto + 1 EvolutionCard, each carrying its Langfuse trace URL, so any disagreement with the verdict drills into the actual reasoning chain in one click. No synchronous coordination required; no "trust me, the LLM said so." Co-opetition (合作竞争), not battle.

## Anti-patterns (NOT agentdex-cli's job)

- **Not a battle.** Co-opetition (合作竞争), not adversarial battle. Per ADR-0009 §Amendment-2026-06-08: baselines are not fighting each other; they run the same task independently and asynchronously, and the Pareto judge aggregates ResultCards when they're all in. No synchronous side-by-side compete. No live combat animation. Pokédex (catalog) survives as the product metaphor; Pokémon Showdown does not.
- **Not a subscription-replacement broker.** We DRIVE Claude/Codex/Manus subscription CLIs the user already pays for. We do not host inference, do not aggregate billing, do not proxy API keys.
- **Not a vibes leaderboard.** Every claim cites a source file + line; every Oracle verdict is grounded in `tasks/<id>/oracle/spec.yaml`. Pure LLM-as-judge without ground-truth anchor is a Phase-6 calibration target, not the headline value.
- **Not a real-time agent orchestrator.** M5 ships sequential baseline runs. Concurrent multi-agent live coordination is post-M8.

## Failure modes we care about most

1. **Reward-hacked Pareto verdict** — winning baseline got there by gaming a weak Oracle rubric, not by solving the task. Mitigation: Oracle repair flagger (P6) emits `seed_provenance="structural"` seeds that surface weak rubrics in the EvolutionCard; soft-judge calibration backtest (P6 `oracle/calibration.py`) gates judge accuracy < 0.7.
2. **Non-reproducible Expedition** — re-running the same `bundle.yaml` produces a different verdict. Mitigation: BLAKE3 source-bundle hash freeze (P3); `expected_outputs/sample-claim-evidence-map.yaml` is the ground-truth anchor.
3. **Trace orphaning** — judge or bridge span doesn't parent to Expedition trace; user clicking the Langfuse URL lands on an isolated child. Mitigation: Phase-4 R3 spike forces explicit pass/fail decision on cross-process trace propagation; per-baseline-root fallback documented in EvolutionCard `langfuse_trace_urls`.
4. **Tautological MVP gate** — M5 passes because seeds always fire mechanically (structural), not because system learned anything (learned). Mitigation: `Seed.seed_provenance: Literal["structural","learned"]` makes this distinction typed + auditable; M7 raises the bar to ≥1 learned seed.
5. **Subscription-CLI drift** — Claude Code or Codex CLI ships breaking output-format change; bridge silently parses garbage. Mitigation: bridge tests use recorded fixtures + a smoke probe at session start.
6. **Upstream 5xx cascade** — one transient Cloudflare 525 / 502 on the judge path takes down EVERY baseline because the orchestrator's per-baseline `try/except` wraps both `bridge.send` AND `oracle.evaluate`. Mitigation (PR #18 + PR #20): `oracle/soft.py:_call_judge_with_retries` runs 3 attempts with exponential backoff against an open-ended exception classifier (class name + body markers covering anthropic / openai / gemini / cohere shapes); explicit `"retryable":false` / `"owner_action_required":true` flags in the body skip the retry budget so origin-config failures surface immediately instead of burning the per-baseline timeout window.

## How we'll know we got there (deferred to EVAL.md)

See `EVAL.md` — every eval criterion traces back to a line in this doc. If an eval doesn't anchor here, it's metric-chasing.
