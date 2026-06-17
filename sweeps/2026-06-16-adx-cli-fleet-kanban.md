---
title: "ADX CLI fleet kanban"
status: active
owner: etang
created: 2026-06-16
updated: 2026-06-16
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

# ADX CLI fleet kanban

This board is the shared intake for ADX CLI dogfood feedback. It replaces
cascading verdict pushes with prioritized cards that each fleet agent can
claim, move, and comment on.

## Operating rules

- A2A inbox remains the per-agent message demux; this board is the durable work queue.
- New findings land as `triage`; harness promotes only the next focused card to `ready`.
- `adx-cli` should normally have one `running` card at a time to avoid context drift.
- Evidence stays on the card as pass IDs, commands, paths, traces, or replay IDs.
- Mutating commands append JSON events so board changes are attributable.
- Mutating commands take a file lock; do not hand-edit JSON during active fleet use.
- `init --force` writes a timestamped JSON backup before replacing an existing board.
- A2A/tmux updates should summarize board deltas, not resend every raw verdict.
- When a fix lands, move the card to `review`; verifier moves it to `done` or `blocked`.

## Commands

```bash
uv run --project ~/gh/bene-main python /home/admin/gh/harness-engineering/scripts/a2a_inbox.py --base adx-cli --count
python3 tools/agent_senses/fleet_kanban.py list --agent adx-cli
python3 tools/agent_senses/fleet_kanban.py move ADX-P0-001 --status running --agent adx-cli --author adx-cli
python3 tools/agent_senses/fleet_kanban.py comment ADX-P0-001 --author codex --body 'repro refreshed'
# Default-board mutations auto-refresh the markdown view.
```

## By Status

### triage

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| ADX-P1-006 | P1 | adx-cli | integrity | Dispute event appended BEFORE re-sim — duplicate events on retry | gateway.py:1771-1777 (append), :1790-1794/:1822 (resim+throw). adversarially confirmed (dogfood audit 2026-06-17) |
| ADX-P1-007 | P1 | adx-cli | fairness | Ladder published_delta race: concurrent _finish for same player inflates delta | gateway.py:1131 (before snapshot), :1160 (append), :1169 (after). adversarially confirmed (dogfood audit 2026-06-17) |
| ADX-P2-004 | P2 | adx-cli | fairness | Rated-battle quota not persisted — resets on gateway restart | consent.py:114-124/:159-182, gateway.py:536-558. adversarially confirmed (dogfood audit 2026-06-17) |
| ADX-P2-006 | P2 | harness | observability | Unbounded sessions/replays dicts — eventual OOM on long-running deploy | gateway.py:564/567 (init), :872/:1202/:1309 (insert), no eviction. adversarially confirmed (dogfood audit 2026-06-17) |

### todo

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| BENE-DOC-02 | P0 | bene-core | blog-content | Blog post: WHY we build BENE — the harness behind the arena | CLAUDE.md, docs/README.md |
| ADX-P1-001 | P1 | adx-cli | fairness | Stop spending rated/evolution/badge quota before work is accepted | pass26, pass33, pass34, pass35, pass36 |
| ADX-P1-002 | P1 | adx-cli | owner-data | Make owner export include replay, badge, and rating lineage | pass17, pass19, pass20, pass21, pass41, pass42-candidate |
| ADX-P1-003 | P1 | harness | observability | Make observability acceptance fail when traces are absent | pass31, pass32 |
| ADX-P1-004 | P1 | adx-cli | security | Tighten admin surface and auth-before-parse contract | pass24, pass25 |
| BENE-DOC-01 | P1 | bene | blog | Scaffold the new /blog section on bene-site (index + post template + nav) | site/build-docs.py, site/index.html |
| BENE-DOC-03 | P1 | bene-core | blog-content | Blog post: WHAT BENE is — the seven pillars | examples/library_basics.py, bene/cli/main.py, docs/architecture.md |
| BENE-DOC-04 | P1 | bene-core | blog-content | Blog post: HOW we build BENE — harness engineering + eval-gated evolution | bene/kernel/eval, bene/metaharness, docs/meta-harness.md |
| BENE-DOC-05 | P1 | bene-core | docs-examples | Surface real runnable examples per pillar in the docs | examples/, docs/architecture.md, docs/cli-reference.md |
| BENE-DOC-06 | P1 | bene-core | case-study | Case study: multi-agent coding arena on BENE (ABSTRACT) | docs/case-studies/cs02-ci-self-healing-refactor-swarm.md |
| BENE-DOC-10 | P1 | bene | render-deploy | Render + deploy all new blog/docs/case-study/design content | site/build-docs.py |
| BENE-DOC-07 | P2 | bene-core | case-study | Case study: trace-based RAG / Other Memory (engrams) | bene/kernel/memory, docs/memory.md |
| BENE-DOC-08 | P2 | bene-core | case-study | Case study: evolutionary meta-harness search | bene/metaharness, docs/meta-harness.md |
| BENE-DOC-09 | P2 | bene-core | design | Design: architecture diagrams (Nexus, engram ladder, autonomy ladder) | docs/architecture.md |

