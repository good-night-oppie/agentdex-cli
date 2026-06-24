---
title: "arena2d — barebones 2D battle viewer + agent mind readout"
status: active
owner: "@EdwardTang"
created: 2026-06-24
updated: 2026-06-24
type: reference
scope: web/arena2d
layer: ui
---

# arena2d — barebones 2D battle viewer + agent "mind readout"

A static, `file://`-safe proof-of-loop: it renders a **real** Pokémon Showdown
battle log in a 2D view and narrates the agent's play turn-by-turn, pairing each
of our coarse PRIMITIVE labels with the agent's **own** per-decision words.

## What's honest here

- `data.js` is **generated from a real live-codex battle** (`battle2`: the
  opponent-aware policy from PR #597, p1 WON). `LOG` is the raw Showdown server
  log; `RATIONALES` are the agent's actual `codex_decide` outputs, in order.
- `anim.js` greedily matches each rationale to the move that produced it, so a
  shown rationale is always the agent's real word for **that** action.
- The PRIMITIVE chips (setup/punish/pivot/…) are **our** coarse classifier and
  can be imprecise — the agent's real words carry the truth. The footer says so.

## Files

| File | Role |
|---|---|
| `index.html` | shell + styles + 2D stage |
| `battle.js` | log/rationale helpers (pure logic, no authored narration) |
| `anim.js` | one pass over the log → animation + per-decision mind-readout |
| `data.js` | **generated** capture (do not hand-edit; regenerate from a live battle) |

## Serving

Static assets only. The live page at `https://agentdex.builders/arena2d/` is
served by **Caddy on the deploy box** (config is box-side, not in this repo).
To preview locally: open `index.html` directly, or `python3 -m http.server`
from this directory.

## Known caveats (pre-ship)

- **Sprites** load from `play.pokemonshowdown.com` CDN (same engine as the
  arena). **Reskin before any public ship** — IP.
- This is a throwaway-grade prototype, **not** baked into the gateway image.
- The local self-play capture path needs the showdown loopback patch
  (`packages/adx_showdown/scripts/patch-showdown-loopback.cjs`, applied via
  `postinstall`) so poke-env login works on a dev host. See that script's header.

## Related

- PR #597 — `feat(codex): give the live-codex policy an opponent model` (the
  reasoning behind the rationales shown here). Still under review.
