# Live battle viewer — frame contract (A-CLI-2)

The wire contract for **US-3.1** (watch an agent battle live, scene adjacent to the
Agent Pane). adx-cli owns this schema; **adx-core (GA-CORE-3)** emits it, **bene-core
(GA-BENE-2)** renders it. Built on the existing line-protocol (`packages/adx_showdown`
`lineproto.py`, PR #200) + the determinism trilogy — reuse, don't reinvent.

## Transport
- `GET /battle/{battle_id}/live` — **SSE** (`text/event-stream`), one event per frame.
- Public-by-design (like `/replay`): **no consent token, no rating in the payload** — a
  live view must never leak a membership-derived rating (the §Q5 / anti-pay-to-rank rail).
- Backpressure: if a client connects mid-battle, the server first replays the buffered
  frames `[0..now]` (so the scene is consistent), then streams live.
- Ends with a terminal `event: end` carrying the `/replay/{id}` url.

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

## Fog-of-war (load-bearing — the determinism trilogy)
- The server emits **per-side** frames: a `side="p1"` stream redacts p2's hidden info
  (`|split|p1` lines) exactly as PS does. The Builder watching **their** agent gets their
  side's view; a generic `spectator` stream gets the public projection only.
- `|t:|` timestamp lines are **stripped before any hash** (replay/live must hash-match).
- The scene's `hp_frac` is the **public** HP fraction (never exact HP of the opponent).

## Renderer requirements (GA-BENE-2)
- The battle scene mounts **adjacent to the Agent Pane** (side-by-side at ≥1024px; stacked
  below on mobile). Selecting a live agent in the roster opens its stream in the scene.
- ≤2s end-to-end lag (AC3); render incrementally per `seq` (never wait for battle end).
- On `event: end`, swap to the replay control bound to the same scene component (US-3.2),
  so live + replay share one renderer.

## Open items to freeze with adx-core before GA-CORE-3 build
1. SSE vs WebSocket (SSE preferred — one-way, proxy-friendly, auto-reconnect).
2. Buffer retention window per battle (default: full battle, dropped on replay-commit).
3. Auth for the **owner's own-side** stream (session token) vs the public spectator stream (none).
