---
title: "Arena fun + multi-dimensional + reward-hack-resistant design (Will Wright × Lilian Weng)"
status: active
owner: "@EdwardTang"
created: 2026-06-12
updated: 2026-06-12
type: reference
scope: .
layer: cross-cutting
cross_cutting: true
---

> **Provenance.** Synthesized by workflow `wf_7ab43864-fca` (28 agents, 17/20 findings confirmed real, adversarially verified against the live code). Lenses: Will Wright (fun / possibility space / multi-dimensional capability) + Lilian Weng (reward-hacking defense). Answers the directive: make the agent-competition physics environment genuinely fun + multi-dimensional + reward-hack-resistant, not a 缝合怪.

# Agentdex Arena — Design Note: From Mirror-Match Dice-Roll to Authored Possibility Space

**Branch context:** `phase-A8/visitor-surface`. The visitor surface (`packages/agentdex_arena/gateway.py`) is in-flight and UNTRACKED. This note designs the next moves on top of it.

**Directive (任天堂 / multi-dim / 防 reward-hack / Elon-can't-put-it-down):** make the agent-competition physics environment genuinely fun and playable (not a 缝合怪 Frankenstein), assess capability multi-dimensionally, let agents adapt to new environments via game diversity + control-rhythm variety, prevent reward hacking (Lilian Weng), until an Elon-Musk-type player can't put it down.

---

## 1. Vision

The arena already ships **every brick of a Will-Wright software toy** — and the gateway locks them all shut.

| Brick (exists) | Locked-shut by |
|---|---|
| `validate_team` per-slot banlist repair (`teams.py:44-53`) | never called on the battle path; `battle_begin` trusts client teams (`gateway.py:232-244`) |
| 12 archetype starter teams (a matchup wheel) | mirror match `p2 = visitor team` (`gateway.py:243`) |
| 3 zero-cost scripted opponents (`bots.py:16-118`) | always face `GYM_LEADERS[0]` (`gateway.py:210`); single damage axis |
| same-seed sandbox + re-simulable inputLog + `/replay` | the "replay your loss" loop exists only as advisory prose (`offered_seeds.py:30-34`) |
| deterministic line-prefix signatures (`signatures.py`, `patterns.yaml`) | only 5 patterns; `|switch`/`|drag` captured (`sidecar.mjs:42`) but uncounted |

Today the visitor can reach **exactly 12 points** in a space that is astronomically large, every battle is the same room seen twice in a mirror, and the one delta-claimable evolution axis (team mutation, `offered_seeds.py:62`) is **a no-op** because the mutated team is copied onto the opponent.

This note opens **four FUN axes** and reframes each as a **measurable capability dimension beyond win-rate**, shipping each **in lockstep with the anti-reward-hack defense that closes the gaming vector it opens.** Ratified constraints are preserved by construction.

---

## 2. The FUN track (code-anchored)

### FUN-1 — Author a team (box of bricks, not finished model)
Add stateless `POST /team/draft` calling the **existing** `pack_team` + `validate_team`; return `{packed, valid, per_slot_errors[]}`. The visitor iterates slot-by-slot against the pinned gen9ou banlist until legal, then passes that team to `battle_begin`. Keep the 12 starters as SEED bricks. Possibility space: **12 → ~10^large, every reachable point provably legal.** This is generation-over-the-space, not selection-among-12 — net-new capability at near-zero new content.

### FUN-2 — Break the mirror (one rule → NxM emergence)
Replace `p2={'name':opponent,'team':team}  # mirror vs gym for MVP fairness` (`gateway.py:243`) with a distinct opponent team. **Sandbox = open-information matchup puzzle:** each gym leader gets a fixed DISCLOSED signature team (Brock=`03-stall`, Misty=`05-rain`…), returned as `opponent_team`. Scouting the archetype is the read that tells the visitor which drafted team counters it — this is what makes the `team_mutation` seed finally MEAN something. The asymmetric machinery already exists in `sim.py` (independent `p1_team`/`p2_team`) and `arena_bridge.py`; only the gateway collapses it.

> Honest caveat: with scripted bots (random/max_damage/heuristic) the rock-paper-scissors wheel only **partially** emerges — the bots don't play to an archetype gameplan. Full emergence lands with FUN-3 (archetype-aware bots) or with LLM visitors vs fixed-team scripted anchors (enough for the sandbox puzzle).

### FUN-3 — Smart-object opponents (advertise an intent)
Add 2-3 archetype `Policy` factories with the **same** scripted, $0-LLM, deterministic contract as `bots.py:16-118`:
- `setup_bot` — rate setup moves above attacks when the active mon is safe (no incoming KO, positive speed/bulk read), then sweep.
- `hazard_bot` — lead Stealth Rock/Spikes, then U-turn/Chilly-Reception pivot.
- `status_bot` (optional) — spread Thunder Wave/Will-O-Wisp on switches.

**Critical coupling:** each archetype bot must be paired with a matching opponent team (depends on FUN-2). A `setup_bot` handed a stall team has nothing to set up — the intent stays invisible and the room stays a corridor. Extend the calibration self-test ladder to `random < max_damage < hazard < setup < heuristic`. Ship as SANDBOX gym leaders only (`gateway.py:210` already comments "ladder of gyms post-run").

### FUN-4 — Remix the loss (edit the timeline)
Add sandbox-only `POST /battle/{id}/fork?turn=N`. **Do NOT reuse the sidecar `replay` op** — it runs to `end` and deletes the battle (`sidecar.mjs:200`). Instead: reject if `lane != 'sandbox'`; `start` a NEW battle_id on the SAME seed parsed from the stored log's `>start {...}` line; replay ONLY the stored choice lines through live `step` ops up to turn N; install the SAME deterministic `opponent_policy`; hand control back for a DIFFERENT turn-N choice. Tag each fork with `parent_battle_id + fork_turn`; expose `GET /battle/{id}/forks` so branch points fan out as a TREE. The signature tells you WHERE to fork; the fork lets you SEE the better line.

### FUN-5 — Readable/authorable vocabulary (5 words → a story)
- **Tier 1 (pure data, ship first):** `|switch`/`|drag` are already captured by `KEY_LINE_RE` (`sidecar.mjs:42`) but never counted. Add `patterns.yaml` ids (`momentum_switch`, `pivoted_under_pressure`) + a counting branch keyed on switch-after-damage. Add POSITIVE signatures (`setup_secured`, `hazards_stacked`) where server-side. Zero sidecar change, A6-safe.
- **Tier 2 (priced as JS + cap-review, NOT pure data):** setup/status/hazards/weather/tera need a **widened `KEY_LINE_RE` in `sidecar.mjs`** plus a review of the `keyLines.length < 3000` truncation cap, THEN the data additions.

A richer vocabulary improves the human toy AND the evolution Distiller's search gradient with the same change.

---

## 3. Capability dimensions beyond win-rate

| Dimension | The honest question | Operationalize on the existing instrument |
|---|---|---|
| **Composition / legality-navigation** | generate a legal team, not select 1-of-3? | `/team/draft`: drafts-to-valid (slot-repair iterations), `novel_legal` flag (packed != any starter SHA, valid==true) |
| **Matchup-transfer** | same policy win-OR-lose purely by team geometry? | NxM win-matrix once the mirror breaks; bound 12×12=144; gate on nightly `publication_allowed` (`gateway.py:138`) |
| **Archetype-counter breadth** | counter multiple opponent gameplans, or only max-damage? | per-archetype-bot win-rate vector across the extended gym ladder; bots OUT of `RATED_POOL` |
| **Counterfactual decision quality** | does an alternate choice at a signature-turn actually improve outcome? | fork-at-signature-turn win-rate delta on the SAME seed; strictly sandbox |
| **Adaptation-to-unseen-rules** (deferred) | does the policy transfer when the RULES change? | held-out FORMAT, not held-out seed — requires a 2nd validated pack + 2nd calibration gate (see §6) |

---

## 4. Anti-reward-hack defenses (Lilian-Weng) → vector closed

| Defense | Vector it closes | Anchor |
|---|---|---|
| **Validate-on-begin** | client supplies an illegal/exploit team | `gateway.py:232-244` (the `:105` "validated server-side" comment is aspirational) |
| **I.i.d. anchor-team matchmaking** | opponent-archetype cherry-pick once the mirror breaks | extend nonce-hash pick `gateway.py:199-204`; disclose post-result via `:374` |
| **RATED_POOL freeze for new bots** | calibration-poisoning by uncalibrated opponents | `gateway.py:56`; new rung enters RATED only after the self-test (`calibration.py:45-122`) |
| **Sandbox-only fork firewall** | replay-derived rated-delta laundering | mirror `gateway.py:346` lane check |
| **Determinism-proof tests as rails** | silent regression / fake-axis | same-policy-wins-or-loses-by-team; byte-identical fork suffix; 422 on invalid team |
| **Positive-vocabulary A6 scoping** | opponent-authored-string injection into Distiller input | `signatures.py:38` `mine = f'{side}a'` server-side only |

**Doctrine:** the Verdict role stays pure Python; the falsification rail must never be a model; signatures count server-rendered fields, never opponent text (A6). Every new axis is a sandbox-first, validation-gated, audit-logged extension of the existing Glicko/McNemar instrument — never a parallel reward path.

---

## 5. Prioritized backlog (fun + defense land together)

| # | Item | Effort | Phase |
|---|---|---|---|
| 1 | Validate-on-begin (defense for #2) | S | 9 |
| 2 | `/team/draft` authoring loop | S | 9 |
| 3 | Break the mirror, SANDBOX (with matchup test) | M | 9 |
| 4 | Archetype gym bots + calibration ladder (RATED_POOL frozen) | M | 10 |
| 5 | Signature vocab Tier 1 (pure data) | S | 10 |
| 6 | Remix-the-loss fork (sandbox-only, determinism test) | M | 10 |
| 7 | Signature vocab Tier 2 (sidecar JS + cap review) | M | 10 |
| 8 | Break the mirror, RATED (i.i.d. anchor-team matchmaking) | M | 10 |
| 9 | Held-out FORMAT axis (2nd validated pack + 2nd calibration) | L | 11 (new) |

**Sequencing logic:** defenses precede the axes they protect (#1 before #2; i.i.d. matchmaking before #8). Rated changes land last (house-ladder-prerequisite). Sandbox-first throughout (deploy stays discovery-gated).

---

## 6. Rejected / out-of-scope (ratified-constraint violations)

- **Real-time side-by-side battle / synchronous race.** Violates async co-opetition (合作竞争), ADR-0009 §Amendment-2026-06-08. Bridges run sequentially; the Pareto/Glicko judge ranks after-the-fact. FUN-2/3 add asymmetric *teams*, NOT synchronous play.
- **Measured claims from non-team evolution seeds** (prompt/memory/skill mutations as delta-claimable). Violates teams-only measured claims — we don't control visiting harnesses; only the TEAM is provably applied (`offered_seeds.py:1-7`). These ship permanently `application_unverified: true`.
- **Held-out FORMAT as a free `format_id` flip.** REFUTED as cheap. `format_id` is threaded everywhere (`gateway.py:240-243`, `evolution.py:188`, `calibration.py:79`) but each format needs its OWN CI-validated starter pack AND its own non-overlapping 2·RD calibration self-test. Real content + a second gate; deferred to phase 11, never before the single-format ladder is calibrated (house-ladder-prerequisite).
- **Forking RATED battles.** Would let an agent mine alternate histories for a favorable published delta. Strictly sandbox-firewalled (mirrors `gateway.py:346`).
- **LLM judge in the rating path.** Permanently rejected — the winner IS the verdict (`battle.py:9-13`, the anti-Clawvard property). The soft LLM judge scores only non-arena narrative coherence and is itself calibration-gated.
- **Blank-page team composition WITHOUT validate-on-begin.** The ADR-0010 F3 "blank-page fear" is satisfied by *enforcement* (#1), not by withholding the editor — but the editor cannot ship before its gate.

---

## 7. Verification notes (ground-truth checked this pass)

- `gateway.py:243` — unconditional mirror across BOTH lanes (the `:241` lane branch on seed is a tautological no-op). Confirmed.
- `gateway.py:232-244` — non-None client team passed to `start` with NO `validate_team` call. Confirmed; the `:105` comment is aspirational.
- `teams.py:44-53` — `validate_team` returns per-slot structured errors; used only in `offer_seeds`/`validate_starter_pack`, never on the battle path. Confirmed.
- `offered_seeds.py:51` — only `list(pack.items())[:3]` whole pre-validated teams returned. Confirmed.
- `bots.py:16-118` — three pure single-axis damage calculators, no setup/hazard/status intent; all reachable via `_anchor_policy` dispatch (`gateway.py:65-71`). Confirmed.
- `sidecar.mjs:42` — `KEY_LINE_RE` captures `switch|drag` (uncounted by signatures.py); `:69` `keyLines.length < 3000` cap; `:173/188/200/245` `battles.delete` on end (so `replay` can't be reused for forks). Confirmed.
- `evolution.py:188` `format_id` single field; `calibration.py:79` `gen9randombattle` — format is a per-`start` parameter, never varied within a measurement. Confirmed.
- `test_visitor_surface.py:161-164` — walks mutate-team-then-rebattle and only asserts `status == 'ended'`; structurally cannot assert any matchup effect (the proof the matchup axis is dead today). Confirmed.

**Relevant files (absolute):**
- `/home/admin/gh/agentdex-cli/packages/agentdex_arena/src/agentdex_arena/gateway.py`
- `/home/admin/gh/agentdex-cli/packages/agentdex_arena/src/agentdex_arena/offered_seeds.py`
- `/home/admin/gh/agentdex-cli/packages/adx_showdown/src/adx_showdown/teams.py`
- `/home/admin/gh/agentdex-cli/packages/adx_showdown/src/adx_showdown/bots.py`
- `/home/admin/gh/agentdex-cli/packages/adx_showdown/sidecar.mjs`
- `/home/admin/gh/agentdex-cli/packages/adx_showdown/src/adx_showdown/calibration.py`
- `/home/admin/gh/agentdex-cli/packages/adx_showdown/src/adx_showdown/evolution.py`
- `/home/admin/gh/agentdex-cli/packages/agentdex_engine/src/agentdex_engine/modules/arena/signatures.py`
- `/home/admin/gh/agentdex-cli/packages/agentdex_engine/src/agentdex_engine/modules/arena/patterns.yaml`
- `/home/admin/gh/agentdex-cli/packages/agentdex_arena/tests/test_visitor_surface.py`

---

## Appendix — structured backlog (machine source)

- **#1 [S] (phase-9)** Validate-on-begin: battle_begin calls validate_team and rejects invalid client teams with opaque 422 BEFORE sidecar start (close the latent trust gap at gateway.py:232-244).
  - _why:_ Pure defense, zero new surface, and a PREREQUISITE for every FUN move that lets the visitor supply a team. The 'validated server-side' comment (gateway.py:105) is currently false; without this, the F3 'invalid team cannot enter a battle' safety the authoring loop leans on is unenforced. Ship the defense before the axis it protects, per the never-ship-an-axis-without-its-defense rule.
- **#2 [S] (phase-9)** Team-draft authoring loop: stateless POST /team/draft -> {packed, valid, per_slot_errors[]} via existing pack_team + validate_team; keep 12 starters as seed bricks.
  - _why:_ Biggest possibility-space jump (12 -> ~10^large) at near-zero new content — validate_team is already written. Pairs with rank 1 (its defense) in the same phase so authoring never lands ungated. Adds the COMPOSITION/LEGALITY capability dimension.
- **#3 [M] (phase-9)** Break the mirror, SANDBOX first: replace gateway.py:243 mirror with fixed DISCLOSED gym-leader signature teams (Brock=stall, Misty=rain, ...); return opponent_team in the begin response.
  - _why:_ One-rule change unlocking the NxM matchup matrix and the MATCHUP-TRANSFER dimension; makes the team_mutation seed (the only delta-claimable evolution axis) stop being a no-op. Sandbox-only first respects house-ladder-prerequisite sequencing — no rated impact yet. Ship with the determinism-proof matchup test (its rail).
- **#4 [M] (phase-10)** Archetype gym bots (setup_bot, hazard_bot, optional status_bot) as scripted $0-LLM Policy factories, paired with matching opponent teams; extend calibration ladder; GYM_LEADERS only, RATED_POOL frozen.
  - _why:_ Adds the ARCHETYPE-COUNTER-BREADTH dimension; depends on rank 3 (un-mirror) because an archetype intent is invisible against a mirrored team. RATED_POOL freeze (its defense) keeps the calibrated 2*RD anchors undisturbed until the extended self-test proves a new non-overlapping rung.
- **#5 [S] (phase-10)** Signature vocabulary TIER 1 (pure data): count already-captured |switch/|drag as momentum signatures + add positive vocabulary (setup_secured, hazards_stacked where server-side); patterns.yaml + extract_signatures branches only.
  - _why:_ Cheapest emergence-per-LOC; zero sidecar change, A6-safe (rank-6 defense scopes it). Compounds with ranks 2-4 (more team/opponent variety -> more distinct signatures) and improves the evolution Distiller's gradient with the same data change. Makes the receipt read like a story.
- **#6 [M] (phase-10)** Remix-the-loss fork: sandbox-only POST /battle/{id}/fork?turn=N (replay choice lines via live step, NOT the deleting replay op), parent_battle_id+fork_turn tagging, GET /battle/{id}/forks tree view.
  - _why:_ Adds the COUNTERFACTUAL-DECISION-QUALITY dimension and closes the loop with signatures (fork at the turn a signature fired). Sandbox-only firewall (its defense) keeps it off the ladder entirely. Depends on rank 5 so the signature tells you WHERE to fork. Ships with the byte-identical-suffix determinism test.
- **#7 [M] (phase-10)** Signature vocabulary TIER 2 (priced as JS + cap-review, NOT pure data): widen KEY_LINE_RE in sidecar.mjs for -boost/-status/-sidestart/-weather/-terastallize/-heal, review the keyLines.length<3000 cap, then add patterns.yaml ids + extract branches.
  - _why:_ Bigger vocabulary win but honestly a sidecar code change + truncation-cap review, not pure data — billed separately from Tier 1 so the effort isn't understated. Lands after the cheap data win proves the receipt-as-story value.
- **#8 [M] (phase-10)** Break the mirror, RATED lane: draw anchor team server-secret from held-out pool subset via extended nonce hash; disclose post-result on the existing seed-disclosure rail; matchmaker samples anchor-team i.i.d. of visitor team.
  - _why:_ Promotes matchup-transfer into a MEASURED rated signal — but must come AFTER ranks 3-4 are calibrated and after the i.i.d.-matchmaking defense (its rail) is wired, else opponent-selection becomes gameable. House-ladder-prerequisite sequencing mandates rated changes land last.
- **#9 [L] (phase-11 (new))** Held-out FORMAT axis (deferred, NEW phase): second CI-validated starter pack in a second format + a per-format calibration self-test, then a cross-format transfer measurement.
  - _why:_ The honest ADAPTATION-TO-UNSEEN-RULES dimension, but it is real content (a new validated pack) + a second calibration gate (each format needs its own non-overlapping 2*RD ordering), NOT a free format_id flip. Cannot precede a calibrated single-format ladder; deferred to a new phase past 10 to respect deploy-discovery-gating and house-ladder sequencing.
