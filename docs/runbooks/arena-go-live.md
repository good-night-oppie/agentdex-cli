---
title: "Arena go-live runbook (deploy / scale / rollback)"
status: active
owner: "@EdwardTang"
created: 2026-06-23
updated: 2026-06-23
type: reference
scope: packages/agentdex_arena
layer: service
cross_cutting: false
---

# Arena go-live runbook (deploy / scale / rollback)

> **Operator-only.** This documents how to deploy, scale, and roll back the
> `agentdex_arena` gateway on the production box. It is NOT an agent-facing
> surface. The canonical env contract lives in
> `packages/agentdex_arena/src/agentdex_arena/__main__.py:build_gateway()`; this
> runbook tracks it.

## 1. Pre-flight env contract

`python -m agentdex_arena` reads all config from the environment at boot. Three
boot postures, by failure mode:

| Env var | Posture if missing | Effect |
|---|---|---|
| `ARENA_ADMIN_TOKEN_HASH` | **fail-closed** — container dies at boot (`AdminAuthError`) | required; admin routes have no degraded mode |
| `ARENA_SIGNING_KEY_HEX` | soft (ephemeral key minted) | **set it** — else every consent token dies on restart/redeploy |
| `ARENA_SESSION_SIGNING_KEY_HEX` | soft (degraded) | `/auth/device/*` + account routes → 503 until set (ADR-0013 D2/D3) |
| `GITHUB_OAUTH_CLIENT_ID` | soft (degraded) | device-flow login → 503 until set (email magic-link still works) |
| `ARENA_BADGE_SIGNING_KEY_HEX` | soft (degraded) | `/badge/mint` → 503; all other routes unaffected (ADR-0011 11c) |
| `ARENA_PUBLIC_BASE_URL` | soft (relative URLs) | prod **must** set it or minted badge README URLs are relative/unverifiable |
| `ARENA_GIT_SHA` | soft (`"unknown"`) | `/healthz .version`; set to the deployed commit SHA so the GA probe can attest the live revision |
| `ARENA_OWNER_WEBHOOK` (+ `_TIMEOUT`) | soft (file inbox) | OOB owner-code delivery; unset → `ARENA_OWNER_INBOX_DIR` file fallback only |
| `ARENA_PG_DSN` (+ `ARENA_PG_APPLY_DDL`) | soft (NDJSON only) | write-behind Postgres event mirror; the hash-chained NDJSON is always source-of-truth |
| `ARENA_RUNTIME_DIR` | default `/tmp/arena-runtime` | persist this on a durable volume for a real deploy |
| `ADX_SIDECAR_POOL_SIZE` | default `1` | sim-tier concurrency — number of node sim processes (see §3) |
| `ARENA_MAX_BATTLES` | default `16` | per-sidecar concurrent-battle cap; total capacity = `POOL_SIZE × ARENA_MAX_BATTLES` (see §3) |
| `ADX_SIDECAR_MAX_OLD_SPACE_MB` | sidecar default | node heap cap per sidecar (see §3) |
| `ARENA_RATE_LIMIT_ENABLED` | default off (inert) | **prerequisite** for ALL rate-limit/lockout controls — they are no-ops unless this is truthy (`1`/`true`/`yes`/`on`) |
| `ARENA_TRUST_PROXIES` | default `0` (no trust) | **only read when `ARENA_RATE_LIMIT_ENABLED` is on**; set `>0` behind Caddy/Koyeb or per-IP lockout keys on the proxy peer = arena-wide login killswitch |

**Pre-flight checklist:** `ARENA_ADMIN_TOKEN_HASH` + `ARENA_SIGNING_KEY_HEX` +
`ARENA_SESSION_SIGNING_KEY_HEX` set and **persistent** (keys on a durable volume,
not regenerated per deploy — else tokens/sessions die on every restart);
`ARENA_PUBLIC_BASE_URL` = the prod hostname; `ARENA_RATE_LIMIT_ENABLED=1` **and**
`ARENA_TRUST_PROXIES=1` behind the edge proxy (the proxy setting is inert without
the enable flag); `ARENA_GIT_SHA` = the commit being deployed.