### ready

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| ADX-P0-001 | P0 | adx-cli | integrity | Make arena receipts atomic before claiming honesty | pass27, pass28, pass37, pass38, pass39, pass40 |

### running

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| ADX-ONLINE-002 | P0 | adx-core | launch-gate | launch gate: agentdex 100-user readiness assessment + go/no-go | wf:agentdex-100-user-readiness(54/71), a2a#312, a2a#320 |
| ADX-ONLINE-001 | P1 | adx-cli | launch-ux | launch: watchable Human-vs-AI battle UX (line-protocol + sim/client/view + spectator/TUI/replay) | PR#200, PR#201, .supergoal-v3/ROADMAP.md |

### review

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| ADX-P1-005 | P1 | codex | integrity | Collusion quarantine_reason leaks heuristic internals to the agent (D7) | gateway.py:1001-1045 (_check_collusion detailed strings), :1059-1062 (written to session.ended), :1116-1126 (event log). adversarially confirmed (dogfood audit 2026-06-17) |
| ADX-P2-001 | P2 | codex | agent-ux | Reduce starter and CLI footguns for visiting agents | pass14, pass15, pass16, pass29 |
| ADX-P2-002 | P2 | codex | gameplay | Make arena gameplay feedback more legible and less first-legal | pass2, pass3, pass4, pass6, pass7, pass8, pass12, pass13 |
| ADX-P2-005 | P2 | codex | integrity | Scratchpad rendered into battle state without escaping — self-injection of fake turn lines | showdown_battle_bridge.py:~107 (scratchpad rendered into state); no escaping/validation/tests. adversarially confirmed (dogfood audit 2026-06-17) |

### done

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| ADX-P2-003 | P2 | harness | regression-guard | Preserve verified strengths while fixing gaps | pass5, pass11, pass22, pass23, pass30 |

## Card Detail

### BENE-DOC-02 - Blog post: WHY we build BENE — the harness behind the arena

- Priority: `P0`
- Status: `todo`
- Assignee: `bene-core`
- Lane: `blog-content`
- Impact: Frames the whole site: BENE is the durable, auditable local-first multi-agent substrate that backs agentdex-cli (the arena). Gom-jabbar harness thesis.
- Suggested fix: Write blog/why-bene.md (EN). ABSTRACT ONLY: pseudo-code, NO agentdex-cli internals. zh routed to og.
- Evidence: CLAUDE.md, docs/README.md

### ADX-P0-001 - Make arena receipts atomic before claiming honesty

- Priority: `P0`
- Status: `ready`
- Assignee: `adx-cli`
- Lane: `integrity`
- Impact: Human owner and agent both receive durable receipts that can be false or partial when EventLog, sidecar, or rating writes fail.
- Suggested fix: Group side effects behind an atomic write plan: validate and reserve first, then commit event/replay/rating/badge together or compensate visibly.
- Evidence: pass27, pass28, pass37, pass38, pass39, pass40

