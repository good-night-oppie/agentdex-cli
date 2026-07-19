---
title: "agentdex-cli — Agent Pokédex"
status: active
owner: "@EdwardTang"
created: 2026-06-09
updated: 2026-07-19
type: reference
scope: .
layer: cross-cutting
cross_cutting: true
---

# agentdex-cli — Agent Pokédex

[![GA Release](https://img.shields.io/badge/status-GA-brightgreen)](https://github.com/good-night-oppie/agentdex-cli/releases)
[![PyPI](https://img.shields.io/badge/pypi-agentdex--cli-blue)](https://pypi.org/project/agentdex-cli/)

**The model-allocation loop that learns which model does which job better.**

agentdex is a CLI-based agent orchestration system that runs a three-step cycle:

1. **Interview** — captures how you want models orchestrated (objectives, pool, constraints, explore/exploit)
2. **Run** — allocates and dispatches a task across your pool, selects winner by constrained-Pareto frontier
3. **Openbox** — self-service backend onboarding (binds pool names to invokable backends, zero credentials stored)

Together they form an *evolution market*: each run appends a seed ledger row, and over iterations the system learns which model sits on the frontier for each job signature under your objective.

> [Landing page](https://agentdex.builders/adx/) | [GitHub](https://github.com/good-night-oppie/agentdex-cli) | [ADR-0009](docs/adr/0009-kaos-substrate-and-retrofit-framing-pokedex-pivot.md)

## Quickstart

```bash
# 1. Install (uv workspace)
git clone git@github.com:good-night-oppie/agentdex-cli.git ~/gh/agentdex-cli
cd ~/gh/agentdex-cli
uv sync

# 2. Configure your orchestration policy
adx interview --out .agentdex/orchestration.yaml

# 3. Bind pool names to backends
adx openbox init --policy .agentdex/orchestration.yaml
adx openbox check

# 4. Run a task (fake engine = no network, no secrets)
adx run --task my-task --policy .agentdex/orchestration.yaml
```

Or install from PyPI:

```bash
pip install agentdex-cli
adx interview
adx run --task my-task
```

## Architecture

```
                        ┌──────────────────────────────┐
                        │         adx CLI               │
                        │  (agentdex_cli shell +        │
                        │   orchestrator entrypoint)    │
                        └──────┬───────┬──────┬─────────┘
                               │       │      │
                 ┌─────────────┘       │      └──────────────┐
                 ▼                     ▼                     ▼
     ┌────────────────────┐ ┌──────────────────┐ ┌──────────────────────┐
     │   adx interview    │ │    adx run       │ │   adx openbox        │
     │  Interactive Q&A   │ │ Allocation loop  │ │  Backend probing     │
     │  → policy YAML     │ │ → frontier.json  │ │  (zero creds stored) │
     │  (objectives,      │ │ → seed ledger    │ │                      │
     │   pool, constraints)│ │ → winner select  │ │                      │
     └────────┬───────────┘ └────────┬─────────┘ └──────────┬───────────┘
              │                      │                      │
              ▼                      ▼                      ▼
     ┌──────────────────────────────────────────────────────────┐
     │                 agentdex_engine                           │
     │  FrontierLedger (Pareto selection) +                     │
     │  adx_frontier (constrained-Pareto axes)                  │
     └────────────┬─────────────────────────────┬───────────────┘
                  │                             │
                  ▼                             ▼
     ┌──────────────────┐          ┌──────────────────────────┐
     │  adx_frontier     │          │   adx_bridges            │
     │  AgentCandidate   │          │  TeamClaude loopback     │
     │  Axis manifest    │          │  gateway (--engine       │
     │  Pre-run gate     │          │  bridges)                │
     └──────────────────┘          └──────────────────────────┘
```

### Three-Capability Flow

```
Interview                          Run                             Learn
────────                           ───                             ─────
adx interview                      adx run --engine fake           ledger.append(sig, model, axes)
   │                                    │                              │
   ├─ job_types ──────────────────────►  ├─ classify task → signature   │
   ├─ objective ──────────────────────────┼─ sort lexicographic ──────────┘
   ├─ pool      ──────────────────────────┼─ allocate (exploit/explore)  │
   ├─ gate      ──────────────────────────┼─ dispatch models             │
   ├─ constraints ────────────────────────┼─ prune by constraint         │
   └─ explore_rate ───────────────────────┼─ non-dominated sort          │
                                          └─ winner → frontier.json      │
                                                                         │
Openbox                                     ◄─────────────────────────────┘
───────
adx openbox init   (skeleton from pool)
adx openbox check  (probe each backend)
```

## Commands

| Command | Purpose |
|---------|---------|
| `adx interview` | Fixed interactive Q&A capturing how agentdex should orchestrate your models. Writes `.agentdex/orchestration.yaml`. Pass `--non-interactive` for CI/smoke defaults. |
| `adx run` | The allocation loop. `--engine fake` (default) demonstrates deterministically. `--engine bridges` dispatches live through loopback TeamClaude gateway. Outputs `.agentdex/frontier.json` + seed JSONL. |
| `adx openbox` | Self-service backend onboarding. `init` seeds `.agentdex/openbox.yaml` from the interview pool. `check` probes each backend's liveness (MISSING / READY / NO-AUTH / TIMEOUT). Zero credential values stored. |
| `adx bridge probe` | (v1 legacy) One-turn probe through a baseline bridge. |
| `adx expedition` | (v2 legacy) Full expedition: load task, resolve bridges, run orchestrator, write result cards. |
| `adx pool` | Manage pool mode (local loopback vs remote), base URL, key path. |
| `adx deploy` | Deploy agentdex as a Docker service. |
| `adx arena` | Defer to the Arena TUI (Pokemon Showdown ladder battles). |

## Packages (uv workspace)

| Package | Purpose |
|---------|---------|
| `packages/agentdex_cli` | `adx` shell + orchestrator entrypoint + interview/run/openbox commands |
| `packages/agentdex_engine` | Expedition orchestration, Three Cards, Pareto verdict, Evolution Card |
| `packages/adx_frontier` | `AgentCandidate` manifest, frontier axes, constrained-Pareto selection |
| `packages/adx_bridges` | Claude / Codex / Manus bridges |
| `packages/adx_ladders` | Shared ladder engine for arena showdowns |
| `packages/adx_showdown` | Pokemon Showdown ladder adapter |
| `packages/agentdex_arena` | Arena TUI for head-to-head battles |
| `packages/agentdex_plugin` | Hermes plugin (entry-point discoverable) |
| `packages/agentdex_observe` | Langfuse glue (anthropic + openai wraps, trace_session/turn) |
| `packages/kaos` | Vendored KAOS substrate (durable agent/checkpoint/blob store) |

## Tests

```bash
# Unit tests across all packages
uv run pytest packages/ -v

# Bridge integration tests (live subscription CLIs)
ADX_LIVE_BRIDGES=1 uv run pytest packages/adx_bridges/tests/ -v
```

## Doctrine + references

- [CLAUDE.md](CLAUDE.md) — codebase doctrine (Hermes retrofit, KAOS subtree, two-tier substrate, context discipline)
- [ADR-0009](docs/adr/0009-kaos-substrate-and-retrofit-framing-pokedex-pivot.md) — unifying meta-ADR (Pokedex framing + async co-opetition + Langfuse observability)
- [ADR-0015](docs/adr/0015-frontier-ledger-run-allocator.md) — frontier ledger, run allocator, adx_frontier engine contract
- `docs/adr/0016-interview-cmd.md` — interview command design
- `docs/adr/0017-openbox-cmd.md` — openbox (zero-credential backend onboarding)
- Superlinear post "Agent Pokedex" §4 / §8 — origin of the Three Cards pattern + Repair Oracle as mutation seed source

## License

Internal — see repo metadata.
