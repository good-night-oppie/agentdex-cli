---
title: "ADR-0014: poke-env battle substrate + Codex/BENE eval-gated evolution"
status: draft
owner: "@EdwardTang"
created: 2026-06-18
updated: 2026-06-19
type: reference
scope: docs/adr
layer: cross-cutting
cross_cutting: true
---

# ADR-0014: poke-env battle substrate + Codex/BENE eval-gated evolution

> **Status: proposed (design-first), Phase-1 substrate already validated.**
> Per the owner's calibrated fleet goal (2026-06-18): *let the open-source coding
> agent **openai/codex** use **agentdex-cli (CLI or MCP)** to run poke-env
> **self-play** ([self_play.html](https://poke-env.readthedocs.io/en/stable/examples/self_play.html))
> — but **instead of RL**, the codex agent doing self-play runs **meta-harness
> evolution loops** powered by agentdex-cli's Three-Cards/Pareto and **gated by
> BENE** (`~/gh/bene-main`).* The substrate retrofit (poke-env + our own PS server
> on `54.203.252.69`, replacing the "stupid" sidecar/TUI) is the enabler; the
> headline deliverable is the codex-driven self-play + meta-harness evolution
> loop. The whole fleet (orchestrated by harness) splits the work; this ADR is
> adx-cli's lane. The local substrate is already proven (see §6).

## 1. Context — what exists today vs. the target

**Today (the substrate being replaced):** `packages/adx_showdown/sidecar.mjs` is
an embedded Node `BattleStream` multiplexer driven over an NDJSON/stdio protocol
by `Sidecar.py` + `SidecarPool` (battle_id partition router). The gateway's
`battle_begin/_advance/_finish` call `sidecar.request("start"/"step")`. This is
bespoke, hard to evolve, and the human play surface on top of it is thin.

**Target:** [poke-env](https://github.com/hsahovic/poke-env) — the mature Python
interface to Pokémon Showdown — becomes the single battle-execution substrate,
talking over websocket to a **real Pokémon Showdown server**. The repo tracks the
`pokemon-showdown@0.11.10` dependency in `packages/adx_showdown/package.json` +
`package-lock.json`, but `node_modules/` is gitignored — so a clean checkout
materializes the server binary with `npm ci` (or `npm install`) in
`packages/adx_showdown`, then boots it via `scripts/adx_ps_server.sh`. That
launcher also performs the one-time `cp config/config-example.js config/config.js`
step the npm package omits (`0.11.10` ships only the example) and pins
`bindaddress` to `ADX_PS_HOST`. It runs on `127.0.0.1` for local dev and on
`54.203.252.69` on the box — **no new _Python_ runtime dependency** (the PS server
is a Node dev-setup step, not an importable package dep).

## 2. Decision

### D1 — poke-env + a real PS server replace the sidecar entirely
The `sidecar.mjs` + `Sidecar.py` + `SidecarPool` layer is **deleted, not
wrapped**. Each arena participant becomes a `poke_env.player.Player` subclass.
Connection is a custom `ServerConfiguration("ws://HOST:PORT/showdown/websocket",
auth_url)` + per-player `AccountConfiguration`. poke-env's one-battle-per-room
model plus multiple `Player` instances subsumes the old partition-by-battle_id
concern.

### D2 — the gateway's public contract is preserved byte-for-byte
`ConsentAuthority` (Ed25519 mint/verify, PoP-per-battle, owner-pooled battle
quota per ADR-0013, membership), `BadgeAuthority`, the `EventLog` durable
append (Class-A append-before-publish), ladder recompute, replay artifacts, and
the per-owner concurrency cap all stay unchanged. Only the **internals** of
`battle_begin/_advance/_finish` change — they orchestrate a poke-env battle
instead of a sidecar request. This protects the ADR-0011/0013 invariants and the
40+ arena tests' wire assertions.

### D3 — the visitor turn stays HTTP; the TUI wire is untouched
The visitor's `Player.choose_move(battle)` blocks on a per-battle asyncio queue
fed by the existing `/battle/{id}/choose` endpoint, so `arena_client` /
`arena_tui` and the MCP choose tools need zero wire changes. Improving the TUI's
polling UX is a separate, non-blocking concern off the substrate critical path.

### D4 — Three-Cards / Pareto / oracle stay the verdict source of truth
We add a thin `pokeenv_battle_report()` adapter that converts an
`AbstractBattle` outcome (`.won`, `.turn`, team state, protocol-log path) into the
JSON battle report `BattleOracle` already consumes. The expedition flow
(`ResultCard.pass_rate`, `pareto_verdict` over (pass_rate↑, cost↓, speed↓),
`EvolutionCard` mutation seeds, KAOS lineage) is otherwise unchanged.

### D5 — self-play + meta-harness evolution (NOT RL); codex is the agent
The poke-env `self_play.html` example trains one shared policy with PPO
(Stable-Baselines3, a gym env, `ppo.learn()`). We keep the **self-play
structure** — an agent battles copies/variants of itself, both perspectives count,
win-rate is the signal — but **replace the RL optimizer with meta-harness
evolution**: the "learning step" is a code/prompt/strategy mutation, not a
gradient update. The **agent is openai/codex** (`~/gh/codex`, `codex exec --dangerously-bypass-approvals-and-sandbox`),
which drives the loop *through agentdex-cli's CLI/MCP surface* (D8): it runs a
self-play match, reads the battle report + win-rate, proposes a mutated
`choose_move` policy / prompt / harness, and re-plays. agentdex-cli supplies the
Three-Cards/Pareto machinery (each candidate → `ResultCard`; `pareto_verdict`
ranks; `EvolutionCard` carries the mutation seeds). **BENE** (`~/gh/bene-main`)
supplies the eval-gated promotion: a win-rate `Probe` with a hash-locked kill
gate (`win_rate >= incumbent + delta`) over N self-play battles; `promote()`
blocks activation without an ACCEPT verdict; `MetaHarnessSearch.Benchmark.evaluate`
= `measure_win_rate(candidate_player, incumbent_player)`. Codex `finish_success`
is hard-gated on the BENE verdict — **never** the coordinator model's
self-assessment.

### D8 — agentdex-cli exposes the self-play + evolve surface to codex (CLI + MCP)
Because codex is the *user* of agentdex-cli, the loop's operations are first-class
agentdex-cli verbs, reachable both as CLI commands and as MCP tools (the existing
Hermes `agentdex` toolset): start a self-play match on the PS server, fetch the
resulting battle report/win-rate, run one evolution iteration (mutate → battle →
Pareto → BENE gate), and read the current champion + lineage. This keeps the
codex agent decoupled from agentdex internals — it calls tools, agentdex-cli runs
poke-env + BENE underneath.

### D9 — non-goals (this lane)
No PPO/Stable-Baselines3/gradient training is built (the owner said "instead of
RL"); poke-env's gym/`SinglesEnv` env is a *possible future RL baseline*, not on
this path. The TUI's polling UX is improved separately, off the substrate
critical path. Fleet-level task splitting is harness's job; this ADR scopes only
adx-cli's lane.

### D6 — replay equivalence is asserted against PS, not the retired sidecar
poke-env-over-PS does not give the sidecar's synchronous per-step hash guarantee.
We do **not** chase byte-hash equivalence with the old sidecar. Instead we capture
the PS server's raw protocol stream (seed, teams, inputLog, keyLines) into the
existing replay artifact and keep a re-sim audit path against the vendored
simulator. Equivalence is asserted against Pokémon Showdown itself.

### D7 — local-first, then the box
Develop against a local PS server (`127.0.0.1:8000`); the identical config swap
points at `54.203.252.69`. `gen9randombattle` is frozen for the first phases (no
team-builder coupling); `gen9ou` + `Teambuilder` packed teams come only once the
loop is green.

## 3. Phasing — tiny-PR roadmap

**Spine (critical path to the goal): the codex self-play meta-harness loop.**

- **Phase 1 — substrate + this ADR (VALIDATED).** Local PS server launcher
  (`scripts/adx_ps_server.sh`); poke-env installed in the dev venv (`uv pip
  install poke-env>=0.15` — a dev dependency, **not** a declared workspace dep, so
  the genome/fitness path stays import-safe without it; see §5); and
  `scripts/spikes/{two_random_players,decision_seam}.py` proving a battle + the
  `choose_move` decision seam + win-rate signal.
- **Phase 2 — policies as poke-env Players.** A `Policy`/`Player` abstraction
  (the unit codex mutates): re-home the existing bot policies
  (`max_damage/heuristic/stall/trick_room/hyper_offense/balance`) as
  `poke_env.Player` subclasses; unit-test vs the local server.
- **Phase 3 — self-play harness (no RL).** Mirror `self_play.html`'s structure —
  an agent battles copies/variants of itself, both perspectives count — but the
  output is a battle report + win-rate, NOT a PPO update. `selfplay(policy_a,
  policy_b, n)` → win-rate + per-battle reports.
- **Phase 4 — Three-Cards over self-play battles.** `pokeenv_battle_report()`
  adapter (`AbstractBattle` → the JSON report `BattleOracle` consumes); a
  self-play expedition → `ResultCard.pass_rate` + `pareto_verdict` +
  `EvolutionCard` mutation seeds.
- **Phase 5 — BENE eval-gated promotion.** `measure_win_rate(candidate,
  incumbent, n)`; a win-rate `Probe` (hash-locked gate, `>= incumbent + delta`) +
  admissibility self-test + kill-gated `promote()` + `HeldoutGate`.
- **Phase 6 — agentdex-cli CLI + MCP surface for the loop (D8).** First-class
  verbs/tools codex calls: run a self-play match, fetch the report/win-rate, run
  one evolution iteration (mutate → battle → Pareto → BENE gate), read the
  champion + lineage. Wire into the existing Hermes `agentdex` MCP toolset.
- **Phase 7 — codex auto-drive runs the loop end-to-end.** `codex exec --dangerously-bypass-approvals-and-sandbox`
  over "raise win-rate vs the incumbent via mutation", driving agentdex-cli's
  MCP/CLI; `finish_success` hard-gated on a BENE ACCEPT verdict; promoted
  champions recorded with engram/KAOS lineage. Then deploy the PS server to
  `54.203.252.69` (gated on box access — §5).

**Secondary track (parallel, not on the goal's critical path): public-arena
substrate swap.** Refactor `ArenaGateway.battle_begin/_advance/_finish` onto
poke-env behind an `ADX_BATTLE_BACKEND=pokeenv|sidecar` flag, port the 40+ arena
tests from sidecar mocks to poke-env fakes, and retire `sidecar.mjs` /
`Sidecar.py` / `SidecarPool` — preserving every platform invariant (D2). This
upgrades the *public* arena to the same substrate the codex loop already uses, but
the codex self-play loop ships without waiting on it.

## 4. Alternatives considered

- **Wrap the sidecar behind a poke-env-shaped facade** instead of deleting it —
  keeps two simulators alive, doubles the test surface, and never lets the team
  benefit from poke-env's `Player`/env ecosystem. Rejected; delete the sidecar.
- **poke-env's gym/PettingZoo `SinglesEnv` for an RL agent** instead of the
  `Player.choose_move` seam — viable later for an RL baseline, but the
  Three-Cards/Codex/BENE loop drives strategy via code/prompt mutation, not
  gradient training, so the `Player` seam is the MVP. Kept as a future option.
- **Battle on the public Smogon server** instead of self-hosting — rate limits,
  no seed control, not disposable. Rejected; self-host the vendored PS binary.

## 5. Open items / blockers

- **poke-env not yet a declared dependency:** poke-env (`>=0.15`) is installed
  ad-hoc in the dev venv — it is **not** in any `pyproject.toml` or `uv.lock`, so a
  clean `uv sync` does not provide it. Reproduce Phase 1 from a clean checkout
  with `uv pip install poke-env>=0.15` (or a future `selfplay` optional-dependency
  extra) before running `scripts/spikes/*.py` or the `adx_showdown.selfplay`
  tests. Keeping poke-env out of the hard deps is deliberate: the genome/fitness
  modules import-guard it so they load without poke-env, and only the live
  runner/baselines need the server-facing client.
- **Box access:** SSH to `54.203.252.69` currently fails (`Permission denied
  (publickey)`); the key `~/.ssh/ssh-ed25519-agentdex-arena-europa` is a valid
  ed25519 key but the username is unknown. adx-core owns the infra — either a
  deploy key/username is provided or adx-core runs the PS server + poke-env
  on-box. Phase 6 deploy is gated on this.
- **Replay reconstruction:** confirm poke-env's exposed message stream is enough
  to rebuild the `inputLog/keyLines/seed` artifact, or add a server-side
  `BattleStream` tap.
- **Seeded determinism:** can we fix the PS RNG seed per battle for reproducible
  re-sim audits + BENE probes, or must the probe average over larger N?
- **Concurrency budget** of one PS server at the box's resources, and how the
  per-owner cap maps to PS room limits.

## 6. Consequences

- Phase-1 substrate is **already proven locally**: the vendored/real PS server
  boots, and poke-env drives `gen9randombattle`s end-to-end (two `RandomPlayer`s
  complete a battle; a `MaxBasePower` `choose_move` beat `RandomPlayer` 10/10 —
  proving the decision seam and that win-rate is a clean eval signal for the
  evolution loop).
- The arena keeps every paid/free platform feature and the Three-Cards expedition
  flow; the change is contained to the battle-execution internals + a new
  evolution loop.
- A real PS substrate unlocks the full poke-env ecosystem (teams, formats, the
  RL env) and a credible agent-vs-agent evolution story driven by Codex + BENE.
