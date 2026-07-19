---
title: "PokeAgent Challenge ladder-diligence gate (M1)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
---

actual_route: coordinator_inline_exception

# PokeAgent Challenge — ladder diligence gate (user-specified, 2026-07-11)

## What was learned

User's bar before wiring pokeagentchallenge.com in as a live-adversarial
ladder — "the same bar that just retired HF": (a) currently ACTIVE, (b)
persistent queryable ranking, (c) programmatic submission/adapter path.

**Verdict: PASS on all three.**

- **(a) ACTIVE:** "began as a NeurIPS 2025 competition" and is now "an ongoing
  benchmark with a live leaderboard" (pokeagentchallenge.com landing). Run by
  researchers from Princeton, UT Austin, NYU, JHU, Google DeepMind, CMU.
- **(b) Persistent queryable ranking:** ladder at
  `battling.pokeagentchallenge.com/ladder` (JS-rendered Pokémon-Showdown-style
  client; plain fetch shows the SPA shell) + replays at
  `replays.pokeagentchallenge.com`; Track 1 "results published on a public
  leaderboard updated in real time" with PS matchmaking/rating (Phase 1 open
  ladder; Phase 2 bracket).
- **(c) Programmatic path:** teams create named AI agents, "each agent gets
  credentials your bot uses to connect and battle"; "participants run agents
  locally and communicate action decisions to the server using the Pokémon
  Showdown API"; poke-env is the organizer-recommended Python client.

Two tracks: competitive battling (Track 1) and RPG speedrunning (Track 2 —
Pokémon Emerald/Red long-context). Paper: arXiv:2603.15563.

**Synergy:** agentdex ADR-0014 already validated poke-env + a self-hosted
Pokémon Showdown server as the battle substrate — the PokeAgent run-adapter
reuses that stack nearly verbatim (swap server URL + credential config).

## What changed

None — read-only diligence. Taxonomy directive recorded in GOALS.md.

## Supporting evidence

- https://pokeagentchallenge.com (landing: ongoing benchmark, live leaderboard, tracks, orgs)
- https://pokeagent.github.io/track1.html (Track 1 mechanics: team accounts, agent credentials, ladder, phases)
- https://pokeagentchallenge.com/battling.html (battling guide)
- https://arxiv.org/abs/2603.15563 (The PokeAgent Challenge: Competitive and Long-Context Learning at Scale)
- https://poke-env.readthedocs.io/en/stable/examples/connecting_to_showdown_and_challenging_humans.html
- battling.pokeagentchallenge.com/ladder fetch: SPA shell ("Initializing...") — ranking is client-rendered; adapter should read rating via the Showdown protocol/API rather than scraping.

## Authenticated verification (2026-07-11, Playwright login with user credentials)

Automated Playwright login (headed-on-Xvfb, kit conventions, credentials read
in-process from `~/.pok-challenge` — values never logged) as `adx-oppie-1`
verified from INSIDE:

- **Login works** end-to-end (name → password → userbar shows `adx-oppie-1`);
  PS auth is per-connection (no cookies persisted; browser sessions re-login,
  bots authenticate per WebSocket connection — normal Showdown behavior).
- **Team already provisioned:** team **AgentDex** (member `adx-oppie-1`,
  registered 2026-06-25) with bot agent **`adx-bot-1`** (registered
  2026-06-26). "Your bot will log in with this name and your team's agent
  password" — the concealed `agent-password` field in the credential item.
  Team Description + Code-link fields exist (unset) for project attribution.
- **Live leaderboard verified:** Gen 1 OU active with 22 baselines online
  (Metamon team tops at 1813±14; PokéAgent MM-*/BH-* baselines span 850-1697);
  Gen 9 OU Long-Timer active with 3 baselines; other formats offline. Glicko-
  style `rating±deviation`, W/L, battle counts, 500-game minimum for a Skill
  Rating, top-20 head-to-head win-rate matrix, "last updated 4m ago", plus a
  continuously-updating "Showdown Metrics" toggle. Screenshots:
  `/tmp/pokeagent_recon_{myteam,leaderboard_index,leaderboard_gen1ou}.png`;
  scripts: `harness-engineering/scripts/browser/{login,recon}_pokeagent.mjs`.

## What should happen next

Wire PokeAgent Challenge into the ladder taxonomy as the third
live-adversarial lane (Kaggle, ARC-AGI-3, PokeAgent). The run-adapter derives
from the ADR-0014 poke-env substrate and connects as `adx-bot-1` with the
team agent password; rating ingestion should read the ladder room / Showdown
protocol rather than scraping the SPA shell. Active-format targeting: Gen 1 OU
(primary, 22 baselines) and Gen 9 OU Long Timer (secondary).
