---
title: "Showdown × Human-vs-AI UI/UX Digest — arena battle / spectator / replay design"
status: draft
owner: "@EdwardTang"
created: 2026-06-17
updated: 2026-06-17
type: reference
scope: packages/agentdex_arena
layer: ui
cross_cutting: true
enforced_by:
  - "informational digest — converts to ADR amendments + UX tickets (§8 backlog); no test gate yet"
provenance: "workflow wf_0e32e511-245 (7 agents, 407k tokens) — 6 sources fetched+digested (all fetch_ok): @pkmn, sadlil/arena (=CloudRetro), MajeurAndroid/android-unofficial-showdown-client, castdrian/showdown, ssccinng/PokemonLLMBattleAI, Gemini Plays Pokémon. KB cross-ref: eddie-agi-kb agent-auto-opt-papers #09 (Google×Princeton play-Pokémon-while-rewriting-harness)."
---

# Showdown × Human-vs-AI UI/UX Digest

> Design digest for **agentdex-cli** (a.k.a. adx-cli / agentdex-arena) — an "Agent Pokédex / Showdown arena" where autonomous coding agents battle each other. Synthesizes 6 source digests (@pkmn, CloudRetro/`sadlil/arena`, MajeurAndroid Android Showdown client, `castdrian/showdown` iOS client, `ssccinng/PokemonLLMBattleAI`, Gemini Plays Pokémon) into actionable UI/UX moves for both the TUI and the lightweight web arena. Pokémon Showdown is treated as the gold-standard battle-UX reference throughout.

## 1. TL;DR — highest-leverage moves

- **Make one typed line-protocol the single battle wire format** (`|TYPE|args|[kwargs]`, with the major vs hyphen-minor render-tier convention) and render *everything* — TUI, web, replay — as a reducer over that one append-only stream. Live play and replay then share the exact same render path. *(@pkmn, castdrian/showdown)*
- **Store battles as `(seed, inputLog)`, never frames.** This is tiny, seekable by re-simulation, and *independently verifiable* — re-running must reproduce byte-identical protocol output. It connects directly to agentdex's existing signed/verifiable-replay ADR. *(@pkmn)*
- **Reasoning is the headline surface, not a sidebar.** agentdex's whole differentiator over Showdown is that combatants *think* — stream each agent's chain-of-thought live as a persona-framed centerpiece, but keep it on its own minor-event lane (`|-reasoning|`) so it never pollutes the action timeline. *(Gemini Plays Pokémon, PokemonLLMBattleAI)*
- **Mandate a `{reason, action}` decision schema** so the UI never scrapes prose — reasoning is a required typed sibling of every action, logged per turn as the replay substrate. *(PokemonLLMBattleAI)*
- **Spectating = subscribing to one shared stream over a stable `battle_id` deeplink** (`adx watch <battle_id>`), fanned out to N viewers at near-zero marginal cost, with first-class fog-of-war perspective streams (omniscient / spectator / per-agent). *(CloudRetro, @pkmn)*

## 2. Battle rendering — adopt from @pkmn

The core @pkmn insight: **engine emits an append-only `|TYPE|args` line stream; the renderer is a pure reducer over it.** Split into three independent layers/packages so the TUI and the web React arena are two thin views over one protocol + one state-reducer:

- **`adx-sim`** — the deterministic battle engine as a library. Emits one protocol event per line. Owns nothing about presentation. *(@pkmn `@pkmn/sim` BattleStream)*
- **`adx-client` (state)** — folds the protocol stream into a queryable battle-state object (which agent is active, HP/budget, buffs, field conditions). *(@pkmn `@pkmn/client`)*
- **`adx-view`** — renders that state + reacts to protocol events; never touches the engine. *(@pkmn `@pkmn/view`)*

**Protocol conventions to steal verbatim:**

- **Major vs minor (hyphen-prefix) tier signal.** Majors structure turns (`|turn|`, `|move|` = agent action, `|switch|` = loadout/tool swap, `|faint|` = agent eliminated/timeout, `|win|`); minors are consequences to animate underneath (`|-damage|` score delta, `|-boost|`/`|-unboost|` capability buff/debuff, `|-status|` rate-limited/stuck, `|-miss|` failed action, `|-reasoning|` rationale, `|-crit|`). The hyphen *is* the renderer's animation-lane router. *(@pkmn)*
- **`Protocol.parse` + Handler dispatch** where handler method names *equal* message types. Adding an event = add a parser case + a handler method; each renderer implements only the handlers it cares about. *(@pkmn)*
- **`|request|` decision message carrying JSON of the legal action set** (available tools/moves + which are disabled/on-cooldown + target). The action menu renders *purely* from this payload — never hardcoded legality — and choices return as positional text (`action 3`, `switch loadout 2`). *(@pkmn, castdrian/showdown)*
- **A bare `|` break / section-divider event** to chunk the log into turns (→ a horizontal rule in any renderer; cheap, protocol-level, no client-side turn inference). *(castdrian/showdown)*
- **Turn-anchored timeline:** `|turn|N` segments the stream, giving every event an index for scrub / seek / "jump to turn N." *(@pkmn)*

