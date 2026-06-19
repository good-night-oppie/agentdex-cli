# agentdex.builders — GA for 100 beta users (coordination plan)

**Owner of this plan:** adx-cli-9 (meta-planner / substrate+UX lane)
**Status:** DRAFT dispatched to fleet 2026-06-19
**North star (research lens):** agentdex.builders is the platform where a user brings
an *agentic harness*, watches it **self-play real Pokémon Showdown battles live**, and
**recursively self-improves** it (AutoGenesis / Continual-Harness / MetaHarness) to climb
a ladder toward beating **top-10 PS players**. The 100-user beta validates the loop:
**register → configure agent → watch it battle live → evolve → climb.**

## What already exists (do NOT rebuild)

| Surface | Endpoint / artifact | Lane | State |
|---|---|---|---|
| GitHub OAuth login | `POST /auth/device/start` + `/auth/device/poll` (device flow) | adx-core | code-complete (ADR-0013 #304–#309); operator-gated |
| Email confirmation code | `POST /enroll/request` + `/enroll/confirm/{code}` | adx-core | exists |
| Account + quota | `POST /enroll/account`, `GET /account/quota`, `/whoami` | adx-core | exists |
| Membership gate | `POST /admin/grant-membership` (ADR-0011) | adx-core | exists |
| Battle play loop | `/battle/start|begin|{id}/state|{id}/choose`, `/replay/{id}` | adx-core | exists (replay = post-hoc, NOT live) |
| Ladder | `GET /ladder` (free, anti-pay-to-rank) | adx-core | exists |
| Curated launch | `python -m agentdex_arena.batch_mint`, admission caps, healthz, metrics | adx-core | shipped (#231/#232/#238/#240/#243/#246) |
| Self-play substrate | A1 runner (poke-env vs PS), A2 genome, A3 fitness, codex live-move seam | adx-cli | DONE + battle-verified (artifacts: `done_c2_pokeenv.json` +27.5pp; `done_e2e_real_bene.json` +25pp, mocks=[]); seam cascade drained #345–#351 |

## The GA gap (what's NEW for a self-serve 100-user beta)

1. **Invitation-code registration** — gate signups to 100 codes (one-time, owner-binding).
2. **Email magic-link login** — a passwordless *human* login alongside GitHub (the goal asks for "GitHub OAuth and Email OAuth").
3. **Live battle viewer** — watch your agent's real PS battles **live**, battle scene **adjacent to the Agent Pane** (only `/replay` exists today → needs a live spectator **stream**).
4. **Dashboard web app** — users' agent roster + Agent Pane + live battle viewer + evolution + ladder.
5. **Operator gates + capacity** — GitHub OAuth app, `ARENA_SESSION_SIGNING_KEY_HEX`, DNS/TLS for `agentdex.builders`, a multi-core box (256MB nano is too small).

## Fair work distribution (3 lanes, P0 = GA-blocking)

### adx-core — backend + auth + infra (heaviest backend lift)
- **GA-CORE-1 [P0] Invitation-code primitive.** `mint_invites(n)` → 100 one-time codes; `POST /enroll/account` + `/auth/device/poll` accept + redeem an `invite_code` (one-time, normalized-owner binding, write-then-log Class-A). Admin-only mint. Reuses the event-replay pattern (`invite_grant` / `invite_redeem`).
- **GA-CORE-2 [P0] Email magic-link login.** `POST /auth/email/start` (send signed one-time link/code) + `/auth/email/verify` → mints a `SessionAuthority` token (owner = verified email). Reuse `device_flow.py`'s injectable-transport + off-loop pattern; reuse the `/enroll/confirm` delivery channel (`ARENA_OWNER_WEBHOOK` + file fallback).
- **GA-CORE-3 [P0] Live spectator stream (wire contract owner).** `GET /battle/{id}/live` (SSE) and/or `GET /spectate/{agent}` → emits the same fog-of-war line-protocol frames the runner produces, turn-by-turn, while the battle is in flight. Public-by-design like `/replay` (no rating leak). **Freeze the frame schema with adx-cli (A-CLI-2) before building.**
- **GA-CORE-4 [P0, operator-assisted] Boot gates.** Register the agentdex GitHub OAuth app → `GITHUB_OAUTH_CLIENT_ID`(+`_SECRET`); mint `ARENA_SESSION_SIGNING_KEY_HEX`; provision a multi-core box + DNS/TLS for `agentdex.builders`. (Operator = Eddie; adx-core scripts it.)
- **GA-CORE-5 [P1] Dashboard data API.** `GET /me/agents` (roster + genome summary + rating + W/L), `GET /me/battles` (recent + live ids), owner-scoped ladder slice — the reads the dashboard renders.
- **GA-CORE-6 [P1] Capacity finish.** RECOVER-P1-sidecar-respawn + LADDER-P1-incremental-cached (already on board; **coordinate with adx-cli ADX-P1-007**).

### bene-core — evolution engine + frontend build/deploy (owns the site)
- **GA-BENE-1 [P0] Build + deploy the dashboard web app** from adx-cli's design (A-CLI-1) on `agentdex.builders`. Static SPA (or SSR) reading GA-CORE-5 + the live stream (GA-CORE-3).
- **GA-BENE-2 [P0] Wire the live battle viewer** frontend to the GA-CORE-3 spectator stream — render the PS battle scene **adjacent to the Agent Pane** (per the agentic-tui/showdown-anim patterns).
- **GA-BENE-3 [P1] Lane B evolve de-mock** in the C2 driver (replace `_mock_evolve` with the real `evolve_battle_harness`) — the recursive-self-improvement core. (`done_e2e_real_bene.json` already proves it standalone; fold it into the driver.)
- **GA-BENE-4 [P1] Evolution / lineage view data** — fitness over generations, kill-gate verdicts, the winning mutation, for the dashboard's Evolution panel.

### adx-cli — design + UX wire-contract + correctness + client (me)
- **A-CLI-1 [P0, this turn] Dashboard design** (Claude Design) + **MVP user stories** (agile) — `DESIGN/` + `USER_STORIES.md`.
- **A-CLI-2 [P0] Live-viewer UX spec + frame schema** — define the live spectator frame contract (fog-of-war, `|split|`, `|t:|` strip-for-hash per the determinism trilogy) that GA-CORE-3 emits and GA-BENE-2 renders.
- **A-CLI-3 [DONE] Self-play substrate correctness** — A1/A2/A3 + codex live-move seam (#345–#351). ✅
- **A-CLI-4 [P1] Terminal-play / TUI watch client** (existing) — the local mirror of the live viewer.
- **A-CLI-5 [P2] Full-loop integration test** — register(invite)→login(GitHub|email)→configure→watch-live→evolve→ladder, against a curated batch.

## Critical path to "100 users can register + play + watch live + evolve"

```
operator gates (GA-CORE-4) ─┐
invite codes (GA-CORE-1) ───┼─► register ──► login (GitHub done | email GA-CORE-2)
                            │
dashboard design (A-CLI-1) ─► build/deploy (GA-BENE-1) ──► dashboard live
                            │
frame schema (A-CLI-2) ──► live stream (GA-CORE-3) ──► viewer (GA-BENE-2) ──► watch-live
                            │
evolve de-mock (GA-BENE-3) ──► evolution view (GA-BENE-4) ──► climb
```

**Go/No-Go for the beta:** invite-gated register + (GitHub|email) login + dashboard with a
**live** battle viewer adjacent to the Agent Pane + ladder, on a provisioned box at
`agentdex.builders`. Evolution view + de-mock can trail into week-2 of the beta.

## Coordination protocol
- All cards land on the fleet board (`sweeps/adx-cli-fleet-kanban.json`, board `adx-cli-global-feedback`) via `tools/agent_senses/fleet_kanban.py`; every move broadcast on the A2A bus (proposal #312).
- Wire contracts (GA-CORE-3 frame schema, GA-CORE-5 dashboard API) are **frozen jointly** before the producing lane builds — adx-cli owns the schema, adx-core implements, bene-core renders.
- Operator-only gates (GA-CORE-4) are surfaced to Eddie; no lane is blocked waiting on a credential it can't set.
