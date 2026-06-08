# IDEAL_EXPERIENCE — agentdex-cli

> Cursor G14: define what success looks like BEFORE choosing metrics. Evals derive from this; the doc is the anchor.

## Who is agentdex-cli for?

A developer or researcher evaluating multiple agentic coding/research subscriptions (Claude Code, Codex, Manus) against the SAME task and wanting a reproducible, comparable verdict — not vibes-based "I think Claude was better." They run subscription CLIs they already pay for; agentdex-cli orchestrates them, scores them, and persists the receipt.

## The ideal session looks like

- **User runs:** `adx expedition --task nvidia-earnings-infographic --baselines claude,codex,manus --judge claude-haiku-4.5`
- **agentdex-cli does:** spawns one long-lived `hermes gateway --profile agentdex`, drives 3 baselines sequentially through bridges, each baseline produces a trace + ResultCard, soft Oracle judge scores narrative quality via `agentdex_observe.anthropic_client()` (Langfuse-wrapped), Pareto judge picks winner OR `no_clear_winner`, EvolutionCard collects mutation seeds tagged `seed_provenance ∈ {structural, learned}`, KAOS persists the lineage entry; all artifacts written to `expeditions/<id>/`.
- **User feels:** **certain.** The same NVIDIA bundle frozen by BLAKE3 hash produces the same Pareto verdict tomorrow. The Pokédex entry has 3 ResultCards + 1 Pareto + 1 EvolutionCard, each carrying its Langfuse trace URL, so any disagreement with the verdict drills into the actual reasoning chain in one click. No "trust me, the LLM said so."

## Anti-patterns (NOT agentdex-cli's job)

- **Not a battle-replay UI.** Pokémon Showdown is the marketing analogy; Pokédex (catalog + receipt + lineage) is the product. We render YAML cards and Langfuse links, not live combat animations.
- **Not a subscription-replacement broker.** We DRIVE Claude/Codex/Manus subscription CLIs the user already pays for. We do not host inference, do not aggregate billing, do not proxy API keys.
- **Not a vibes leaderboard.** Every claim cites a source file + line; every Oracle verdict is grounded in `tasks/<id>/oracle/spec.yaml`. Pure LLM-as-judge without ground-truth anchor is a Phase-6 calibration target, not the headline value.
- **Not a real-time agent orchestrator.** M5 ships sequential baseline runs. Concurrent multi-agent live coordination is post-M8.

## Failure modes we care about most

1. **Reward-hacked Pareto verdict** — winning baseline got there by gaming a weak Oracle rubric, not by solving the task. Mitigation: Oracle repair flagger (P6) emits `seed_provenance="structural"` seeds that surface weak rubrics in the EvolutionCard; soft-judge calibration backtest (P6 `oracle/calibration.py`) gates judge accuracy < 0.7.
2. **Non-reproducible Expedition** — re-running the same `bundle.yaml` produces a different verdict. Mitigation: BLAKE3 source-bundle hash freeze (P3); `expected_outputs/sample-claim-evidence-map.yaml` is the ground-truth anchor.
3. **Trace orphaning** — judge or bridge span doesn't parent to Expedition trace; user clicking the Langfuse URL lands on an isolated child. Mitigation: Phase-4 R3 spike forces explicit pass/fail decision on cross-process trace propagation; per-baseline-root fallback documented in EvolutionCard `langfuse_trace_urls`.
4. **Tautological MVP gate** — M5 passes because seeds always fire mechanically (structural), not because system learned anything (learned). Mitigation: `Seed.seed_provenance: Literal["structural","learned"]` makes this distinction typed + auditable; M7 raises the bar to ≥1 learned seed.
5. **Subscription-CLI drift** — Claude Code or Codex CLI ships breaking output-format change; bridge silently parses garbage. Mitigation: bridge tests use recorded fixtures + a smoke probe at session start.

## How we'll know we got there (deferred to EVAL.md)

See `EVAL.md` — every eval criterion traces back to a line in this doc. If an eval doesn't anchor here, it's metric-chasing.
