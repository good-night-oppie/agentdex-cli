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
| LADDER-P1-incremental-cached | P1 | adx-core | ladder | Incremental ladder fold + cached /ladder (full recompute = boot/repair only); coordinate with ADX-P1-007 | events.py:195-237 recompute_ladder; called gateway.py:1355, 1144, 1182, mcp_surface.py:349, 1996. Same _finish lines as ADX-P1-007. |
| RECOVER-P1-interrupted-signal | P1 | adx-core | durability | Return a clear 409 'interrupted by restart' for begin-without-end battles after gateway restart (vs opaque 403) | self.sessions={} on boot gateway.py:572; boot replay rebuilds only names/memberships gateway.py:544-565; /choose 403 gateway.py:1663-1664. |
| ADX-P2-004 | P2 | adx-cli | fairness | Rated-battle quota not persisted — resets on gateway restart | consent.py:114-124/:159-182, gateway.py:536-558. adversarially confirmed (dogfood audit 2026-06-17) |
| ADX-P2-006 | P2 | harness | observability | Unbounded sessions/replays dicts — eventual OOM on long-running deploy | gateway.py:564/567 (init), :872/:1202/:1309 (insert), no eviction. adversarially confirmed (dogfood audit 2026-06-17) |
| DURABLE-P2-append-throughput-measure | P2 | harness | ops | Run ADR-0012 MUST-MEASURE #2: EventLog append throughput at ~100x turns/s (single fcntl-lock NDJSON) | events.py:72-97 single global fcntl lock + single fd; per-turn append hot path gateway.py:1702; loadtest covered sim only. |
| DURABLE-P2-ratings-pg-projection | P2 | adx-core | ladder | Add a ratings projection table to the PG mirror for multi-instance/replica reads (post-MVP) | eventsync.py mirrors raw arena_event_log only, no derived ratings view; ADR-0012:117-118. |
| SNAPSHOT-P2-sidecar-restore | P2 | adx-core | durability | Wire snapshot/restore ops into sidecar.mjs using engine State.serializeBattle (full in-flight crash recovery) | engine primitive exists (pokemon-showdown sim/state.js:79/99) but sidecar.mjs has no snapshot/restore op. |

### todo

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| ENROLL-P0-batch-mint | P0 | adx-core | onboarding | Batch-mint N consent tokens via one-shot script (emit register events) + distribute, bypassing self-serve confirm | consent.py:136 mint() works; gateway.py:639-649 ConsentClaims shape; _registered append-only gateway.py:637. |
| ENROLL-P0-delivery-channel | P0 | adx-core | onboarding | Wire a real confirmation-code delivery channel (env webhook/email, file fallback) into build_gateway() | __main__.py:128 hardcodes _file_inbox_notifier to container /tmp; __main__.py:7 docstring promises ARENA_OWNER_WEBHOOK but no code reads it; gateway.py:622 notify_owner is the only path. |
| LLM-P0-must-measure-3 | P0 | harness | infra | Run ADR-0012 MUST-MEASURE #3: LLM fan-out vs platform proxy rate/budget at 100 concurrent | ADR-0012:124, 126 names LLM tier first; loadtest doc:61-63 defers it; arena server makes $0 LLM calls (bots.py:1) so risk is 100 client agents. |
| ADMIT-P1-retry-after-and-per-owner-cap | P1 | adx-core | admission | Admission control: Retry-After on capacity 503 + per-owner concurrent-battle cap (anti-monopolization) | gateway.py:836-843 bare 503, grep retry-after=0; self.sessions keyed by battle_id only (gateway.py:572); BattleSession.claims_token_id gateway.py:388. |
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
| ENROLL-P1-docs-fix-false-webhook | P1 | adx-core | onboarding | Fix docs that promise a prod webhook/email delivery channel that does not exist | SKILL.md:185-193, bootstrap.sh:11-12, ENROLLMENT.md:23-24, arena_play.py:10 promise out-of-band delivery with no code. |
| ENROLL-P1-playtest-return-code | P1 | adx-core | onboarding | Env-gated playtest enroll path (ARENA_ENROLL_RETURN_CODE, off by default) that returns the code | gateway.py:599-626 stores pending_enrollments[code] but never returns it; arena_play.py:61-77 only works co-located. |
| OPS-P1-forward-scale-envvars | P1 | adx-cli | ops | Forward ADX_SIDECAR_POOL_SIZE + ADX_SIDECAR_MAX_OLD_SPACE_MB in `adx deploy` (only ARENA_* forwarded today) | cli.py:821 forwards only k.startswith('ARENA_'); __main__.py:179 reads ADX_SIDECAR_POOL_SIZE; sidecar.py:76 reads OLD_SPACE_MB. |
| OPS-P1-go-live-runbook | P1 | platform-instructor | ops | Write a go-live deploy/scale/rollback RUNBOOK (pre-flight envs, thresholds, rollback) | docs/runbooks/ holds only badge-admin.md + membership-admin.md; defaults POOL_SIZE=1, MAX_BATTLES=16, OLD_SPACE=96. |
| OPS-P1-healthz-readiness | P1 | adx-core | observability | Make /healthz a real readiness probe (sidecar alive + RSS) instead of static {ok:true} | gateway.py:1406/1418-1420 static _ARENA_HEALTH; Sidecar.rss_mb adx_showdown/sidecar.py:153; SidecarPool.rss_mb pool.py:108. |
| OPS-P1-metrics-stats | P1 | adx-core | observability | Add /metrics (or /debug/stats): RSS, active battles, 503 count (queue depth when queue lands) | no /metrics/counters (grep none); len(self.sessions) gateway.py:572 + rss_mb already exist. |
| RECOVER-P1-sidecar-respawn | P1 | adx-core | durability | Auto-respawn a dead sidecar in SidecarPool and evict its battle_id/_load routes | sidecar.py:117-126 fails pending futures with no respawn; pool.py:96-106 keeps dead sidecar in _owner/_load. |
| ROUTE-P1-dispute-pool | P1 | adx-core | routing | Route dispute replay op through SidecarPool (start <id>-dispute or special-case replay as battle-less) + regression test | gateway.py:1818 replay_input_log(battle_id=f'{id}-dispute') never start-ed; pool.py:95-98 raises 'not owned'. |
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