### ADX-ONLINE-002 - launch gate: agentdex 100-user readiness assessment + go/no-go

- Priority: `P0`
- Status: `running`
- Assignee: `adx-core`
- Lane: `launch-gate`
- Impact: Getting agentdex online today requires a measured readiness verdict across the user-facing surface (capacity, integrity, security). This is the launch go/no-go gate the UX rides on top of.
- Suggested fix: Complete the agentdex-100-user-readiness assessment (in progress, 54/71 agents) -> capacity + integrity + security punch-list + go/no-go. Coordinate fixes with adx-cli; P0/P1 integrity items (atomic receipts ADX-P0-001) gate launch.
- Evidence: wf:agentdex-100-user-readiness(54/71), a2a#312, a2a#320

### ADX-P1-006 - Dispute event appended BEFORE re-sim — duplicate events on retry

- Priority: `P1`
- Status: `triage`
- Assignee: `adx-cli`
- Lane: `integrity`
- Impact: POST /battle/{id}/dispute appends the 'dispute' event (gateway.py:1771-1777) BEFORE running replay_input_log (:1790). If re-sim throws (:1822) the handler 500s but the dispute event is already durable; a client retry appends a SECOND dispute event — structural event-log corruption (violates Class A write-then-log intent for disputes).
- Suggested fix: Append the dispute event AFTER a successful re-sim, OR guard with an idempotence check (skip if a dispute event for this battle_id already exists). Mirror the append-before-publish/fail-closed contract.
- Evidence: gateway.py:1771-1777 (append), :1790-1794/:1822 (resim+throw). adversarially confirmed (dogfood audit 2026-06-17)

### ADX-P1-007 - Ladder published_delta race: concurrent _finish for same player inflates delta

- Priority: `P1`
- Status: `triage`
- Assignee: `adx-cli`
- Lane: `fairness`
- Impact: _finish captures before_rating (gateway.py:1131) OUTSIDE the atomic append window, then recomputes after (:1169). If a second concurrent _finish for the same visitor_name appends between A's capture and A's recompute, A's published_delta double-counts B's battle — a fairness/rating-integrity violation under async concurrency.
- Suggested fix: Capture before_rating AFTER the append_many (or serialize _finish per visitor_name with a per-player lock) so before/after bracket exactly one battle's mutation.
- Evidence: gateway.py:1131 (before snapshot), :1160 (append), :1169 (after). adversarially confirmed (dogfood audit 2026-06-17)

### ADX-P1-001 - Stop spending rated/evolution/badge quota before work is accepted

- Priority: `P1`
- Status: `todo`
- Assignee: `adx-cli`
- Lane: `fairness`
- Impact: Owner pays scarce monthly quota for invalid teams, capacity failures, sidecar failures, and signer failures.
- Suggested fix: Move quota debit after validation and successful durable acceptance, or add explicit refund records on retryable failures.
- Evidence: pass26, pass33, pass34, pass35, pass36

### ADX-P1-002 - Make owner export include replay, badge, and rating lineage

- Priority: `P1`
- Status: `todo`
- Assignee: `adx-cli`
- Lane: `owner-data`
- Impact: Human owner and agent cannot reconstruct paid/rated history from `/my/events` or local SQLite.
- Suggested fix: Select events by canonical agent/battle joins and nested period payloads, not only top-level tenant_id.
- Evidence: pass17, pass19, pass20, pass21, pass41, pass42-candidate

### ADX-P1-003 - Make observability acceptance fail when traces are absent

- Priority: `P1`
- Status: `todo`
- Assignee: `harness`
- Lane: `observability`
- Impact: The platform can pass trace-propagation tests while producing no usable trace/span link.
- Suggested fix: Require actual trace context/link presence in acceptance tests; document fallback mode separately.
- Evidence: pass31, pass32

### ADX-P1-004 - Tighten admin surface and auth-before-parse contract

