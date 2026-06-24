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
| **OUTCOME** (PRIMITIVE) | the real `-supereffective`/`-immune`/`faint` log lines | stamped **only after** the move resolves (no hindsight) |

The type matchup *grounds* the agent's claims: when it says "resists Grass" or
"immune to Close Combat", the derived chart confirms it (×0.5 / ×0) — and when the
agent and the chart disagree, the UI shows both, honestly.

## Files

| File | Role |
|---|---|
| `index.html` | layout + styles + 2D stage + decision timeline |
| `data.js` | **generated** capture: `LOG` (Showdown protocol) + `RATIONALES` (do not hand-edit) |
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