## 2. Deploy

**Prod (canonical): a `dev`→`main` promotion.** `ga-deploy.yml` triggers on
`push` to `main` → builds the image (tag = commit SHA) → ghcr → HMAC webhook to
the Lightsail box `agentdex-arena-1` (agentdex.builders) → the box pulls,
restarts, and health-gates on `/healthz`. The GA lane works on `dev`, which runs
ahead of `main`, so **merging to `dev` does not deploy** — a promotion PR
(`dev`→`main`) is the deploy trigger.

**Koyeb / AI-Builder path:** `adx deploy --service-name agentdex --branch <b>
--env-vars KEY=VALUE,...`. It auto-forwards every `ARENA_*` and `ADX_SIDECAR_*`
var from the deploy environment, so `export ARENA_GIT_SHA=$(git rev-parse HEAD)`
(and the signing keys) before invoking, then add anything else via `--env-vars`.

## 3. Scale

Battles are share-nothing, partitioned by `battle_id` across a `SidecarPool`.

- **Total concurrent-battle capacity = `ADX_SIDECAR_POOL_SIZE × ARENA_MAX_BATTLES`**
  — both knobs matter. Scaling the pool without raising (or while lowering)
  `ARENA_MAX_BATTLES` does not give the headroom you expect.
- `ADX_SIDECAR_POOL_SIZE=N` → N node sim processes (default 1). Raise for
  concurrency; each member holds ~60–70 MB idle, ~185–198 MB across 3 under load.
- `ARENA_MAX_BATTLES` → per-sidecar concurrent-battle cap (default 16, passed as
  `max_battles_per_sidecar`). Beyond it the pool admission-controls (503 +
  Retry-After) rather than overcommitting a node process.
- `ADX_SIDECAR_MAX_OLD_SPACE_MB` → per-sidecar node heap cap; size it under the
  container memory limit ÷ pool size with headroom.
- A dead pool member self-heals on the `/healthz` touch (`reclaim_dead()` respawns
  it in place + evicts its routes — RECOVER-P1-sidecar-respawn); no background
  reaper, the arena is sleeping-tolerant and all lifecycle runs on touch.

## 4. Observability & thresholds

- `GET /healthz` → `200` ready / `503` when the sim tier is dead (platform should
  recycle the container) or `ARENA_*` boot failed. Carries `version` = the
  deployed commit SHA. Cheap + IPC-free (reads cached returncode) — never hangs.
- `GET /metrics` → `active_battles`, `registered_agents`, `cap_503_total`
  (admission-control rejections — a rising count means raise pool size or cap),
  `sidecar_spawned`, `sidecar_pool_size`, `sidecar_rss_mb` (best-effort, null on
  timeout). Watch `sidecar_rss_mb` against the container limit and `cap_503_total`
  for capacity pressure.
- Cold-wake from a suspended Koyeb slot is ~7 s (the first request pays it).

## 5. Rollback

The image tag IS the commit SHA, so rollback = redeploy the prior good SHA:

1. Identify the last-good commit SHA (the prior `main` tip / image tag).
2. Re-trigger the deploy at that SHA (revert the promotion or redeploy the tag).
3. **Confirm the live revision**: `curl -s https://agentdex.builders/healthz`
   and assert `.version` == the rolled-back SHA (this is why `ARENA_GIT_SHA` is
   wired — the probe attests the live revision, not a branch tip).
4. Verify `/healthz` is `200` and `/metrics.active_battles` recovers.

Because signing keys are env-injected (not baked into the image), a rollback does
**not** rotate keys — tokens/sessions/badges issued before the rollback stay
valid as long as the keys are unchanged on the box.
