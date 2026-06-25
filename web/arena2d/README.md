---
title: "arena2d — interactive 2D battle viewer + deep-thinking mind readout"
status: active
owner: "@EdwardTang"
created: 2026-06-24
updated: 2026-06-24
type: reference
scope: web/arena2d
layer: ui
---

# arena2d — barebones 2D battle viewer + interactive "mind readout"

A static, `file://`-safe demo: it renders a **real** Pokémon Showdown battle in a
2D view and, per decision, shows an **interactive deep-thinking readout** on a hard
**epistemic boundary** — what the agent *knew* vs what it *thought*.

## The epistemic boundary (the honesty contract)

| Layer | Source | Shown as |
|---|---|---|
| **OPPONENT MODEL** | reconstructed forward-only from the log, **up to that decision** (fog of war — never future moves) | derived game facts |
| **TYPE MATCHUP** | the real Gen-9 type chart vs the *revealed* types | derived, interactive |
| **AGENT** | `RATIONALES[]` — the agent's own `codex_decide` words, streamed verbatim | the agent's real cognition |
| **CONSIDERED** (the fan) | `RATIONALES[].considered[]` — the moves the agent **weighed and rejected**, with its `why_not`, captured by `codex_decide_explain` (PR #610) | the agent's real deliberation — **attested**, not a derived reconstruction |
| **OUTCOME** (PRIMITIVE) | the real `-supereffective`/`-immune`/`faint` log lines | stamped **only after** the move resolves (no hindsight) |

The type matchup *grounds* the agent's claims: when it says "resists Grass" or
"immune to Close Combat", the derived chart confirms it (×0.5 / ×0) — and when the
agent and the chart disagree, the UI shows both, honestly.

## Data contract — `ReasoningTrace` (one schema, two transports)

`data.js` is the `file://`-safe **projection** of a `ReasoningTrace`
(`adx_showdown.reasoning_trace`) — one self-contained document per battle (DDIA document
model: the `log` + ordered `decisions` are read together, no cross-battle joins). It holds
**only source-of-truth, attested fields**: the protocol `log` and, per decision, the chosen
`move` + verbatim `rationale` + the `considered` fan. Type-effectiveness ×scores and
PRIMITIVE labels are **derived on read** by `dex.js` — never stored — so the UI can never
claim the agent computed a score it didn't emit.

The same document is meant to be served live by a REST endpoint shaped like **Pokémon
Showdown's replay API** (`replay.pokemonshowdown.com/<id>.json`): `to_ps_replay()` emits a
flat doc with `id` / `format` / `formatid` / `players` and the raw protocol as one
newline-joined `log` **string**, so stock PS replay tooling reads the base fields
unchanged. The agent's reasoning rides as additive, namespaced extension fields
(`decisions` + `schema`). The static `data.js` is the `file://`-safe projection of the same
document, so the file fixture and the live endpoint share one schema (the viewer `fetch`es
the endpoint and falls back to `data.js`). A finished battle's trace is immutable → the
endpoint is trivially edge-cacheable.

Regenerate the fixture from a capture:

```bash
uv run --package adx-showdown python tools/build_arena2d_data.py \
    /tmp/arena2d_explain_battle.json web/arena2d/data.js
```

## Files

| File | Role |
|---|---|
| `index.html` | layout + styles + 2D stage + decision timeline |
| `data.js` | **generated** `ReasoningTrace` projection: `LOG` (Showdown protocol) + `RATIONALES` (each with the attested `considered` fan; do not hand-edit) |
| `battle.js` | log helpers (pure logic, no authored narration) |
| `dex.js` | **derived** reference: type chart + this battle's species/move typings |
| `mind.js` | the mind-readout panel (opponent model, interactive type lenses, streaming, outcome) |
| `anim.js` | single forward-only pass → 2D replay + zero-leakage opponent snapshots; drives both panes + scrub |

## Interactions

- **Play / Step / Restart / speed** — the 2D replay; the readout streams in sync.
- **Decision timeline** — click any node to scrub the battle + readout to that decision; nodes color by outcome as it plays.
- **Type lenses** — click an attack-type pill to recompute the matchup verdict live.
- **Click a past decision** — inspect its full opponent model + matchup while paused.

## Serving

Static assets only. The live page at `https://agentdex.builders/arena2d/` is served
by **Caddy on the deploy box** (config is box-side, not in this repo). Preview locally:
open `index.html` directly, or `python3 -m http.server` from this directory.

## Known caveats (pre-ship)

- **Sprites** load from `play.pokemonshowdown.com` CDN — **reskin before any public ship** (IP).
- Throwaway-grade prototype, **not** baked into the gateway image.
- `dex.js` covers only **this battle's** cast — a fuller demo needs a real Pokédex.
- Local self-play capture needs the showdown loopback patch
  (`packages/adx_showdown/scripts/patch-showdown-loopback.cjs`, applied via `postinstall`).

## Related

- PR #597 — `feat(codex): give the live-codex policy an opponent model` (the reasoning
  behind the rationales shown here). Still under review.