### blocked

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| ENROLL-P0-verify-signing-key | P0 | platform-instructor | onboarding | Verify the live deploy has a persistent ARENA_SIGNING_KEY_HEX (else all tokens die on sleep/wake/redeploy) | __main__.py:61-67 mints ephemeral key with warning-only when unset; consent.py:118-120 fail-closes only if BOTH empty. |
| INSTR-P0-bigger-instance | P0 | platform-instructor | platform | INSTRUCTOR: provision a multi-core instance bigger than the 256MB nano, scale-to-zero DISABLED | ADR-0012:117-118; deploy payload cli.py:844-849 has no instance-size/scale-to-zero field; quota 2/2 used. |
| INSTR-P1-free-quota-or-vps | P1 | platform-instructor | platform | INSTRUCTOR/OPERATOR: free the 2/2 quota (delete meta-vex, user green-lit) OR stand up external ~$5/mo VPS fallback | Quota 2/2 (meta-vex+agentdex), no self-serve DELETE (go/no-go:38-42); Dockerfile:60 shell-form CMD honoring $PORT. |

### review

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| BENE-DOC-02 | P0 | bene-core | blog-content | Blog post: WHY we build BENE — the harness behind the arena | CLAUDE.md, docs/README.md |
| ADX-P1-005 | P1 | codex | integrity | Collusion quarantine_reason leaks heuristic internals to the agent (D7) | gateway.py:1001-1045 (_check_collusion detailed strings), :1059-1062 (written to session.ended), :1116-1126 (event log). adversarially confirmed (dogfood audit 2026-06-17) |
| ADX-P2-001 | P2 | codex | agent-ux | Reduce starter and CLI footguns for visiting agents | pass14, pass15, pass16, pass29 |
| ADX-P2-002 | P2 | codex | gameplay | Make arena gameplay feedback more legible and less first-legal | pass2, pass3, pass4, pass6, pass7, pass8, pass12, pass13 |
| ADX-P2-005 | P2 | codex | integrity | Scratchpad rendered into battle state without escaping — self-injection of fake turn lines | showdown_battle_bridge.py:~107 (scratchpad rendered into state); no escaping/validation/tests. adversarially confirmed (dogfood audit 2026-06-17) |

### done

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| ADX-P2-003 | P2 | harness | regression-guard | Preserve verified strengths while fixing gaps | pass5, pass11, pass22, pass23, pass30 |

## Card Detail

### ENROLL-P0-batch-mint - Batch-mint N consent tokens via one-shot script (emit register events) + distribute, bypassing self-serve confirm

