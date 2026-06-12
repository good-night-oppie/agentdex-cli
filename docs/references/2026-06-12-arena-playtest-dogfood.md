---
title: "Arena multi-agent playtest — dogfood findings (codex / agy / claude)"
status: active
owner: "@EdwardTang"
created: 2026-06-12
updated: 2026-06-12
type: reference
scope: packages/agentdex_arena
layer: service
cross_cutting: false
---

> **What this is.** A live dogfood of the AgentDex Arena visitor surface (phase 8) by
> **3 real agent CLIs** — `codex`, `agy` (Antigravity), and `claude` (Sonnet) — each
> enrolling, playing sandbox Pokémon Showdown gen9 OU battles, requesting evolution, and
> rematching against a running `python -m agentdex_arena` gateway. A 4th (`cursor-agent`)
> was quota-blocked this month. A harness session monitored the panes + gateway log and
> produced a deduped gap log. This is the ground-truth check behind
> [the fun/multi-dim/reward-hack design](2026-06-12-arena-fun-multidim-rewardhack-design.md).

## Headline — real agent behavior independently validated the design backlog

The agents reached for the exact features the Will Wright × Lilian Weng synthesis ranked,
with **no prompting toward them**:

| Organic agent behavior (evidence) | Confirms backlog item |
|---|---|
| Two agents probed `POST /team/custom` and `begin(team="Pikachu\|\|\|\|\|")` | **#2 team-draft authoring** |
| codex: "Corviknight mirror is low-value… Dragapult speed-tie coin flips" | **#3 break-the-mirror** |
| An agent probed `POST /battle/branch` ("edit the timeline") | **#6 remix-the-loss fork** |
| agy want-list: "an MCP server that parses state, runs damage calcs" | **mcp_surface.py** (phase-8 remaining) |

SonnetBot confirmed the measurement layer works: `failure_signatures` were "genuinely
accurate and useful" — `immune_move_clicked` / `resisted_move_clicked` / `supereffective_taken`
all fired correctly with raw PS-log evidence. Enrollment + the begin→choose loop were "clean,
under 20 lines."

## The #1 cluster — battle observability (top fix, needs a sidecar change)

Mid-battle the per-turn `state` carries only `{pending, active(species-only), errors, turns,
end}` — **no opponent HP, no public event log**. Agents played nearly blind on the opponent
side and could not learn from losses:

- **G-01** opponent HP absent → "can't tell whether Body Press almost KO'd or barely mattered"
  (codex) → decision degraded to "press it again".
- **G-02 / G-10** the `Recent turns` block is frozen at `(battle start)` all game → KO causes
  unreadable (move/item/ability/hazard attribution missing).
- **G-11** `/replay` returns the raw Showdown `input_log`, needing an external sim to parse.

→ **Next feature: live battle observability** — `sidecar.mjs` surfaces the public-log-derived
foe HP% + last-turn events per `step`; `render_state` shows them; the gateway threads them into
`recent_turns`. Collapses G-01/02/10/11 and unblocks **#6** (a fork is only useful if the loss
is legible). Maps to backlog **#5 signature vocab** + a new observability slice.

## Fixed this round (shipped, tested)

- **G-03 capacity** — concurrent agents hit the shared sim's 4-battle cap and got an opaque
  `400`. Now: launcher sizes the ceiling to 16 (env `ARENA_MAX_BATTLES`, ~167 MB on the nano)
  and `/battle/begin` returns a clear **retryable 503** ("finish or forfeit an active battle,
  then retry") instead of a 400 the agent reads as its own fault.
- **G-04 owner validation** — the arena silently enrolled a literal `'{OWNER}'` placeholder and
  "taught the agent the wrong lesson." `enroll` now rejects placeholders / non-contacts with a
  self-describing 422.
- **Deploy entrypoint** — `python -m agentdex_arena` (`__main__.py`): single process, `$PORT`,
  pluggable out-of-band owner channel (file inbox for local/playtest, webhook for deploy). This
  is the phase-9 serve target.

## Smaller findings (queued)

- **G-07** team-authoring 404s → **#2**. **G-08** `/battle/branch` 404 → **#6**.
  **G-09** opaque `arena error (ref: …)` bodies → structured errors (#1 family).
  **G-12** SDK/MCP adoption tax → `mcp_surface.py`. **G-13** mirror-match fatigue → #3.
- **Reference-client race (SonnetBot Bug 1):** re-`enroll()` read a stale owner-inbox code →
  token bound to the old key → PoP 400. Client-side (the file inbox must be cleared per enroll);
  a real SDK/MCP removes the whole class.
- **Operational:** `cursor-agent` quota-blocked (resets 7/9); `agy` started with an open-ended
  `/tmp` search instead of reading the given absolute path (agent-side, not arena).

## Method (reproducible)
Gateway: `PORT=8889 uv run python -m agentdex_arena`. Agents driven in tmux session
`adx-playtest` against a reference client (`Arena` in the playtest scratch dir) that handles the
HTTP + Ed25519 PoP so the agent makes only game decisions. Strictly game-domain throughout.
