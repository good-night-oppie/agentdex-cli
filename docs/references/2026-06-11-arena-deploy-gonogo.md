---
title: "Arena deploy go/no-go — Spaces platform discovery (phase 2)"
status: active
owner: "@EdwardTang"
created: 2026-06-11
updated: 2026-06-11
type: reference
scope: .
layer: cross-cutting
cross_cutting: true
enforced_by:
  - "tests/golden/arena/ lockstep determinism fixtures (phase 3, CI)"
  - "phase-9 deploy criteria (.supergoal-v2/phases/phase-9.md): RSS headroom + cold-start-tolerant enrollment"
  - "gateway memory watchdog + concurrency cap (phase 8/9 tests)"
---

# Arena deploy go/no-go — Spaces platform discovery (2026-06-11)

Phase 2 of supergoal `.supergoal-v2/` (ADR-0010). Gate anchors: IDEAL_EXPERIENCE
§Arena A6 (injection), A7 (economics). All numbers below are MEASURED this run,
not estimated.

## Verdict: GO — single-service layout, with conditions

`agentdex.ai-builders.space` deployed and HEALTHY this run (spike:
health + stateless streamable-HTTP MCP echo, repo
[EdwardTang/agentdex-arena](https://github.com/EdwardTang/agentdex-arena)).

**Conditions on the single-service design (phase 9):**
1. Battle concurrency cap = 1 rated battle at a time initially (+ queue);
   raise only after deployed-RSS headroom is re-measured (phase 9 criterion).
2. Memory watchdog: gateway refuses new battles above an RSS high-water mark
   (fail-closed, consistent with A7 circuit-breaker posture).
3. Sidecar spawned with minimal env (no secrets in its address space).

**Named fallbacks, in order:**
1. **2-service split** (`agentdex` gateway + `agentdex-sim`) — REQUIRES the
   meta-vex slot: quota is 2 services/user and meta-vex holds one. Deleting a
   service is **instructor-action only** (no self-serve DELETE — deployment
   guide §Service management). User green-lit takedown 2026-06-11; escalation
   = message the instructors. Until then quota stands 2/2 (meta-vex + agentdex).
3. **External sim host** (~$5/mo VPS) — last resort; keeps the gateway on-platform.

## Platform contract (from deployment-prompt.md + openapi.json, hub-cached)

- API base `https://space.ai-builders.com/backend/v1` (note: **singular** `space`;
  `spaces.` does not resolve). OpenAPI spec:
  `https://www.ai-builders.com/resources/students-backend/openapi.json` —
  hub-cached at `/tmp/agentdex/coach/openapi.json` per ADR-0004 (fetch once,
  read slices). 15 paths; relevant: `POST/GET /v1/deployments`,
  `GET /v1/deployments/{name}`, `GET /v1/deployments/{name}/logs`,
  `POST /v1/chat/completions`, `GET /v1/models`, `GET /v1/usage/summary`.
- Deploy = `POST /v1/deployments {repo_url, service_name, branch, env_vars?,
  streaming_log_timeout_seconds?}` → 202 + blocking streaming-log window
  (default 60 s) → Koyeb build → HEALTHY in ~3.5 min (measured this run).
- **Public GitHub repos only** (clone-based); Dockerfile at root; single
  process / single port honoring `$PORT` (shell-form CMD); **256 MB RAM nano**;
  ≤20 env_vars; `AI_BUILDER_TOKEN` auto-injected (== the platform API key;
  verified present in the deployed container).
- Service name = subdomain. Hosting free 1 yr from first deploy
  (`agentdex` expires 2027-06-11).
- Platform LLM proxy models (GET /v1/models, verified): deepseek-v4-flash,
  deepseek-v4-pro, gpt-5, grok-4-fast, kimi-k2.5, gemini-2.5-pro,
  gemini-3-flash-preview, … → **flash tier exists**; ADR-0010 §Cost-table
  pricing assumption holds. `/v1/usage/summary` enables the A7 budget readback.

## Measurements

| Probe | Result |
|---|---|
| Spaces token (1P `spaces.ai-builders.com-api-key`) | valid — GET /v1/deployments HTTP 200 |
| Quota | limit 2; was 1/2 (meta-vex HEALTHY since 2026-05-22); now **2/2** (+agentdex) |
| Deploy 202 → koyeb HEALTHY | ≈ 3.5 min (202 at 21:13:03Z; HEALTHY by 21:16:4xZ) |
| Public health GET (warm) | 200 in **0.37 s** |
| Stateless MCP round-trip (initialize / tools-list / tools-call, warm) | **0.31 / 0.31 / 0.26 s** — ~400× headroom vs the 120 s turn budget |
| Cold start (Koyeb SLEEPING wake) | **7.15 s** end-to-end (HTTP 200, `uptime_s=0.281` proves zero-scale wake; sampled after <15 min idle) — fits the 120 s turn budget with ~17× headroom; enrollment flow must still tolerate it (phase 9 criterion) |
| Idle-to-SLEEPING window | < 15 min (service slept between 21:16 warm probes and 21:35 probe) — keep-alive pings required during battles-in-progress (phase 9) |
| SSE / WebSocket | untested, **informational only** — design needs neither (stateless streamable-HTTP throughout) |
| Sidecar RSS (node 24, pokemon-showdown **0.11.10** pinned): idle / 1 battle / 3 concurrent | **55.2 / 178.1 / 185.5 MB** — one process multiplexes at +~7 MB/battle; confirms mastermind F1 numbers; stock server (599 MB multi-process) stays deleted from design |
| Memory budget vs 256 MB | sidecar ~178 + FastAPI gateway ~60–80 ⇒ ~240–260 MB = borderline → conditions 1–2 above; split fallback documented |

## Determinism finding (feeds phase 3 golden fixtures)

Same battle seed ⇒ identical generated teams and (observed) winner, but
**different turn counts** across runs when two free-running async
`RandomPlayerAI` players race on mid-turn requests (choice arrival order
shifts PRNG draw sequencing). Consequence for `packages/adx_showdown`:

- Golden "same seed → same outcome" fixtures MUST drive choices in
  **lockstep** (request → choice → request), which is also the natural
  gateway-mediated shape (`get_battle_state`/`choose_action` per request).
- A2 re-simulation rides the recorded **inputLog** (all choices recorded) —
  deterministic regardless of player PRNG; the re-sim parity fixture is
  unaffected.
- PRNG facts (0.11.10): seeds are `sodium,<hex>` strings; 4-number arrays
  still accepted (Gen5 path); `RandomPlayerAI(stream, {seed})` seeds the
  player; battle seed goes in the `>start` options JSON.

## Durable store decision (A8)

**Supabase** — `https://mcp.supabase.com/mcp?project_ref=yaejfeeghqyzbbdrryti`
already configured in the attic `.mcp.json` (project exists). events.jsonl
syncs per-battle via the Supabase REST API from the gateway (plain HTTPS,
SLEEPING-tolerant); ratings recompute from the table byte-identically
(phase 5 criterion). Fallback: any S3-compatible append target.

## Security posture changes landed this phase

- PR #33 — dashboard `/route` opaque error ids (kills `repr(e)` leak) +
  dashboard import-rot fix. MERGED.
- PR #34 — `oracle/soft.py` nonce-delimited untrusted region + system-prompt
  convention + 5 structural tests incl. canonical injection fixture. (merge
  pending CI at doc time)

## meta-vex disposition

User green-lit takedown (2026-06-11). No self-serve DELETE exists →
**escalation recorded: ask the ai-builders instructors to delete `meta-vex`**
(frees the slot for the 2-service fallback if phase 9 needs it). Not blocking:
single-service GO path needs no second slot.
