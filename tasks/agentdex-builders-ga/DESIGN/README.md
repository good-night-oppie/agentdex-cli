# Dashboard design — A-CLI-1 (Claude Design)

`dashboard.html` — single self-contained hi-fi prototype for the agentdex.builders
100-user beta. Open it in a browser; selecting a **live** agent in the roster streams a
simulated battle into the scene (conveying the SSE frames in `../LIVE_VIEWER_CONTRACT.md`).

**Realizes the 5 epics** (`../USER_STORIES.md`):
- Top bar — invite-beta seat (US-1.1), GitHub-login identity (US-1.2/1.3), ladder rank.
- Left roster — *My Agents* with Elo / W/L / strategy badge / live-idle dot (US-2.1).
- **Center (load-bearing layout): Agent Pane ADJACENT to the Live Battle scene** — genome
  (strategy, `tool_policy.allow_switch`, system_prompt, Elo, W/L, Evolve) next to the live
  PS scene (real PS sprites, type-colored HP bars, turn counter, scrolling battle log,
  fog-of-war, LIVE pulse) (US-2.2 + US-3.1).
- Evolution panel — win-rate-over-generations sparkline, kept vs kill-gated marks, the
  +27.5pp / 95% CI uplift, the winning **non-prompt** mutation (US-4.1/4.2).
- Ladder — top-10-PS-player goal line, my agents highlighted, held-out baselines anchoring (US-5.1).

**Anti-slop / authenticity:** real Pokémon Showdown sprite CDN (not hand-drawn SVG),
type-colored HP per PS convention, monospace genome HUD, every number tied to the real
system (Elo from fitness, +27pp from `done_c2_pokeenv.json`, the kill-gate CI, the 3 held-out
baselines). No purple gradient, no emoji-as-icons.

**Hand-off:** this is the design source for **GA-BENE-1** (build + deploy) and **GA-BENE-2**
(wire the live viewer to adx-core's `GET /battle/{id}/live` stream, GA-CORE-3).