- Priority: `P0`
- Status: `todo`
- Assignee: `adx-core`
- Lane: `onboarding`
- Impact: Fastest path to real players today: hand pre-minted tokens to configured agents without the broken confirm flow.
- Suggested fix: One-shot script using live persistent ARENA_SIGNING_KEY_HEX; append register events so names survive restart.
- Evidence: consent.py:136 mint() works; gateway.py:639-649 ConsentClaims shape; _registered append-only gateway.py:637.

### ENROLL-P0-delivery-channel - Wire a real confirmation-code delivery channel (env webhook/email, file fallback) into build_gateway()

- Priority: `P0`
- Status: `todo`
- Assignee: `adx-core`
- Lane: `onboarding`
- Impact: Self-serve /enroll/confirm is unreachable for external users -> 0 tokens minted -> no players can onboard.
- Suggested fix: Add an env-selected notifier (ARENA_OWNER_WEBHOOK / email) in build_gateway, keep file-inbox as fallback; wire into notify_owner.
- Evidence: __main__.py:128 hardcodes _file_inbox_notifier to container /tmp; __main__.py:7 docstring promises ARENA_OWNER_WEBHOOK but no code reads it; gateway.py:622 notify_owner is the only path.

### LLM-P0-must-measure-3 - Run ADR-0012 MUST-MEASURE #3: LLM fan-out vs platform proxy rate/budget at 100 concurrent

- Priority: `P0`
- Status: `todo`
- Assignee: `harness`
- Lane: `infra`
- Impact: LLM proxy is the EXPECTED #1 bottleneck and is unmeasured -> go/no-go for 100 concurrent is unknown.
- Suggested fix: Probe /chat/completions concurrency + read /v1/usage/summary budget headroom on the shared AI_BUILDER_TOKEN proxy.
- Evidence: ADR-0012:124, 126 names LLM tier first; loadtest doc:61-63 defers it; arena server makes $0 LLM calls (bots.py:1) so risk is 100 client agents.

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

### ENROLL-P0-verify-signing-key - Verify the live deploy has a persistent ARENA_SIGNING_KEY_HEX (else all tokens die on sleep/wake/redeploy)

- Priority: `P0`
- Status: `blocked`
- Assignee: `platform-instructor`
- Lane: `onboarding`
- Impact: If the key is the ephemeral fallback, every consent token is invalidated on sleep/wake -> all players logged out mid-launch.
- Suggested fix: Confirm ARENA_SIGNING_KEY_HEX is set in the live deploy env_vars (or enroll->restart->whoami probe). Overlaps ADX-P2-004.
- Evidence: __main__.py:61-67 mints ephemeral key with warning-only when unset; consent.py:118-120 fail-closes only if BOTH empty.

### INSTR-P0-bigger-instance - INSTRUCTOR: provision a multi-core instance bigger than the 256MB nano, scale-to-zero DISABLED

- Priority: `P0`
- Status: `blocked`
- Assignee: `platform-instructor`
- Lane: `platform`
- Impact: THE hard blocker for true 100 concurrent: 256MB nano physically cannot host gateway + multi-sidecar pool.
- Suggested fix: Instructor provisions a larger always-on SKU (deploy API has no instance-size field) or confirm none exists -> external host.
- Evidence: ADR-0012:117-118; deploy payload cli.py:844-849 has no instance-size/scale-to-zero field; quota 2/2 used.

### BENE-DOC-02 - Blog post: WHY we build BENE — the harness behind the arena

- Priority: `P0`
- Status: `review`
- Assignee: `bene-core`
- Lane: `blog-content`
- Impact: Frames the whole site: BENE is the durable, auditable local-first multi-agent substrate that backs agentdex-cli (the arena). Gom-jabbar harness thesis.
- Suggested fix: Write blog/why-bene.md (EN). ABSTRACT ONLY: pseudo-code, NO agentdex-cli internals. zh routed to og.
- Evidence: CLAUDE.md, docs/README.md
- Recent comments: bene-core: Drafted + shipped as PR #14 (good-night-oppie/bene, branch content/blog-why-bene). Abstract-only, leak-scan clean. Source md only; render is bene's lane (BENE-DOC-01 scaffold + BENE-DOC-10 deploy).

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

### LADDER-P1-incremental-cached - Incremental ladder fold + cached /ladder (full recompute = boot/repair only); coordinate with ADX-P1-007

