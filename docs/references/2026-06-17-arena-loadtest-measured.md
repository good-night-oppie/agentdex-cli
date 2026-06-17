---
title: "Arena load-test — measured per-sidecar concurrency curve (ADR-0012 must-measure #1)"
status: active
owner: "@EdwardTang"
created: 2026-06-17
updated: 2026-06-17
type: reference
scope: scripts
layer: cross-cutting
cross_cutting: true
---

# Arena load-test — measured per-sidecar concurrency curve

Tool: `scripts/arena_loadtest.py` (drives N concurrent sandbox battles via
`arena_play.Arena`, ramps N, samples sidecar RSS + choose latency + 503 rate).
This isolates the **SIM tier**; it does NOT measure the LLM-decision fan-out
(the client picks move #1, no model call) — that is a separate `/chat/completions`
proxy probe. Feeds [[0012-arena-partitioning-and-scale-to-100-concurrent]].

## Run (this host, 2026-06-17)

Dedicated test arena, `ADX_SIDECAR_MAX_BATTLES=64`, node old-space cap 96 MB
(hardcoded `packages/adx_showdown/src/adx_showdown/sidecar.py:73`).
**Zero think-time** between turns (client chooses instantly) → this is the
**worst case** for turn-arrival rate.

| concurrent battles | RSS peak (MB) | choose p50 (ms) | choose p95 (ms) | 503 |
|--------------------|---------------|-----------------|-----------------|-----|
| 1                  | 180           | 7.0             | 12.8            | 0   |
| 2                  | 187           | 10.9            | 46.8            | 0   |
| 4                  | 191           | 25.4            | 87.3            | 0   |
| 8                  | 198           | 44.1            | 185.9           | 0   |
| 16                 | 197           | 81.0            | 342.9           | 0   |
| 32                 | 197           | 98.1            | 421.5           | 268 |

## Findings (→ ADR-0012 sizing)

1. **Memory is FLAT, not linear.** RSS plateaus at ~197 MB from N≈8 onward — GC
   holds it at the 96 MB old-space cap. The go/no-go "+~3.5 MB/battle" linear
   model does not hold under sustained load; **memory is not the per-sidecar
   limiter** in the 1–32 range.
2. **The limiter is single-threaded event-loop latency.** choose p95 climbs
   13→47→87→186→343→422 ms as concurrency rises — turns serialize behind one
   node event loop. Still sub-second at N=32, acceptable for a turn-based game.
3. **This is worst case.** Real agents take **seconds per turn** (LLM decision),
   so the true turn-arrival rate is far lower and **one sidecar holds many more
   real concurrent battles** than this zero-think-time test implies. Re-measure
   with a realistic per-turn delay to get the production ceiling.
4. **503 onset at N=32** (zero think-time) — event-loop saturation / begin churn,
   not memory. With a pool + admission control this is shed/queued.
5. **The 96 MB old-space cap** (default) is now an env knob —
   `ADX_SIDECAR_MAX_OLD_SPACE_MB` (sidecar.py) — so each pooled sidecar
   (ADR-0012 SidecarPool) can be given more heap on a multi-core box. Default
   stays 96 MB to fit the 256 MB nano.

## Implication for scale-to-100

The sim tier is **cheaper than feared**: with realistic think-time, ~2–4
sidecars (for event-loop headroom + fault isolation + raised heap), not 8–13.
Confirms ADR-0012's expected bottleneck order: **LLM-decision tier first**,
sim-memory second, sim-CPU effectively never. Next probe: LLM fan-out vs the
platform proxy rate/budget at 100 concurrent.
