---
title: "Genome-HUD Re-homing to Team Identity Spec"
status: active
owner: "@EdwardTang"
created: 2026-06-19
updated: 2026-06-19
type: reference
scope: docs/superpowers
layer: cross-cutting
cross_cutting: true
---

# GA-CORE-5 Genome-HUD Re-homing to Team Identity Spec


## Background
The original GA-CORE-5 card anchored on tracking a "rated-ladder genome" (LLM agent genome) that does not actually exist on the rated play wire (`BeginRequest → battle_begin`). Rated play carries a visitor's `team` payload, while genomes only exist in the selfplay/eval lanes.
To resolve this blocker (Gate 0 identity decision), we pivot the HUD to track the visitor's `team` (the packed Pokémon team payload) as the build identity.

## Design Details

### 1. Gate 0 Identity Decision
* Re-home the HUD from "genome" to "team/build identity". 
* The API returns both `team_summary`/`team_hash`/`team_packed` and `genome_summary`/`genome_hash`/`genome_packed` (pointing to the same team data) to preserve backward compatibility for old clients and tests.

### 2. Event Log Roster Projection (`me_agents`)
* The roster dashboard (`GET /me/agents`) folds the global event log (`events.jsonl`) sequentially by chain `seq`.
* For each agent:
  - Finds the latest `team_hash` from completed, non-quarantined rated battles.
  - Determines if the agent has a `mixed_window` (either multiple unique `team_hash` values used in rated battles or any uncaptured/missing teams).

### 3. Detail View (`me_agent_team`)
* Serves `/me/agents/{agent_name}/team` (and `/me/agents/{agent_name}/genome` as an alias).
* Finds the latest eligible rated `team_hash`.
* Quarantined battles are excluded from the latest eligible rated calculations. If a battle is quarantined, its `team_hash` is disregarded and we fall back to the previous rated battle's `team_hash` (or `None`).
* Since the event log carries no battle timestamp, ordering is purely `seq`-based. We drop the `last rated <date>` field from the detail view.
* If the agent's most recent battle was in a non-rated lane, we populate `recent_non_rated_note` with `"Most recent play was in {lane} lane"`.

### 4. Out-of-band Storage
* To preserve owner prompt IP, the full team string is stored out-of-band in the gateway's `artifacts_dir / "teams" / {owner_dir} / {team_hash}.json`.
* Only the 8-character `team_hash` is appended to the event log (`battle_begin`).
* If out-of-band capture fails, the battle starts successfully (Gate-2: fail-closed admission but best-effort identity capture), writing `team_hash = null` to the event log.