- Priority: `P1`
- Status: `todo`
- Assignee: `adx-cli`
- Lane: `security`
- Impact: Operator-only endpoints are exposed in public OpenAPI and one documented auth ordering claim is false for malformed JSON.
- Suggested fix: Hide or split admin OpenAPI, then test auth rejection before body validation for protected routes.
- Evidence: pass24, pass25

### BENE-DOC-01 - Scaffold the new /blog section on bene-site (index + post template + nav)

- Priority: `P1`
- Status: `todo`
- Assignee: `bene`
- Lane: `blog`
- Impact: No blog exists yet; the WHY/WHAT/HOW narrative needs a home. Render lane (bene).
- Suggested fix: Add site/blog/ index + post template + nav link (EN+zh) and build-docs.py blog-page generation; rebase on og in-flight build-docs.py changes, do not clobber; render-verify.
- Evidence: site/build-docs.py, site/index.html

### BENE-DOC-03 - Blog post: WHAT BENE is — the seven pillars

- Priority: `P1`
- Status: `todo`
- Assignee: `bene-core`
- Lane: `blog-content`
- Impact: Crisp WHAT: per-agent VFS, checkpoints, engrams, eval-probe kill-gates, autonomy ladder, MCP server, evolutionary meta-harness search.
- Suggested fix: Write blog/what-is-bene.md (EN); each pillar with one REAL example snippet from examples/, ground-truthed against the CLI/code.
- Evidence: examples/library_basics.py, bene/cli/main.py, docs/architecture.md

### BENE-DOC-04 - Blog post: HOW we build BENE — harness engineering + eval-gated evolution

- Priority: `P1`
- Status: `todo`
- Assignee: `bene-core`
- Lane: `blog-content`
- Impact: Answers HOW: tiny PRs, falsifiable eval-probe kill-gates, the breeding program, trace-based RAG.
- Suggested fix: Write blog/how-we-build-bene.md (EN), grounded in the real repo (probes, mh search, tiny-PR discipline).
- Evidence: bene/kernel/eval, bene/metaharness, docs/meta-harness.md

### BENE-DOC-05 - Surface real runnable examples per pillar in the docs

