# agentdex-cli — Agent Pokédex

Async co-opetition (合作竞争) orchestrator across subscription-CLI baselines
(Claude Code, Codex app-server, Manus / codex-web fallback). Produces a
Pokédex-style record of each Expedition: 3 Result Cards, 1 Pareto verdict,
1 Evolution Card with mutation seeds, plus full per-bridge traces.

See [ADR-0009](docs/adr/0009-kaos-substrate-and-retrofit-framing-pokedex-pivot.md) for the
unifying architecture and [CLAUDE.md](CLAUDE.md) for codebase doctrine.

## Quickstart

```bash
# 1. Clone + enter
git clone git@github.com:good-night-oppie/agentdex-cli.git ~/gh/agentdex-cli
cd ~/gh/agentdex-cli

# 2. uv workspace sync (resolves all 7 packages)
uv sync

# 3. Install bridges / cli / observe as editable
uv pip install -e packages/adx_bridges -e packages/agentdex_cli \
                -e packages/agentdex_observe -e packages/agentdex_engine \
                -e packages/kaos

# 4. (Optional) install Manus camoufox backend
uv pip install camoufox && uv run python -m camoufox fetch

# 5. Probe one baseline against the frozen NVIDIA task
uv run adx bridge probe --bridge claude --task nvidia-earnings-infographic

# 6. Run the full M5 Expedition (mocked path = no live live live live API keys needed)
uv run adx expedition \
    --task nvidia-earnings-infographic \
    --baselines claude,codex,manus \
    --judge claude-haiku-4.5 \
    --output expeditions/nvidia-q3-fy2026-exp-001/ \
    --mocked
```

Artifacts land under `expeditions/<id>/`:
- `task_card.yaml`
- `result_card_<agent>.yaml` (×3)
- `pareto_verdict.yaml`
- `evolution_card.yaml`
- `trace/<agent>_full_trace.jsonl` (×3)

KAOS lineage is persisted under `kaos.db` (or `--kaos-db <path>`).

## Architecture

```
                           ┌──────────────────────────┐
                           │  adx CLI (agentdex_cli)  │
                           │  bridge probe / expedition│
                           └──────────┬───────────────┘
                                      │
                          ┌───────────┴───────────────┐
                          │  agentdex_engine          │
                          │  Three Cards + Oracle     │
                          │  + Pareto + Expedition    │
                          └─┬───────────┬─────────────┘
                            │           │
              ┌─────────────┘           └───────────────┐
              ▼                                         ▼
  ┌────────────────────┐                  ┌──────────────────────┐
  │  adx_bridges       │                  │  agentdex_plugin     │
  │  Claude / Codex /  │                  │  Hermes gateway      │
  │  Manus (Camofox)   │                  │  entry-point + tools │
  └─────────┬──────────┘                  └────────────┬─────────┘
            │                                          │
            ▼                                          ▼
     subscription CLIs                       hermes_cli.plugins
     (stdio JSON-RPC)                        (PluginContext + manifest)
```

Two-tier substrate:
- **Hot tier (M6+):** `helios` daemon — mutation-seed scoring in-process.
  Vendors only the Python client at `packages/helios_client/`.
- **Warm/cold tier (M5):** `packages/kaos/` — durable agent/checkpoint/blob
  store. Lineage entries live here.

## Packages (uv workspace)

| Package | Purpose |
|---------|---------|
| `packages/agentdex_cli` | `adx` shell + orchestrator + bridge probe |
| `packages/agentdex_engine` | Three Cards + Oracle + Pareto + Expedition |
| `packages/agentdex_plugin` | Hermes plugin discoverable via entry-points |
| `packages/adx_bridges` | Claude / Codex / Manus / codex-web bridges |
| `packages/agentdex_observe` | Langfuse glue (anthropic + openai wraps, trace_session/turn) |
| `packages/helios_client` | Python client to external `helios` daemon |
| `packages/kaos` | Vendored KAOS substrate (squashed git subtree) |

## Tests

```bash
uv run pytest packages/agentdex_engine/tests/ -v   # 28 tests (Cards + Oracle + Pareto)
uv run pytest packages/adx_bridges/tests/ -v       # 9 tests (mock + live live live)
uv run pytest packages/agentdex_cli/tests/ -v      # 9 smoke (Expedition end-to-end)
ADX_LIVE_BRIDGES=1 uv run pytest packages/adx_bridges/tests/ -v   # live subscription CLIs
```

## Doctrine + references

- [CLAUDE.md](CLAUDE.md) — codebase doctrine (Hermes retrofit, KAOS subtree,
  two-tier substrate, context discipline).
- [ADR-0009](docs/adr/0009-kaos-substrate-and-retrofit-framing-pokedex-pivot.md) — unifying
  meta-ADR (Pokédex framing + async co-opetition + Langfuse observability).
- Superlinear post "Agent Pokédex" §4 / §8 — origin of the Three Cards
  pattern + Repair Oracle as mutation seed source.

## License

Internal — see repo metadata.
