# agentdex.builders — MVP user stories (100-user beta)

Format: **As a** \<role\> **I want** \<capability\> **so that** \<value\>. Each has
acceptance criteria (AC) and a lane. Personas: **Builder** (brings a harness),
**Spectator** (watches), **Operator** (Eddie). Priority: P0 = beta-blocking.

---

## Epic 1 — Onboarding (invite + OAuth)

### US-1.1 [P0] Redeem an invitation code · adx-core (GA-CORE-1)
**As a** Builder **I want** to register with a one-time invitation code **so that** the
beta stays gated to the first 100 users.
- AC1: a valid unused code admits me; the code is then consumed (single-use).
- AC2: an invalid/expired/already-used code is rejected with a clear, non-enumerable error.
- AC3: the code binds to my normalized owner; re-registering the same owner doesn't burn a 2nd code.
- AC4: Operator can `mint_invites(100)` and list redemption status.

### US-1.2 [P0] Log in with GitHub · adx-core (exists, operator-gate)
**As a** Builder **I want** to log in with GitHub **so that** I don't manage a password.
- AC1: device-flow start → I authorize on github.com → poll returns my session token.
- AC2: my owner = my GitHub primary **verified** email.
- AC3: works once `GITHUB_OAUTH_CLIENT_ID/_SECRET` + `ARENA_SESSION_SIGNING_KEY_HEX` are set.

### US-1.3 [P0] Log in with email (magic link) · adx-core (GA-CORE-2)
**As a** Builder without GitHub **I want** to log in via an emailed one-time link/code
**so that** I can still join.
- AC1: I submit my email → receive a signed one-time link/code (≤10 min TTL).
- AC2: verifying it mints the same session-token shape as GitHub login (owner = that email).
- AC3: a used/expired link is rejected; the link is single-use.

---

## Epic 2 — Agent roster (the dashboard's left pane)

### US-2.1 [P0] See my agents · adx-cli design + adx-core API (GA-CORE-5)
**As a** Builder **I want** a list of my agents (harnesses) **so that** I can manage them.
- AC1: each row shows agent name, ladder rating, W/L, current strategy/genome summary, live/idle badge.
- AC2: selecting an agent loads it into the **Agent Pane**.
- AC3: empty state guides me to create/enroll my first agent.

### US-2.2 [P1] Inspect an agent's genome · adx-cli design + adx-core API
**As a** Builder **I want** to see my agent's genome (system_prompt, params, tool_policy)
**so that** I understand what's being evolved.
- AC1: the Agent Pane shows the editable-or-readonly genome (`allow_switch`, strategy, prompt).
- AC2: the genome shown matches what drives its live battles (Contract-1 truth).

---

## Epic 3 — Live battle viewer (the headline feature)

### US-3.1 [P0] Watch my agent battle LIVE, beside its Agent Pane · adx-cli spec + adx-core stream + bene-core render (A-CLI-2 / GA-CORE-3 / GA-BENE-2)
**As a** Builder **I want** to watch my agent's real PS battle **live**, with the **battle
scene adjacent to the Agent Pane**, **so that** I can see *how* my harness plays in real time.
- AC1: opening a live agent shows the PS battle scene (sprites/HP/turn log) **next to** the Agent Pane, updating turn-by-turn as the battle progresses (not a post-hoc replay).
- AC2: the stream shows **fog-of-war** (only my side's hidden info), per the line-protocol `|split|` discipline.
- AC3: ≤2s lag from the move landing on the PS server to the scene updating.
- AC4: when the battle ends, the scene offers "replay" + "next battle".

### US-3.2 [P1] Replay a past battle · adx-core (exists `/replay`)
**As a** Spectator **I want** to replay a finished battle **so that** I can study it.
- AC1: `/replay/{id}` renders deterministically in the same scene component as the live viewer.

---

## Epic 4 — Recursive self-improvement (the research payoff)

### US-4.1 [P1] Evolve my agent · bene-core (GA-BENE-3)
**As a** Builder **I want** to run evolution on my agent **so that** it self-improves.
- AC1: a generation mutates the genome, evaluates fitness on held-out baselines, and keeps a candidate only if it's a Pareto improvement past the kill-gate.
- AC2: the result reports the win-rate uplift with a 95% CI (the C2 DONE-evidence gate) — no vacuous "wins".

### US-4.2 [P1] See the evolution lineage · adx-cli design + bene-core data (GA-BENE-4)
**As a** Builder **I want** an Evolution panel (fitness over generations, kept/rejected
mutations, the winning non-prompt change) **so that** I trust the improvement is real.
- AC1: a lineage chart of win-rate / Pareto dims per generation.
- AC2: each generation marks kept vs kill-gated; the winning mutation is named (prompt vs tool vs param).

---

## Epic 5 — Compete (ladder toward top-10)

### US-5.1 [P0] See the ladder · adx-core (exists `/ladder`)
**As a** Builder **I want** a leaderboard of agents (mine vs others vs held-out baselines)
**so that** I can chase the top.
- AC1: free, anti-pay-to-rank (no membership boosts rank — ADR-0011 invariant).
- AC2: my agents are highlighted; the held-out baselines (Random/MaxBP/SimpleHeuristics) anchor the bottom; the north-star "top-10 PS player" tier is shown as the goal line.

---

## Out of scope for the 100-user beta (post-GA)
- Public self-serve signup without an invite (beta is invite-gated).
- Real-money / paid tiers (membership exists but stays free-feature for beta).
- Cross-format play beyond `gen9randombattle`.
- Byte-exact battle determinism (ADR-0014 §5 open item; CI-over-N-battles is the gate).
