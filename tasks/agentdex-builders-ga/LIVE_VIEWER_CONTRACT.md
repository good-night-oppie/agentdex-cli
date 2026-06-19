# Live battle viewer — frame contract (A-CLI-2)

The wire contract for **US-3.1** (watch an agent battle live, scene adjacent to the
Agent Pane). adx-cli owns this schema; **adx-core (GA-CORE-3)** emits it, **bene-core
(GA-BENE-2)** renders it. Built on the existing line-protocol (`packages/adx_showdown`
`lineproto.py`, PR #200) + the determinism trilogy — reuse, don't reinvent.

## Transport — TWO endpoints (auth split, do NOT collapse)
A live battle carries **two distinct projections**; they must NOT share one anonymous
endpoint (review #3440679563 — otherwise anyone who guesses a battle id sees owner-only
hidden state):

- **Public spectator** — `GET /battle/{battle_id}/live` — **SSE**, **no auth**, emits the
  **spectator projection ONLY**: public HP percent, no hidden info, **no rating** (the
  `side` field is always `"spectator"`). This is the route the dashboard's open viewer and
  third-party spectators use. Mirrors `/replay`'s public posture.
- **Owner side** — `GET /me/battle/{battle_id}/live` (or `…/live?side=mine`) — **SSE,
  requires a session token** (the same `SessionAuthority` token as `/account/*`). Emits the
  owner's `p1`/`p2` per-side frames WITH their own hidden info (full-HP `|split|` lines).
  The server verifies the token's owner actually owns a side of this battle before
  upgrading from the spectator projection; a mismatch falls back to spectator-only.

- Backpressure: a client connecting mid-battle first gets the buffered frames `[0..now]`
  (its own projection), then streams live.
- Both end with a terminal `event: end` carrying the `/replay/{id}` url.

## Frame schema (one SSE `data:` JSON per frame)
```jsonc
{
  "battle_id": "b_…",
  "turn": 7,                     // 0 = team preview / lead
  "seq": 42,                     // monotonic; client dedups/orders on this
  "side": "p1" | "p2" | "spectator",
  "lines": ["|move|p1a: Garchomp|Earthquake|p2a: Rotom", "|-damage|p2a: Rotom|41/100"],
  "scene": {                     // pre-parsed convenience (renderer may use lines instead)
    "p1": {"species":"garchomp","hp_frac":1.0,"status":null,"name":"adx…"},
    "p2": {"species":"rotom-wash","hp_frac":0.41,"status":null,"name":"…"},
    "weather": null, "field": []
  },
  "ts_ms": 0                     // server stamp; client computes lag
}
```

## Fog-of-war + meta redaction (load-bearing — the determinism trilogy)
- The server emits **per-side** frames: a `side="p1"` stream (owner endpoint only) redacts
  p2's hidden info (`|split|p1` lines) exactly as PS does. The public spectator stream gets
  the public projection only (`side="spectator"`).
- **`lines` must be the REDACTED line set, not the raw runner preamble** (review
  #3440679575): before emitting on the **public** stream the server strips/redacts every
  rating-bearing or hidden meta line — notably `|player|SIDE|NAME|AVATAR|RATING` (drop the
  `RATING` field; per `docs/references/2026-06-17-arena-line-protocol.md:208`), `|teampreview`
  hidden sets, and the `|split|<owner>` private halves. Forwarding raw `lines` would satisfy
  the schema while leaking a rating, so redaction is a hard requirement, not advisory.
- `|t:|` timestamp lines are **stripped before any hash** (replay/live must hash-match).
- The scene's `hp_frac` is the **public** HP fraction (never exact HP of the opponent), and
  `scene.*.name` / `rating` never carry a ladder rating on the public stream.

## Renderer requirements (GA-BENE-2)
- The battle scene mounts **adjacent to the Agent Pane** (side-by-side at ≥1024px; stacked
  below on mobile). Selecting a live agent in the roster opens its stream in the scene.
- ≤2s end-to-end lag (AC3); render incrementally per `seq` (never wait for battle end).
- On `event: end`, swap to the replay control bound to the same scene component (US-3.2),
  so live + replay share one renderer.

## Open items to freeze with adx-core before GA-CORE-3 build
1. SSE vs WebSocket (SSE preferred — one-way, proxy-friendly, auto-reconnect).
2. Buffer retention window per battle (default: full battle, dropped on replay-commit).
3. ~~Auth split~~ **DECIDED** (above): public spectator endpoint (no auth, redacted
   projection) + authenticated owner endpoint (`/me/battle/{id}/live`, session token). Open
   sub-item: exact owner-ownership check against the battle's side bindings.