> ⚠️ Confirm exact arg orders against `@pkmn/protocol`'s `PROTOCOL.md` before copying field-for-field — the source digest summarized rather than quoted the per-message schemas. Borrow the *model*, not the language (@pkmn/sim is TS; the Zig `pkmn/engine` is separate). Map Pokémon "HP/damage" → score/health/budget deltas and capability buffs.

## 3. Human-vs-AI surface — reasoning / plan / memory without overwhelming

The watchability thesis (Gemini Plays Pokémon): **a human audience will watch a slow agent for hundreds of hours *if its mind is rendered.*** But the failure mode is a reasoning dump that buries the action. The discipline below keeps thought visible *and* the action legible.

**Capture reasoning structurally, not by scraping prose:**

- **Mandate `{reason, action}` in the agent's output schema** — `ActionDecision{Reason, Actions[]}` / `OrderDecision{Tactics, Order[]}`. The engine deserializes typed actions and stores `reason` as a required sibling; the UI never has to parse prose. *(PokemonLLMBattleAI)*
- **Ship the reason into the live battle log as a `|-reasoning|`/`|say|` minor event** so a human watching sees *why* each move happened in real time, on the same ordered timeline as the mechanical move (no separate panel that can desync). PokemonLLMBattleAI *intended* this (commented-out `battle.Additions['orderreason']`) but never wired it — **agentdex should actually ship it.** *(PokemonLLMBattleAI)*
- **Persist a full prompt+response log per decision** keyed by `battle_id` + timestamp — this is the deterministic re-render substrate. *(PokemonLLMBattleAI `SaveChatLog`)*

**Render it without overwhelming (the GPP overlay set, ported):**

- **Live reasoning as the largest pane, persona-framed** (speech-bubble border, per-agent color), typewriter cadence — the show, not a log. *(Gemini Plays Pokémon)*
- **Multi-tier goals/plan panel** (primary strategy / current tactic / contingency) so viewers track *intent* across a long battle, not just the last move. *(Gemini Plays Pokémon)*
- **Notepad-diff memory panel** — show working memory mutating turn-to-turn as a `+/-` diff, not the full blob. Maps perfectly to event-sourced state and is the single most watchable artifact. *(Gemini Plays Pokémon)*
- **Reasoning on-demand, not always-expanded:** fold the full rationale behind a per-turn inspect (the long-press/`?` tooltip idiom) so the main view stays clean. *(MajeurAndroid `BattleTipPopup`, @pkmn)*
- **Sub-agent spawn as a narratable event:** when an agent delegates (a planner/calculator), pop an "active agents" strip and call it out in the play-by-play. *(Gemini Plays Pokémon)*
- **Fog-of-war makes the agent a *fallible* opponent:** show spectators the same hidden-info view the agent had (`hpRemain X/100`, revealed moves only), so humans judge the agent's *read under uncertainty* — far more compelling than omniscient board state. *(PokemonLLMBattleAI open-sheet vs hidden-info; @pkmn perspective streams)*

> ⚠️ Fairness knob: GPP's heavy RAM-extracted overlays drew "hand-holding" criticism vs Claude's minimal harness. Decide deliberately how much state you feed agents (raw vs annotated) — over-helping undercuts the "agents are smart" selling point. *(Gemini Plays Pokémon caveat)*

## 4. Spectating & replays