- Priority: `P1`
- Status: `triage`
- Assignee: `adx-core`
- Lane: `ladder`
- Impact: recompute_ladder is 3 full O(N) passes run synchronously on the single event loop per /ladder, twice per rated finish, whoami, badge.
- Suggested fix: Maintain a live in-memory ratings fold updated per battle-result; serve /ladder from cache; preserve Q5 anti-pay-to-rank parity.
- Evidence: events.py:195-237 recompute_ladder; called gateway.py:1355, 1144, 1182, mcp_surface.py:349, 1996. Same _finish lines as ADX-P1-007.

### RECOVER-P1-interrupted-signal - Return a clear 409 'interrupted by restart' for begin-without-end battles after gateway restart (vs opaque 403)

- Priority: `P1`
- Status: `triage`
- Assignee: `adx-core`
- Lane: `durability`
- Impact: After a restart, /choose on a dropped in-flight battle returns an opaque 403, confusing players mid-game.
- Suggested fix: Detect begin-without-end on boot and return 409 interrupted; full (seed,inputLog) resurrection needs a WAL schema change (backlog).
- Evidence: self.sessions={} on boot gateway.py:572; boot replay rebuilds only names/memberships gateway.py:544-565; /choose 403 gateway.py:1663-1664.

### ADMIT-P1-retry-after-and-per-owner-cap - Admission control: Retry-After on capacity 503 + per-owner concurrent-battle cap (anti-monopolization)

- Priority: `P1`
- Status: `todo`
- Assignee: `adx-core`
- Lane: `admission`
- Impact: Bare 503 gives clients no backoff signal; one owner can fill the whole pool and starve the other 99 users.
- Suggested fix: Add Retry-After header to the capacity 503; cap concurrent battles per claims_token_id. ADR-0012 sec7. (bounded queue deferred.)
- Evidence: gateway.py:836-843 bare 503, grep retry-after=0; self.sessions keyed by battle_id only (gateway.py:572); BattleSession.claims_token_id gateway.py:388.

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

### ENROLL-P1-docs-fix-false-webhook - Fix docs that promise a prod webhook/email delivery channel that does not exist

- Priority: `P1`
- Status: `todo`
- Assignee: `adx-core`
- Lane: `onboarding`
- Impact: SKILL.md/bootstrap.sh/ENROLLMENT.md dead-end users at pending_owner_confirmation with no real channel.
- Suggested fix: Correct the docs to the real (curated/batch-mint) onboarding path; ties to ENROLL-P0-delivery-channel. Overlaps ADX-P2-001 (done).
- Evidence: SKILL.md:185-193, bootstrap.sh:11-12, ENROLLMENT.md:23-24, arena_play.py:10 promise out-of-band delivery with no code.

### ENROLL-P1-playtest-return-code - Env-gated playtest enroll path (ARENA_ENROLL_RETURN_CODE, off by default) that returns the code

- Priority: `P1`
- Status: `todo`
- Assignee: `adx-core`
- Lane: `onboarding`
- Impact: Self-service onboarding alternative to batch-mint for a curated launch; default-off preserves A1 out-of-band invariant.
- Suggested fix: Return pending code only when ARENA_ENROLL_RETURN_CODE set; keep test_mcp_surface.py A1 green when unset.
- Evidence: gateway.py:599-626 stores pending_enrollments[code] but never returns it; arena_play.py:61-77 only works co-located.

### OPS-P1-forward-scale-envvars - Forward ADX_SIDECAR_POOL_SIZE + ADX_SIDECAR_MAX_OLD_SPACE_MB in `adx deploy` (only ARENA_* forwarded today)

- Priority: `P1`
- Status: `todo`
- Assignee: `adx-cli`
- Lane: `ops`
- Impact: The SidecarPool scale lever is silently dropped on deploy -> pool size can't be set on the bigger box without the --env-vars escape hatch.
- Suggested fix: Extend cli.py env-forward allowlist to ADX_SIDECAR_* (pays off on the multi-core box).
- Evidence: cli.py:821 forwards only k.startswith('ARENA_'); __main__.py:179 reads ADX_SIDECAR_POOL_SIZE; sidecar.py:76 reads OLD_SPACE_MB.

### OPS-P1-go-live-runbook - Write a go-live deploy/scale/rollback RUNBOOK (pre-flight envs, thresholds, rollback)

