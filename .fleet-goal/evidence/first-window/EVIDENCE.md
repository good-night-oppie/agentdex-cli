---
title: "First real PokeAgent Challenge battle windows (adx-bot-1, Gen 1 OU)"
status: active
owner: "@EdwardTang"
created: 2026-07-18
updated: 2026-07-19
type: reference
scope: .fleet-goal/evidence/first-window
layer: cross-cutting
cross_cutting: true
---

# First real PokeAgent battle window — scripted candidate vs official baselines

- **When:** 2026-07-18T23:52:58Z
- **Authority:** Eddie in-session ("get to play battle in poke agent challenge against baseline" + gogogogo)
- **Server:** battling.pokeagentchallenge.com (official PokeAgent Challenge), Gen 1 OU
- **Bot account:** adx-bot-1 (creds read inline from ~/.pok-challenge, never echoed)
- **Candidate:** pokeagent-scripted-legal (deterministic max-base-power policy, no LLM, $0 spend)
- **Team:** hand-authored standard Gen 1 OU (Tauros/Snorlax/Chansey/Starmie/Exeggutor/Alakazam), packed + validated via the pokemon-showdown clone

## Result (verified receipt)

| axis | value |
|---|---|
| **quality (FH-BT skill rating)** | **1076.0** |
| wall_clock_sec | 27.2 |
| cost_dollar | 0.01 (declared; cost_is_measured=false — scripted = $0 real) |
| receipt.tier | **verified** |
| receipt.ref | https://battling.pokeagentchallenge.com/ladder#gen1ou/adx-bot-1 |
| ladder_class | live_adversarial (effective: static this window) |

## Setup notes / bugs fixed en route
1. poke-env is an optional extra — `uv sync --package adx-ladders --extra pokeagent`.
2. `~/.pok-challenge` is a 1Password item; password lives at
   `details.sections[0].fields[t=agent-password]` (the recon's top-level `d["fields"]`
   walk was wrong for this shape).
3. `adx` entrypoint is in the agentdex-cli package (`uv run --package agentdex-cli adx measure`),
   not adx-ladders.
4. Packed team format needs 11 pipes per mon (`Name||||moves|||||||`) and `]` between mons —
   generated with `pokemon-showdown pack-team`; a hand-written short-a-pipe version raised
   "too many values to unpack (expected 12)".
5. The team file must have NO trailing newline, else poke-env parses it as a 7th mon and raises
   "invalid literal for int() with base 10: '\n'".

## Ladder-activity gate
Gen1 OU only matchmakes with >=2 organizer baselines online. A read-only one-shot check
(login + userdetails only, no battle search, no rated game) showed 20/22 then 19/22 online =
ACTIVE before firing.

## Second window — LLM-driven candidate (Eddie-authorized live spend)

- **Candidate:** pokeagent-llm-gen1ou — per-move decision by claude-gpt-5.6-sol through the
  loopback TeamClaude gateway (no credentials, no remote base URL); abstain-on-any-fault,
  max-base-power fallback if the model is unreachable.
- **Result:** quality (FH-BT skill rating) **1076.0**, 40.6s, receipt tier=verified.
- **Decisions logged:** 2 LLM moves (earthquake, then switch to starmie) before the battle
  resolved.

### Honest finding — quality axis is the ACCOUNT leaderboard rating, not a per-battle W/L
Both the scripted and LLM windows report quality=1076.0 because the score is adx-bot-1's
FH-BT *leaderboard* skill rating (adapters/pokeagent.py: quality = query_skill_rating result),
not the win/loss of the single game just played. One rated game barely moves a 500+-game
account rating, so a 1-game window cannot discriminate two candidates on quality. To compare
scripted vs LLM meaningfully you need either (a) many games per candidate to move the rating,
or (b) a separate per-window win-rate metric. This is a real measurement-semantics limitation
of the current pokeagent quality axis, not a bug — recorded for the roadmap.