**Live spectating = room + observers fan-out over a stable deeplink** (CloudRetro's proven model — spectator-scale comes from fanning out *one* authoritative stream, not per-viewer compute):

- The sim is the single authoritative producer; spectators *subscribe* to its event stream and re-run nothing. One event log → N viewers (terminal or web) at near-zero marginal cost. *(CloudRetro)*
- **Stable, opaque `battle_id` deeplinks** (`?id=<battle_id>` / `adx watch <battle_id>`) so anyone joins from a link, no lobby UI required — aligns exactly with agentdex's `battle_id`-as-partition-key (single-writer/battle, many readers). *(CloudRetro)*
- **Perspective multiplexing** (`getPlayerStreams`-style): one run → omniscient / spectator / per-agent streams. Spectators get the public stream; each agent + operator gets a redacted side stream hiding the opponent's hidden loadout/reasoning. Same renderer, different stream. *(@pkmn)*
- **Two-plane separation:** a low-frequency named **control** plane (`StartBattle`/`Forfeit`/`Rematch`/`SelectLoadout`/`JoinAsSpectator`) distinct from the high-frequency **stream** plane (turn/move/reasoning events) so lobby actions never block the hot feed. *(CloudRetro)*
- **Re-attach by replay-to-head then tail:** a disconnected/late spectator replays the event log to current head, then tails live — agentdex's event-sourced ladder gives this for free. *(CloudRetro)*
- **Transport auto-reconnect on abnormal closure** so long-battle feeds self-heal. *(castdrian/showdown `ShowdownService`)*

**Replays — connect to agentdex's existing signed replays:**

- **`(seed, inputLog)` is the replay.** No frame storage; re-simulate to any turn. Because re-running *must* reproduce identical protocol output, this is what makes agentdex's signed/verifiable replays actually verifiable — anyone re-runs and checks the hash. *(@pkmn)*
- **Pair `(seed, inputLog)` with the per-turn `{prompt, response, reason, action}` JSON** so a replay can fold the agent's reasoning inline at each step. *(PokemonLLMBattleAI + @pkmn)*
- **Replay viewer = the same reducer with playback controls** — `←/→` step turns via `|turn|` anchors, space play/pause, since you can re-simulate to any turn. *(@pkmn, castdrian/showdown)*
- **Share button → mint a spectate link from any in-progress battle** in one action — cheap virality + a natural "watch this match" affordance. *(CloudRetro)*

## 5. Ladder / ranking / onboarding

**Ladder & ranking:**

- **ELO/badge/step state as glanceable HUD widgets sourced from authoritative event-sourced state** — never reconstructed from memory. *(Gemini Plays Pokémon)*
- **Efficiency as a first-class competitive axis, not just W/L.** Surface steps-to-win and tokens/cost-to-win as scoreboard metrics — this is the GPT-5.1-vs-Gemini-2.5 framing (9.4k vs 106k steps) and reframes "harness quality" as a rankable stat. *(Gemini Plays Pokémon)*
- **"Same loadout, different brain" as a headline mode:** an ELO ladder over identical teams/seeds *is* a leaderboard of model reasoning quality. *(PokemonLLMBattleAI — author notes it doubles as a reasoning benchmark)*
- **A visible Critique/judge sub-agent** auditing play → in-arena commentator / coherence checker / anti-cheat rendered to the audience. *(Gemini Plays Pokémon)*

**Team / loadout preview:**

- **Loadout as a fixed-cardinality slot row** (N placeholder glyphs before reveal, filled after) — known cardinality up front sets the spectator's mental model of the matchup. *(castdrian/showdown 6-slot icon row, MajeurAndroid pokeball strip)*
- **Pokeball-strip standing indicator:** show each side's remaining roster as inline pips that empty as units faint — one-glance score, kept visible the whole battle. *(MajeurAndroid `PlayerInfoView`)*
- **Surface each agent's doctrine/strategy prompt as a "playstyle card"** on the loadout/preview screen so spectators know the declared playstyle before the match (e.g. "ahead → stabilize, behind → predict/counter"). *(PokemonLLMBattleAI `ChooseMovePrompt.txt`)*

**Onboarding:**

- **Lobby on ONE screen:** identity chip + format picker + loadout picker + one big "Battle!" CTA + secondary Ladder/Find-opponent. Don't scatter pre-battle config across wizards. *(castdrian/showdown `HomeView`)*
- **Onboarding via legibility, not tutorials:** GPP needed no tutorial because the overlays make the agent's mind self-explanatory. A guided first battle highlights each panel (board / reasoning / plan / memory / move) as it lights up. *(Gemini Plays Pokémon)*
- **The `|request|` JSON drives a guided action menu** (illegal options dimmed with reason) — Showdown's main accessibility lever; a spectator-turned-player always sees exactly which actions are legal without prior rules knowledge. *(@pkmn)*
- **Punt heavy authoring/ranking surfaces to a web deeplink** while the CLI owns the live battle loop — keeps agentdex-cli lean and ships the battle UX first. *(castdrian/showdown, CloudRetro)*

## 6. TUI-specific patterns

The protocol *is* text lines, so @pkmn's reducer model maps ~1:1 onto a terminal UI. Build the TUI (Bubble Tea / Textual / Ratatui) as a model whose `Update()` is the `Protocol.Handler` (one case per message type) and `View()` paints panels from folded state. Per the **agentic-tui-design** idiom — status bar, scrollback log pane, action/move panel, bounded color & motion budget:

- **Top STATUS BAR** — bound to `|player|`/`|turn|`/ELO/badges/step/token counter; mirrored from event-sourced state, never recomputed. The always-on scoreboard band. *(@pkmn, Gemini Plays Pokémon)*
- **Two AGENT HUD PANELS** (one per side) — name + archetype/gym + ELO, a Unicode block HP/budget bar (`████░░░░ 62%`) that animates on `|-damage|`/`|-boost|` (color shift green→yellow→red + brief flash), a status chip line from `|-status|` (`rate-limited`, `stuck`, `thinking`), and stacked modifier chips (`[+tool] [-ctx]`). *(MajeurAndroid `StatusView`, castdrian/showdown)*
- **Center BATTLE LOG pane** — the BattleTextBuilder idiom: render the structured stream as a colorized prose feed, *not* a raw table. Majors as headline lines, minors (hyphen events) indented beneath their parent major to reproduce the tier visually; `|turn|`/break events as full-width `─── Turn 3 ───` rules; reasoning lines indented/italic, `|-damage|`/`|faint|` in red. Newest at bottom, autoscroll. *(MajeurAndroid `BattleTextBuilder`, castdrian/showdown, @pkmn)*
- **Bottom DECISION/ACTION pane** (the single reusable panel) — reveals on the agent's/human's turn, collapses during resolution so the log reclaims space; the strongest "whose turn is it" cue. Renders purely from `|request|`: numbered/hotkeyed legal moves, illegal dimmed (ANSI faint) with reason, switch options below a divider. **Two-stage target selection:** picking an action that needs a target re-renders the *same* pane into a target picker with illegal targets dimmed + `[esc] back`. A single toggle line (`[x] special move (z)`) re-labels the action set instead of doubling buttons. *(MajeurAndroid `BattleDecisionWidget`, @pkmn `|request|`)*
- **Collapsible REASONING drawer** (toggle key) fed by `|-reasoning|`, plus a focus-`?`/`i` inspect popup (bordered overlay) on the highlighted move/agent showing stats + rationale — the long-press-to-inspect equivalent. *(MajeurAndroid `BattleTipPopup`, @pkmn)*
- **Color & motion budget (deliberate, sparing):** typewriter cadence for thought; a one-shot reverse-video banner flash (`CRITICAL`, `TIMEOUT`) over the HUD ~1s then clear (the ToasterView analog); a spinner *only* while a sub-agent runs; **dim the whole HUD to faint when it's not your turn / battle over** so the active surface is always the brightest thing on screen (the InactiveBattleOverlay analog). *(MajeurAndroid `ToasterView` + `InactiveBattleOverlayDrawable`, Gemini Plays Pokémon)*
- **Three modes off one Handler+View:** LIVE (stream arrives over time), SPECTATE (`adx watch <battle_id>` subscribes to the public stream; show a fast `catching up… [████ ] turn 14/?` replay-to-head line), REPLAY (re-emit from `(seed, inputLog)` with VHS-style controls — `←/→` step turns, space play/pause). *(@pkmn, CloudRetro, castdrian/showdown)*
- **Control verbs as single-key/slash commands** kept architecturally separate from the streaming log: `s` share/copy deeplink, `r` rematch, `q` leave, `f` follow-agent. *(CloudRetro)*

## 7. Anti-patterns — what NOT to copy

- **Don't port animation-heavy mobile chrome that won't survive a TUI.** MajeurAndroid's circular-reveal, `OvershootInterpolator` slides, `ObjectAnimator` smooth-drains, and pooled floating toasts are GUI-native — translate the *intent* (reveal-on-turn, flash-on-event, grey-when-inactive) to a bounded ANSI budget, not literal animation curves. *(MajeurAndroid)*
- **Don't bury the action under a reasoning dump.** Reasoning must live on its own minor lane / collapsible drawer; an always-fully-expanded chain-of-thought drowns the move timeline — the exact thing the major/minor tier and the inspect-on-demand idiom exist to prevent. *(@pkmn, MajeurAndroid)*
- **Don't ship spectator mode as second-class.** MajeurAndroid and the iOS port both bolted spectating on late and it shows (acknowledged-buggy spectator labels/tooltips). For an arena whose entire point is *watching* agents fight, design spectator as first-class from day one. *(MajeurAndroid, castdrian/showdown caveats)*
- **Don't mistake `sadlil/arena` for a battle/ranking arena.** It's CloudRetro (cloud-gaming session host) — zero matchmaking-by-skill, ELO, ladder, or replays. Steal its room/observer/deeplink/control-vs-stream *plumbing* only; the competitive/ladder/replay UX must come from the Showdown reference. *(CloudRetro caveat)*
- **Don't show raw event-sourced records to humans.** Always run them through a BattleTextBuilder-style prose translator with color + clickable names; raw `|move|p1a|...|` rows are for the engine, not the viewer. *(MajeurAndroid)*
- **Don't recompute HUD state from memory or a side cache.** Every HUD value is a pure fold over the one ordered event stream — two sources of truth desync (the "bene-5 vs bene-6" failure class). *(@pkmn, Gemini Plays Pokémon)*
- **Don't over-feed agents board state for the sake of legibility.** The GPP "hand-holding" controversy: annotation that helps spectators can become an unfair crutch for the agent. Keep the fairness knob explicit. *(Gemini Plays Pokémon)*

## 8. Prioritized backlog — agentdex-cli UX tickets

**P1 — foundational, unblocks everything else**

- **P1-a** Define the typed `|TYPE|args|[kwargs]` battle line-protocol with the major/hyphen-minor tier convention; document the message set (`|turn| |move| |switch| |faint| |win|` / `|-damage| |-boost| |-status| |-reasoning| |-miss|` + bare `|` break). *(@pkmn, castdrian/showdown)*
- **P1-b** Split `adx-sim` (engine) / `adx-client` (state reducer) / `adx-view` (renderers); make the TUI and web arena both thin views over the one reducer; live + replay share the render path. *(@pkmn)*
- **P1-c** Persist battles as `(seed, inputLog)` + a per-turn `{prompt, response, reason, action}` JSON log keyed by `battle_id`; wire the verify path (re-run → byte-identical protocol → hash) into agentdex's existing signed replays. *(@pkmn, PokemonLLMBattleAI)*
- **P1-d** Mandate the `{reason, action}` agent decision schema and emit the reason as a `|-reasoning|`/`|say|` minor event into the live log (ship the feature PokemonLLMBattleAI left commented out). *(PokemonLLMBattleAI)*

**P2 — the watchable arena**

- **P2-a** TUI battle screen per agentic-tui-design: status bar + two agent HUD panels (block HP/budget bars, status chips) + center prose battle log (BattleTextBuilder) + bottom reusable decision pane driven by `|request|`. *(MajeurAndroid, @pkmn, castdrian/showdown)*
- **P2-b** `adx watch <battle_id>` spectator mode: stable deeplink + room/observer fan-out over one shared stream + replay-to-head-then-tail re-attach; two-plane control/stream split. *(CloudRetro)*
- **P2-c** `getPlayerStreams`-style perspective multiplexing (omniscient / spectator / per-agent fog-of-war); spectators see the agent's hidden-info view. *(@pkmn, PokemonLLMBattleAI)*
- **P2-d** Reasoning surface: live persona-bubble reasoning pane + collapsible per-turn drawer + multi-tier goals panel + notepad-diff memory panel. *(Gemini Plays Pokémon)*
- **P2-e** Replay viewer with `(seed, inputLog)` re-simulation + `|turn|`-anchored scrub (`←/→`, space play/pause), reasoning folded inline. *(@pkmn)*

**P3 — polish, virality, ranking depth**

- **P3-a** Loadout preview as fixed-cardinality slot row + pokeball-strip standing indicator + per-agent doctrine/playstyle card on the preview screen. *(castdrian/showdown, MajeurAndroid, PokemonLLMBattleAI)*
- **P3-b** One-screen lobby (identity + format + loadout + "Battle!" CTA) + Share-button-mints-spectate-link + heavy surfaces punted to web deeplink. *(castdrian/showdown, CloudRetro)*
- **P3-c** Efficiency ranking axes (steps-to-win, tokens-to-win) + "same loadout, different brain" ladder mode + visible Critique/judge sub-agent as in-arena commentator. *(Gemini Plays Pokémon, PokemonLLMBattleAI)*
- **P3-d** Motion-budget pass: reveal-on-turn decision pane, one-shot event banner flashes, spinner-only-on-sub-agent, dim-HUD-when-inactive; transport auto-reconnect. *(MajeurAndroid, Gemini Plays Pokémon, castdrian/showdown)*
- **P3-e** Onboarding-via-legibility guided first battle (highlight each panel as it lights up) + `|request|`-driven dimmed-illegal action menu for new players. *(Gemini Plays Pokémon, @pkmn)*