- Priority: `P1`
- Status: `todo`
- Assignee: `platform-instructor`
- Lane: `ops`
- Impact: Dangerous defaults + boot-crash envs + keep-alive + rollback are scattered across go-nogo + loadtest + ADR-0012.
- Suggested fix: Consolidate into docs/runbooks/arena-go-live.md incl the concrete bigger-instance env set (<=20 cap; inventory ~17).
- Evidence: docs/runbooks/ holds only badge-admin.md + membership-admin.md; defaults POOL_SIZE=1, MAX_BATTLES=16, OLD_SPACE=96.

### OPS-P1-healthz-readiness - Make /healthz a real readiness probe (sidecar alive + RSS) instead of static {ok:true}

- Priority: `P1`
- Status: `todo`
- Assignee: `adx-core`
- Lane: `observability`
- Impact: Platform never recycles a sick container -> an OOM/dead-sidecar spiral stays 'healthy' and keeps taking traffic.
- Suggested fix: Compute readiness from app.state.sidecar rss_mb + returncode (cheap one-ps-read/sidecar); fail when unhealthy.
- Evidence: gateway.py:1406/1418-1420 static _ARENA_HEALTH; Sidecar.rss_mb adx_showdown/sidecar.py:153; SidecarPool.rss_mb pool.py:108.

### OPS-P1-metrics-stats - Add /metrics (or /debug/stats): RSS, active battles, 503 count (queue depth when queue lands)

- Priority: `P1`
- Status: `todo`
- Assignee: `adx-core`
- Lane: `observability`
- Impact: Operator is blind between a healthy spike and an OOM spiral; the 503 path increments no counter.
- Suggested fix: Expose len(self.sessions) + rss_mb + a 503 counter via a small /metrics endpoint.
- Evidence: no /metrics/counters (grep none); len(self.sessions) gateway.py:572 + rss_mb already exist.

### RECOVER-P1-sidecar-respawn - Auto-respawn a dead sidecar in SidecarPool and evict its battle_id/_load routes

- Priority: `P1`
- Status: `todo`
- Assignee: `adx-core`
- Lane: `durability`
- Impact: One OOM permanently degrades a fraction of 100 users: dead sidecar stays in routing map, new battles routed to the corpse.
- Suggested fix: On Node death, respawn the pool member and purge its _owner/_load entries so _least_loaded stops routing to it.
- Evidence: sidecar.py:117-126 fails pending futures with no respawn; pool.py:96-106 keeps dead sidecar in _owner/_load.

### ROUTE-P1-dispute-pool - Route dispute replay op through SidecarPool (start <id>-dispute or special-case replay as battle-less) + regression test

- Priority: `P1`
- Status: `todo`
- Assignee: `adx-core`
- Lane: `routing`
- Impact: Disputes 500 the instant ADX_SIDECAR_POOL_SIZE>1 (the config 100 concurrent needs) -> broken integrity surface under scale.
- Suggested fix: Start the dispute battle on a pool member before replay, or special-case replay/import as battle-less; add test_pool replay test.
- Evidence: gateway.py:1818 replay_input_log(battle_id=f'{id}-dispute') never start-ed; pool.py:95-98 raises 'not owned'.

### ADX-ONLINE-001 - launch: watchable Human-vs-AI battle UX (line-protocol + sim/client/view + spectator/TUI/replay)