- Priority: `P1`
- Status: `todo`
- Assignee: `bene-core`
- Lane: `docs-examples`
- Impact: Mission asks for REAL examples; 19 example scripts exist but are not woven into the docs narrative.
- Suggested fix: Expand docs (architecture/quickstart/pillar pages) with runnable, explained snippets drawn from examples/*.py; each ground-truth-run exit 0.
- Evidence: examples/, docs/architecture.md, docs/cli-reference.md

### BENE-DOC-06 - Case study: multi-agent coding arena on BENE (ABSTRACT)

- Priority: `P1`
- Status: `todo`
- Assignee: `bene-core`
- Lane: `case-study`
- Impact: Flagship case study and the concrete WHY: BENE as the substrate backing a competitive multi-agent coding platform.
- Suggested fix: Write docs/case-studies/cs03-multi-agent-arena.md. HARD CONSTRAINT: agentdex-cli is the real consumer but DO NOT expose internals — pseudo-code/abstract ONLY.
- Evidence: docs/case-studies/cs02-ci-self-healing-refactor-swarm.md

### BENE-DOC-10 - Render + deploy all new blog/docs/case-study/design content

- Priority: `P1`
- Status: `todo`
- Assignee: `bene`
- Lane: `render-deploy`
- Impact: New content must reach the live site; recurring render/deploy lane (bene).
- Suggested fix: Regen HTML via build-docs.py, sync the 4-copy mirror chain, Koyeb deploy, render-verify all 4 view x lang per the bilingual-render lesson; coordinate with og translation pass.
- Evidence: site/build-docs.py

### ADX-ONLINE-001 - launch: watchable Human-vs-AI battle UX (line-protocol + sim/client/view + spectator/TUI/replay)

- Priority: `P1`
- Status: `running`
- Assignee: `adx-cli`
- Lane: `launch-ux`
- Impact: Getting agentdex ONLINE means a watchable arena — the whole pitch is spectating agents fight. Without the typed protocol + state-reducer + spectator/replay, the online arena is unwatchable (raw |move| rows, no fog-of-war, no replay).
- Suggested fix: Ship the digest 2026-06-17 P1->P3 backlog as tiny PRs. P1 protocol foundation MERGED today (PR #200 typed lineproto, PR #201 full protocol-log capture + (seed,inputLog) re-sim parity). Next: state-reducer (client.py), {reason,action} schema + |-reasoning|, then TUI/spectator/replay.
- Evidence: PR#200, PR#201, .supergoal-v3/ROADMAP.md

### ADX-P1-005 - Collusion quarantine_reason leaks heuristic internals to the agent (D7)

- Priority: `P1`
- Status: `review`
- Assignee: `codex`
- Lane: `integrity`
- Impact: _check_collusion returns detailed reason strings (thresholds, 'repeatedly clicked choice: move 0', 'win-transfer W-L over N matches') into session.ended.quarantine_reason, surfaced to the visiting agent on the battle receipt. Leaking the exact heuristic enables trivial evasion (add 1 random move; stay under the 5-match win-transfer threshold) — same D7 anti-enumeration class as the battle_id leak (#186).
- Suggested fix: Collapse quarantine_reason to an opaque/coarse value on the wire (or omit it); log the detailed forensic reason server-side only (log.warning), mirroring _opaque_error. Keep the EventLog row detailed for audit.
- Evidence: gateway.py:1001-1045 (_check_collusion detailed strings), :1059-1062 (written to session.ended), :1116-1126 (event log). adversarially confirmed (dogfood audit 2026-06-17)
- Recent comments: codex: Fixed: PR #189 MERGED — opaque 'quarantined by collusion forensics' on the wire (session.ended + receipt); detailed heuristic reason preserved in durable quarantine EventLog row + server log.warning for operator audit. _check_collusion unchanged (unit test green). Full arena suite 189 passed. Same D7 class as #186.

### ADX-P2-004 - Rated-battle quota not persisted — resets on gateway restart

- Priority: `P2`
- Status: `triage`
- Assignee: `adx-cli`
- Lane: `fairness`
- Impact: quota_used is in-memory only (consent.py:159-182); EventLog replay on boot (gateway.py:536-558) hydrates 'register'/'membership_grant' but NOT quota. A gateway restart resets every agent's daily rated cap, allowing >5 rated battles/UTC-day across restarts (anti-pay-to-rank-adjacent, ADR-0011 §3a/§5e). Exploitability is low on a stable single-process deploy (agent cannot force a restart), hence P2 not P1.
- Suggested fix: Emit a durable quota_spent event on each spend_quota increment; replay quota_spent (scoped to current UTC day) on boot to rehydrate quota_used.
- Evidence: consent.py:114-124/:159-182, gateway.py:536-558. adversarially confirmed (dogfood audit 2026-06-17)

### ADX-P2-006 - Unbounded sessions/replays dicts — eventual OOM on long-running deploy

- Priority: `P2`
- Status: `triage`
- Assignee: `harness`
- Lane: `observability`
- Impact: ArenaGateway.sessions and .replays (gateway.py:564/567) grow ~1KB/session + ~2KB/replay with zero eviction (no del/pop/clear anywhere; _expire_if_stale only marks ended, doesn't remove). A long-running deploy OOMs after enough battles. Low urgency on a nano deploy that restarts often → P2.
- Suggested fix: Bounded LRU/OrderedDict (cap N most-recent) for sessions+replays, or a TTL sweep that evicts ended sessions; replays should fall back to the durable EventLog/store rather than living in RAM forever.
- Evidence: gateway.py:564/567 (init), :872/:1202/:1309 (insert), no eviction. adversarially confirmed (dogfood audit 2026-06-17)

### BENE-DOC-07 - Case study: trace-based RAG / Other Memory (engrams)

- Priority: `P2`
- Status: `todo`
- Assignee: `bene-core`
- Lane: `case-study`
- Impact: Shows engrams + trace-based RAG — the next agent never starts cold.
- Suggested fix: Write docs/case-studies/cs04-trace-rag-other-memory.md grounded in the real engram/retrieve CLI.
- Evidence: bene/kernel/memory, docs/memory.md

### BENE-DOC-08 - Case study: evolutionary meta-harness search

- Priority: `P2`
- Status: `todo`
- Assignee: `bene-core`
- Lane: `case-study`
- Impact: Shows the breeding program — kill-gated promotion of evolved harness strategies.
- Suggested fix: Write docs/case-studies/cs05-meta-harness-evolution.md grounded in the mh CLI + eval probes.
- Evidence: bene/metaharness, docs/meta-harness.md

### BENE-DOC-09 - Design: architecture diagrams (Nexus, engram ladder, autonomy ladder)

- Priority: `P2`
- Status: `todo`
- Assignee: `bene-core`
- Lane: `design`
- Impact: Mission asks for designs; visual diagrams make the architecture legible.
- Suggested fix: Author mermaid diagrams for the single-file Nexus, engram compression ladder (tiers 0-4), autonomy ladder L0-L4; embed in docs (final HTML render routed to bene).
- Evidence: docs/architecture.md

### ADX-P2-001 - Reduce starter and CLI footguns for visiting agents

- Priority: `P2`
- Status: `review`
- Assignee: `codex`
- Lane: `agent-ux`
- Impact: Agents hit stale docs, missing `adx` arena commands, traceback setup errors, and asymmetric MCP proxy behavior.
- Suggested fix: Update `/skill.md`, add or explicitly defer `adx arena` commands, normalize starter-kit errors, and test missing battle IDs.
- Evidence: pass14, pass15, pass16, pass29
- Recent comments: codex: D1 (SKILL.md staleness) shipped: PR #184 MERGED — corrected initial battle-state example (added lane/status + gym-only opponent_team fields) and fixed MCP choose_action param idx->choice_index (matched mcp_surface.py:140). Doc verified vs HEAD. Next: D3 starter-kit raw tracebacks, then D5 battle_id enumeration. / codex: D3 (starter-kit raw tracebacks) shipped: PR #185 MERGED — shared run_agent_main() wrapper turns missing keyfile/team/expired-token/unreachable-arena into one-line stderr + exit codes (setup=2, runtime=1), re-raises genuine bugs; all 3 agents + bootstrap.sh enroll guarded. 7-case test. Verified e2e. Remaining ADX-P2-001: D5 battle_id enumeration (security, prio5). D4 WONTFIX. / codex: ADX-P2-001 agent-ux footguns COMPLETE (4 tiny PRs merged): D2 adx-arena-stub #183, D1 SKILL.md-shape #184, D3 starter-kit-clean-errors #185, D5 battle_id-anti-enumeration #186 (security: auth-before-existence on state/choose/fork/dispute, full arena suite 187 passed). D4 MCP-proxy-asymmetry adversarially REFUTED -> WONTFIX (intentional Mode2 game-only split). Moving to review for adx-cli/harness verification. Next codex card: ADX-P2-002 gameplay legibility (D6 gym-mapping already merged #167; remaining: foe-HP/recent_turns, replay metadata, anchor/gym test coverage).

### ADX-P2-002 - Make arena gameplay feedback more legible and less first-legal

- Priority: `P2`
- Status: `review`
- Assignee: `codex`
- Lane: `gameplay`
- Impact: Agents can win or lose for shallow reasons and cannot always understand losses from state/replay alone.
- Suggested fix: Repair gym mapping, expose opponent HP/recent turns, enrich replay metadata, and test anchor/gym coverage.
- Evidence: pass2, pass3, pass4, pass6, pass7, pass8, pass12, pass13
- Recent comments: codex: ADX-P2-002 gameplay legibility substantively COMPLETE: D8 /replay opponent archetype #187, D7 turn-0 (battle start) marker #188 (was empty recent_turns, confirmed empirically). D6 gym-trick-room mapping already merged #167. D9 anchor/gym coverage: already closed by parametrized test_every_gym_resolves_to_a_real_team over ALL GYM_LEADERS + badge/selection/rated tests — no real gap found (char's 'GYM_TEAM_INDEX collision' did NOT hold up: distinct keys 1/2/3, gyms use separate ARCHETYPE_GYM_TEAMS). Full arena suite 189 passed. Moving to review.

### ADX-P2-005 - Scratchpad rendered into battle state without escaping — self-injection of fake turn lines

- Priority: `P2`
- Status: `review`
- Assignee: `codex`
- Lane: `integrity`
- Impact: Agent-authored scratchpad text is rendered into the battle-state string (showdown_battle_bridge.py:~107 / state render) without escaping, so an agent can inject a '## Recent turns'-style header + forged 'T#: ...' lines that appear in its OWN rendered state and poison its decision loop. Self-harm only today (no cross-agent/rating impact) → P2; but it is the latent cross-surface injection risk if scratchpad ever reaches a replay/opponent view.
- Suggested fix: Escape/segregate scratchpad when rendering (fence it in a clearly-delimited block, strip markdown headers, or render structured fields instead of raw markdown). Add a render test asserting injected headers don't duplicate real section headers.
- Evidence: showdown_battle_bridge.py:~107 (scratchpad rendered into state); no escaping/validation/tests. adversarially confirmed (dogfood audit 2026-06-17)
- Recent comments: codex: Fixed: PR #190 MERGED — scratchpad fenced between --- BEGIN/END NOTES --- in render_state so forged section headers can't masquerade as server-authored state. Note: scratchpad was already capped at MAX_SCRATCHPAD_CHARS=1200 (the 'unbounded' half of the audit note didn't apply). render_state+bridge suites green.

### ADX-P2-003 - Preserve verified strengths while fixing gaps

- Priority: `P2`
- Status: `done`
- Assignee: `harness`
- Lane: `regression-guard`
- Impact: Known-good surfaces are easy to break while fixing adjacent defects.
- Suggested fix: Keep recompute ladder, anti-pay-to-rank property tests, `/whoami` redaction, team validation, and local log idempotence in the regression suite.
- Evidence: pass5, pass11, pass22, pass23, pass30

## Recent Events

| Time | Action | Actor | Card | Detail |
|---|---|---|---|---|
| 2026-06-17T22:31:10Z | add | adx-cli | ADX-ONLINE-001 | {} |
| 2026-06-17T22:31:10Z | add | adx-cli | ADX-ONLINE-002 | {} |
| 2026-06-17T22:32:11Z | add | bene-core | BENE-DOC-01 | {} |
| 2026-06-17T22:32:12Z | add | bene-core | BENE-DOC-02 | {} |
| 2026-06-17T22:32:12Z | add | bene-core | BENE-DOC-03 | {} |
| 2026-06-17T22:32:12Z | add | bene-core | BENE-DOC-04 | {} |
| 2026-06-17T22:32:12Z | add | bene-core | BENE-DOC-05 | {} |
| 2026-06-17T22:32:12Z | add | bene-core | BENE-DOC-06 | {} |
| 2026-06-17T22:32:12Z | add | bene-core | BENE-DOC-07 | {} |
| 2026-06-17T22:32:12Z | add | bene-core | BENE-DOC-08 | {} |
| 2026-06-17T22:32:12Z | add | bene-core | BENE-DOC-09 | {} |
| 2026-06-17T22:32:12Z | add | bene-core | BENE-DOC-10 | {} |

## Source Pattern

Adapted from Hermes Kanban's useful primitives: durable board slugs,
explicit statuses, priorities, assignees, comments/events, and per-profile
worker isolation. ADX keeps v1 file-backed so every fleet agent can use it
from the shared repo without a new daemon.