- Priority: `P1`
- Status: `running`
- Assignee: `adx-cli`
- Lane: `launch-ux`
- Impact: Getting agentdex ONLINE means a watchable arena — the whole pitch is spectating agents fight. Without the typed protocol + state-reducer + spectator/replay, the online arena is unwatchable (raw |move| rows, no fog-of-war, no replay).
- Suggested fix: Ship the digest 2026-06-17 P1->P3 backlog as tiny PRs. P1 protocol foundation MERGED today (PR #200 typed lineproto, PR #201 full protocol-log capture + (seed,inputLog) re-sim parity). Next: state-reducer (client.py), {reason,action} schema + |-reasoning|, then TUI/spectator/replay.
- Evidence: PR#200, PR#201, .supergoal-v3/ROADMAP.md
- Recent comments: adx-cli: Battle-UX foundation merged: PR #200 (typed line-protocol) + #201 (full protocol-log capture, byte-identical re-sim). Side quest: drained the SidecarPool review cascade (#197/#198/#203/#204) as 6 tiny PRs #202-#207 — fixes the pool capacity-leak + routing bugs relevant to ADX-ONLINE-002's 100-user push. Next: adx-client state-reducer, then {reason,action} + spectator/TUI/replay.

### INSTR-P1-free-quota-or-vps - INSTRUCTOR/OPERATOR: free the 2/2 quota (delete meta-vex, user green-lit) OR stand up external ~$5/mo VPS fallback

- Priority: `P1`
- Status: `blocked`
- Assignee: `platform-instructor`
- Lane: `platform`
- Impact: Contingency if no on-platform bigger SKU: need a service slot or an off-platform host for the scale instance.
- Suggested fix: Instructor DELETE meta-vex (green-lit 2026-06-11), or operator stands up VPS + DNS + ~17 env vars + secrets (Dockerfile is portable).
- Evidence: Quota 2/2 (meta-vex+agentdex), no self-serve DELETE (go/no-go:38-42); Dockerfile:60 shell-form CMD honoring $PORT.

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

### DURABLE-P2-append-throughput-measure - Run ADR-0012 MUST-MEASURE #2: EventLog append throughput at ~100x turns/s (single fcntl-lock NDJSON)

- Priority: `P2`
- Status: `triage`
- Assignee: `harness`
- Lane: `ops`
- Impact: Diagnostic: tells whether the single global append lock is a real ceiling at 100 concurrent.
- Suggested fix: Microbench events.py append under concurrent turns; WAL-SQLite migration is the to-build fix if it's a ceiling.
- Evidence: events.py:72-97 single global fcntl lock + single fd; per-turn append hot path gateway.py:1702; loadtest covered sim only.

### DURABLE-P2-ratings-pg-projection - Add a ratings projection table to the PG mirror for multi-instance/replica reads (post-MVP)

- Priority: `P2`
- Status: `triage`
- Assignee: `adx-core`
- Lane: `ladder`
- Impact: Only load-bearing once we go multi-core/horizontal; single-process today rebuilds from disk on boot.
- Suggested fix: Add a derived ratings view to eventsync's PG mirror for replica reads.
- Evidence: eventsync.py mirrors raw arena_event_log only, no derived ratings view; ADR-0012:117-118.

### SNAPSHOT-P2-sidecar-restore - Wire snapshot/restore ops into sidecar.mjs using engine State.serializeBattle (full in-flight crash recovery)

- Priority: `P2`
- Status: `triage`
- Assignee: `adx-core`
- Lane: `durability`
- Impact: Post-launch hardening: today a sidecar crash loses in-flight battles (load test shows crash isn't the demonstrated failure mode yet).
- Suggested fix: Add snapshot/restore ops to sidecar.mjs on top of the existing engine primitive + WAL replay rail.
- Evidence: engine primitive exists (pokemon-showdown sim/state.js:79/99) but sidecar.mjs has no snapshot/restore op.

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
| 2026-06-17T22:39:11Z | add | adx-core | LADDER-P1-incremental-cached | {} |
| 2026-06-17T22:39:11Z | add | adx-core | RECOVER-P1-interrupted-signal | {} |
| 2026-06-17T22:39:11Z | add | adx-core | SNAPSHOT-P2-sidecar-restore | {} |
| 2026-06-17T22:39:11Z | add | adx-core | DURABLE-P2-ratings-pg-projection | {} |
| 2026-06-17T22:39:11Z | add | adx-core | OPS-P1-forward-scale-envvars | {} |
| 2026-06-17T22:39:11Z | add | adx-core | LLM-P0-must-measure-3 | {} |
| 2026-06-17T22:39:11Z | add | adx-core | DURABLE-P2-append-throughput-measure | {} |
| 2026-06-17T22:39:11Z | add | adx-core | ENROLL-P0-verify-signing-key | {} |
| 2026-06-17T22:39:11Z | add | adx-core | INSTR-P0-bigger-instance | {} |
| 2026-06-17T22:39:11Z | add | adx-core | INSTR-P1-free-quota-or-vps | {} |
| 2026-06-17T22:39:11Z | add | adx-core | OPS-P1-go-live-runbook | {} |
| 2026-06-17T23:07:54Z | comment | adx-cli | ADX-ONLINE-001 | {} |

## Source Pattern

Adapted from Hermes Kanban's useful primitives: durable board slugs,
explicit statuses, priorities, assignees, comments/events, and per-profile
worker isolation. ADX keeps v1 file-backed so every fleet agent can use it
from the shared repo without a new daemon.
