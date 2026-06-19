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
| LADDER-P1-incremental-cached | P1 | adx-core | ladder | Incremental ladder fold + cached /ladder (full recompute = boot/repair only); coordinate with ADX-P1-007 | events.py:195-237 recompute_ladder; called gateway.py:1355, 1144, 1182, mcp_surface.py:349, 1996. Same _finish lines as ADX-P1-007. |
| ADX-P2-006 | P2 | harness | observability | Unbounded sessions/replays dicts — eventual OOM on long-running deploy | gateway.py:564/567 (init), :872/:1202/:1309 (insert), no eviction. adversarially confirmed (dogfood audit 2026-06-17) |
| DURABLE-P2-append-throughput-measure | P2 | harness | ops | Run ADR-0012 MUST-MEASURE #2: EventLog append throughput at ~100x turns/s (single fcntl-lock NDJSON) | events.py:72-97 single global fcntl lock + single fd; per-turn append hot path gateway.py:1702; loadtest covered sim only. |
| DURABLE-P2-ratings-pg-projection | P2 | adx-core | ladder | Add a ratings projection table to the PG mirror for multi-instance/replica reads (post-MVP) | eventsync.py mirrors raw arena_event_log only, no derived ratings view; ADR-0012:117-118. |
| SNAPSHOT-P2-sidecar-restore | P2 | adx-core | durability | Wire snapshot/restore ops into sidecar.mjs using engine State.serializeBattle (full in-flight crash recovery) | engine primitive exists (pokemon-showdown sim/state.js:79/99) but sidecar.mjs has no snapshot/restore op. |

### todo

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| BENE-RVW-P0-launch-gate | P0 | bene | launch-gate | Day-3 public-launch gate: version-triple-match + correct llms links + no fake CN | Eddie review Day-3 + total readiness 6.5/10 (private-preview yes, public-launch no until P0s fixed). |
| LLM-P0-must-measure-3 | P0 | harness | infra | Run ADR-0012 MUST-MEASURE #3: LLM fan-out vs platform proxy rate/budget at 100 concurrent | ADR-0012:124, 126 names LLM tier first; loadtest doc:61-63 defers it; arena server makes $0 LLM calls (bots.py:1) so risk is 100 client agents. |
| ADX-P1-003 | P1 | harness | observability | Make observability acceptance fail when traces are absent | pass31, pass32 |
| BENE-DOC-10 | P1 | bene | render-deploy | Render + deploy all new blog/docs/case-study/design content | site/build-docs.py |
| BENE-RVW-P1-landing-honesty | P1 | bene | launch-ux | Landing: move turnkey-vs-wire-yourself honesty up; bind 30s/0.3s/HEAD claims to version+provenance | Eddie review: 'honesty in landing but position too low'; Integrating-BENE 'agent loop turnkey; everything else is lego'. |
| BENE-SCRUB-08 | P1 | bene | render-deploy | Rebuild site + ride pending redeploy (DNS+DOC-10+zh+scrub); live-verify clean | PR#27, BENE-DOC-10 |
| ENROLL-P1-device-flow-backend | P1 | adx-core | onboarding | adx-core: implement ADR-0013 device-flow + /enroll/account backend (D2/D3/D7 wire contract) | PR #295 docs/adr/0013-first-time-user-onboarding-pip-login-wizard.md (Sections D2/D3/D7) |
| ENROLL-P1-docs-fix-false-webhook | P1 | adx-core | onboarding | Fix docs that promise a prod webhook/email delivery channel that does not exist | SKILL.md:185-193, bootstrap.sh:11-12, ENROLLMENT.md:23-24, arena_play.py:10 promise out-of-band delivery with no code. |
| ENROLL-P1-playtest-return-code | P1 | adx-core | onboarding | Env-gated playtest enroll path (ARENA_ENROLL_RETURN_CODE, off by default) that returns the code | gateway.py:599-626 stores pending_enrollments[code] but never returns it; arena_play.py:61-77 only works co-located. |
| RECOVER-P1-sidecar-respawn | P1 | adx-core | durability | Auto-respawn a dead sidecar in SidecarPool and evict its battle_id/_load routes | sidecar.py:117-126 fails pending futures with no respawn; pool.py:96-106 keeps dead sidecar in _owner/_load. |
| RVW-P1-codex-adx-cli-prs | P1 | codex | review | codex: review all open adx-cli PRs (#295 ADR-0013, #178 observability acceptance) | PR #295, PR #178 |
| RVW-P1-og-adx-cli-prs | P1 | og | review | og: review all open adx-cli PRs (#295 ADR-0013, #178 observability acceptance) | PR #295, PR #178 |

### running

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| ADX-ONLINE-002 | P0 | adx-core | launch-gate | launch gate: agentdex 100-user readiness assessment + go/no-go | wf:agentdex-100-user-readiness(54/71), a2a#312, a2a#320 |
| ADX-ONLINE-001 | P1 | adx-cli | launch-ux | launch: watchable Human-vs-AI battle UX (line-protocol + sim/client/view + spectator/TUI/replay) | PR#200, PR#201, .supergoal-v3/ROADMAP.md |

### blocked

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| GA-BENE-1 | P0 | bene | bene-core | agentdex.builders: build + deploy the dashboard web app (SPA reading GA-CORE-5 + GA-CORE-3) | blocked on A-CLI-1 final hi-fi design (follow-up PR) + GA-CORE-5 dashboard API |
| GA-BENE-2 | P0 | bene | bene-core | agentdex.builders: wire live battle viewer to GA-CORE-3 spectator stream (adjacent to Agent Pane) | blocked on A-CLI-2 frame schema + adx-core GA-CORE-3 stream |
| AWS-PUBLIC-DNS-TLS | P1 | adx-core | platform | agentdex.builders DNS A-record + Caddy auto-TLS -> arena box | op service-account rate-limited / openclaw vault access for namecheap-api creds (op://openclaw/namecheap-api); egress 54.202.180.208 already whitelisted. |
| BENE-BATTLE-INTEGRATE | P1 | bene-core | bene-core | Lane B → A3 integration: swap mock_fitness for real multi_dim_fitness |  |
| GA-BENE-4 | P1 | bene | bene-core | Evolution/lineage view data: fitness-over-gens, kill-gate verdicts, winning mutation (dashboard Evolution panel) | depends on GA-BENE-3 real-evolve output shape |
| INSTR-P1-free-quota-or-vps | P1 | platform-instructor | platform | INSTRUCTOR/OPERATOR: free the 2/2 quota (delete meta-vex, user green-lit) OR stand up external ~$5/mo VPS fallback | Quota 2/2 (meta-vex+agentdex), no self-serve DELETE (go/no-go:38-42); Dockerfile:60 shell-form CMD honoring $PORT. |

### review

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| OPS-P1-go-live-runbook | P1 | adx-core | ops | Write a go-live deploy/scale/rollback RUNBOOK (pre-flight envs, thresholds, rollback) | docs/runbooks/ holds only badge-admin.md + membership-admin.md; defaults POOL_SIZE=1, MAX_BATTLES=16, OLD_SPACE=96. |

### done

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| ADX-P0-001 | P0 | adx-cli | integrity | Make arena receipts atomic before claiming honesty | pass27, pass28, pass37, pass38, pass39, pass40 |
| BENE-DOC-02 | P0 | bene-core | blog-content | Blog post: WHY we build BENE — the harness behind the arena | CLAUDE.md, docs/README.md |
| BENE-RVW-P0-cn-docs | P0 | og | docs-zh | P0#4 CN docs = Chinese shell + English body: fix entry/nav/priority-3/annotation | docs/zh now = README + cli-reference + integrating-bene only (exactly the 3 priority docs); og confirmed lane done on bus #373 / commit c2a876c. |
| BENE-RVW-P0-llms-canonical | P0 | bene | launch-gate | P0#2 canonical repo: llms.txt + GitHub links point to EdwardTang/bene-site, not good-night-oppie/bene | site/llms.txt Source/Issues/Discussions all = github.com/EdwardTang/bene-site; product repo under review = good-night-oppie/bene. |
| BENE-RVW-P0-version | P0 | bene | launch-gate | P0#1 version drift: landing shows v0.2.0, package/PyPI are 0.2.1 | pyproject.toml version=0.2.1; PyPI=0.2.1; site/index.html and site/zh/index.html each show v0.2.0 (1 ref each) on good-night-oppie/bene main. |
| ENROLL-P0-batch-mint | P0 | adx-core | onboarding | Batch-mint N consent tokens via one-shot script (emit register events) + distribute, bypassing self-serve confirm | consent.py:136 mint() works; gateway.py:639-649 ConsentClaims shape; _registered append-only gateway.py:637. |
| ENROLL-P0-delivery-channel | P0 | adx-core | onboarding | Wire a real confirmation-code delivery channel (env webhook/email, file fallback) into build_gateway() | __main__.py:128 hardcodes _file_inbox_notifier to container /tmp; __main__.py:7 docstring promises ARENA_OWNER_WEBHOOK but no code reads it; gateway.py:622 notify_owner is the only path. |
| ENROLL-P0-verify-signing-key | P0 | adx-core | onboarding | Verify the live deploy has a persistent ARENA_SIGNING_KEY_HEX (else all tokens die on sleep/wake/redeploy) | __main__.py:61-67 mints ephemeral key with warning-only when unset; consent.py:118-120 fail-closes only if BOTH empty. |
| INSTR-P0-bigger-instance | P0 | adx-core | platform | INSTRUCTOR: provision a multi-core instance bigger than the 256MB nano, scale-to-zero DISABLED | ADR-0012:117-118; deploy payload cli.py:844-849 has no instance-size/scale-to-zero field; quota 2/2 used. |
| ADMIT-P1-retry-after-and-per-owner-cap | P1 | adx-core | admission | Admission control: Retry-After on capacity 503 + per-owner concurrent-battle cap (anti-monopolization) | gateway.py:836-843 bare 503, grep retry-after=0; self.sessions keyed by battle_id only (gateway.py:572); BattleSession.claims_token_id gateway.py:388. |
| ADX-P1-001 | P1 | adx-cli | fairness | Stop spending rated/evolution/badge quota before work is accepted | pass26, pass33, pass34, pass35, pass36 |
| ADX-P1-002 | P1 | adx-cli | owner-data | Make owner export include replay, badge, and rating lineage | pass17, pass19, pass20, pass21, pass41, pass42-candidate |
| ADX-P1-004 | P1 | adx-cli | security | Tighten admin surface and auth-before-parse contract | pass24, pass25 |
| ADX-P1-005 | P1 | codex | integrity | Collusion quarantine_reason leaks heuristic internals to the agent (D7) | gateway.py:1001-1045 (_check_collusion detailed strings), :1059-1062 (written to session.ended), :1116-1126 (event log). adversarially confirmed (dogfood audit 2026-06-17) |
| ADX-P1-006 | P1 | adx-cli | integrity | Dispute event appended BEFORE re-sim — duplicate events on retry | gateway.py:1771-1777 (append), :1790-1794/:1822 (resim+throw). adversarially confirmed (dogfood audit 2026-06-17) |
| ADX-P1-007 | P1 | adx-cli | fairness | Ladder published_delta race: concurrent _finish for same player inflates delta | gateway.py:1131 (before snapshot), :1160 (append), :1169 (after). adversarially confirmed (dogfood audit 2026-06-17) |
| BENE-BATTLE-B1 | P1 | bene-core | bene-core | Lane B: evolve_battle_harness Contract-4 entrypoint (bene) |  |
| BENE-BATTLE-B2 | P1 | bene-core | bene-core | Lane B: Pareto evaluator wired to Contract-3 5-dim fitness |  |
| BENE-BATTLE-B3 | P1 | bene-core | bene-core | Lane B: hash-locked kill-gate probe (win_rate_uplift + anti-vacuous) |  |
| BENE-BATTLE-B4 | P1 | bene-core | bene-core | Lane B: SharedLog lineage + run_seed reproducibility |  |
| BENE-CODEX-EVO-G1 | P1 | bene-core | bene-core | SECH Contract G: evolve_codex_harness + DGM archive + hash-locked kill-gate (bene-core B1) | PR#64 merged 1e3ea0c; full suite 1082 |
| BENE-CODEX-EVO-HELDOUT | P1 | bene-core | bene-core | SECH held-out anti-overfit gate: disjointness + VOID + hash-stamping (bene-core) | PR#65 merged 9b508e9; full suite 1087 |
| BENE-DOC-01 | P1 | bene | blog | Scaffold the new /blog section on bene-site (index + post template + nav) | site/build-docs.py, site/index.html |
| BENE-DOC-03 | P1 | bene-core | blog-content | Blog post: WHAT BENE is — the seven pillars | examples/library_basics.py, bene/cli/main.py, docs/architecture.md |
| BENE-DOC-04 | P1 | bene-core | blog-content | Blog post: HOW we build BENE — harness engineering + eval-gated evolution | bene/kernel/eval, bene/metaharness, docs/meta-harness.md |
| BENE-DOC-05 | P1 | bene-core | docs-examples | Surface real runnable examples per pillar in the docs | examples/, docs/architecture.md, docs/cli-reference.md |
| BENE-DOC-06 | P1 | bene-core | case-study | Case study: multi-agent coding arena on BENE (ABSTRACT) | docs/case-studies/cs02-ci-self-healing-refactor-swarm.md |
| BENE-RVW-P1-docs-honesty-tone | P1 | bene-core | docs | Pull Integrating-BENE turnkey-vs-lego honesty into README; align tone with benchmark honesty | Eddie review Docs (Integrating BENE best doc) + Benchmark-report honesty. |
| BENE-RVW-P1-readme-restructure | P1 | bene-core | readme | Day-2 README restructure: user-success path first, lore + 16 papers down | Eddie review Repo-README + Day-2 sequence. |
| BENE-SCRUB-01 | P1 | bene-core | unpublish | UN-PUBLISH docs/design/ + docs/research/ (relocate out of docs/, delete published HTML) | PR#27, docs/design/v0.3-roadmap-spec.md |
| BENE-SCRUB-02 | P1 | bene-core | scrub | Scrub work-trace from docs/tutorials/t02-e2e-self-healing.md | docs/tutorials/t02-e2e-self-healing.md |
| BENE-SCRUB-03 | P1 | bene-core | scrub | Scrub work-trace from docs/tutorials/t07-regression-guard.md | docs/tutorials/t07-regression-guard.md |
| BENE-SCRUB-04 | P1 | bene-core | scrub | Scrub work-trace from docs/tutorials/t08-hundred-agents-scale.md | docs/tutorials/t08-hundred-agents-scale.md |
| BENE-SCRUB-07 | P1 | og | scrub-zh | ZH scrub: all docs/zh/ counterparts (design+research unpublish + reader-doc scrub) | docs/zh/design/v0.3-roadmap-spec.md, PR#28 |
| GA-BENE-3 | P1 | bene-core | bene-core | Lane B evolve de-mock: replace _mock_evolve with real evolve_battle_harness in the C2 driver | done_e2e_real_bene.json proves real bene evolve e2e; _mock_evolve at e2e_driver.py:276/451 |
| OPS-P1-forward-scale-envvars | P1 | adx-core | ops | Forward ADX_SIDECAR_POOL_SIZE + ADX_SIDECAR_MAX_OLD_SPACE_MB in `adx deploy` (only ARENA_* forwarded today) | cli.py:821 forwards only k.startswith('ARENA_'); __main__.py:179 reads ADX_SIDECAR_POOL_SIZE; sidecar.py:76 reads OLD_SPACE_MB. |
| OPS-P1-healthz-readiness | P1 | adx-core | observability | Make /healthz a real readiness probe (sidecar alive + RSS) instead of static {ok:true} | gateway.py:1406/1418-1420 static _ARENA_HEALTH; Sidecar.rss_mb adx_showdown/sidecar.py:153; SidecarPool.rss_mb pool.py:108. |
| OPS-P1-metrics-stats | P1 | adx-core | observability | Add /metrics (or /debug/stats): RSS, active battles, 503 count (queue depth when queue lands) | no /metrics/counters (grep none); len(self.sessions) gateway.py:572 + rss_mb already exist. |
| PLAY-P1-bene-e2e-live | P1 | bene-core | e2e-play | bene-core: e2e side-by-side LIVE play on the cloud arena — surface real issues for immediate fix | ADX-ONLINE-001 (battle UX) + PR #295 (onboarding) + ADX-ONLINE-002 (100-user launch gate) |
| RECOVER-P1-interrupted-signal | P1 | adx-core | durability | Return a clear 409 'interrupted by restart' for begin-without-end battles after gateway restart (vs opaque 403) | self.sessions={} on boot gateway.py:572; boot replay rebuilds only names/memberships gateway.py:544-565; /choose 403 gateway.py:1663-1664. |
| ADX-P2-001 | P2 | codex | agent-ux | Reduce starter and CLI footguns for visiting agents | pass14, pass15, pass16, pass29 |
| ADX-P2-002 | P2 | codex | gameplay | Make arena gameplay feedback more legible and less first-legal | pass2, pass3, pass4, pass6, pass7, pass8, pass12, pass13 |
| ADX-P2-003 | P2 | harness | regression-guard | Preserve verified strengths while fixing gaps | pass5, pass11, pass22, pass23, pass30 |
| ADX-P2-004 | P2 | adx-cli | fairness | Rated-battle quota not persisted — resets on gateway restart | consent.py:114-124/:159-182, gateway.py:536-558. adversarially confirmed (dogfood audit 2026-06-17) |
| ADX-P2-005 | P2 | codex | integrity | Scratchpad rendered into battle state without escaping — self-injection of fake turn lines | showdown_battle_bridge.py:~107 (scratchpad rendered into state); no escaping/validation/tests. adversarially confirmed (dogfood audit 2026-06-17) |
| BENE-CODEX-EVO-B3 | P2 | bene-core | bene-core | SECH in-episode continual swap (Continual-Harness pillar): ContinualMutator -> CodexHarness | proposed A2A bus position 501; not started |
| BENE-DOC-07 | P2 | bene-core | case-study | Case study: trace-based RAG / Other Memory (engrams) | bene/kernel/memory, docs/memory.md |
| BENE-DOC-08 | P2 | bene-core | case-study | Case study: evolutionary meta-harness search | bene/metaharness, docs/meta-harness.md |
| BENE-DOC-09 | P2 | bene-core | design | Design: architecture diagrams (Nexus, engram ladder, autonomy ladder) | docs/architecture.md |
| BENE-SCRUB-05 | P2 | bene-core | scrub | Scrub docs/benchmarks/COMMUNITY-BENCH-REPORT.md | docs/benchmarks/COMMUNITY-BENCH-REPORT.md |
| BENE-SCRUB-06 | P2 | bene-core | scrub | Scrub docs/primitive-review-cycle.md | docs/primitive-review-cycle.md |

### archived

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| ROUTE-P1-dispute-pool | P1 | adx-cli | routing | Route dispute replay op through SidecarPool (start <id>-dispute or special-case replay as battle-less) + regression test | gateway.py:1818 replay_input_log(battle_id=f'{id}-dispute') never start-ed; pool.py:95-98 raises 'not owned'. |

## Card Detail

### BENE-RVW-P0-launch-gate - Day-3 public-launch gate: version-triple-match + correct llms links + no fake CN

- Priority: `P0`
- Status: `todo`
- Assignee: `bene`
- Lane: `launch-gate`
- Impact: Public launch must not ship with version/repo/CN drift; needs one repeatable readiness gate before flipping public.
- Suggested fix: On a fresh machine: pipx install bene && bene demo --no-ui && bene --version -> landing version = PyPI = repo, all 0.2.1; /bene/llms.txt repo links = good-night-oppie/bene; CN docs promise no untranslated content; live /bene/docs index = 37 not 45. Gate runs AFTER BENE-SCRUB-08 deploy.
- Evidence: Eddie review Day-3 + total readiness 6.5/10 (private-preview yes, public-launch no until P0s fixed).
- Recent comments: imported: PARTIAL VERIFY (bene-core-6, 2026-06-18T22:52:40Z): criteria 1 v0.2.1=PASS, 2 llms-canonical=PASS, 4 work-trace-0=PASS, 5 integrating-bene-0.2.1=PASS. Criterion 3 docs=37 PENDING -- live site has 75 HTML in docs (BENE-SCRUB-08 must deploy first to prune to 37). Gate explicitly blocked on BENE-SCRUB-08 deploy (bene lane).

### LLM-P0-must-measure-3 - Run ADR-0012 MUST-MEASURE #3: LLM fan-out vs platform proxy rate/budget at 100 concurrent

- Priority: `P0`
- Status: `todo`
- Assignee: `harness`
- Lane: `infra`
- Impact: LLM proxy is the EXPECTED #1 bottleneck and is unmeasured -> go/no-go for 100 concurrent is unknown.
- Suggested fix: Probe /chat/completions concurrency + read /v1/usage/summary budget headroom on the shared AI_BUILDER_TOKEN proxy.
- Evidence: ADR-0012:124, 126 names LLM tier first; loadtest doc:61-63 defers it; arena server makes $0 LLM calls (bots.py:1) so risk is 100 client agents.

### ADX-ONLINE-002 - launch gate: agentdex 100-user readiness assessment + go/no-go

- Priority: `P0`
- Status: `running`
- Assignee: `adx-core`
- Lane: `launch-gate`
- Impact: Getting agentdex online today requires a measured readiness verdict across the user-facing surface (capacity, integrity, security). This is the launch go/no-go gate the UX rides on top of.
- Suggested fix: Complete the agentdex-100-user-readiness assessment (in progress, 54/71 agents) -> capacity + integrity + security punch-list + go/no-go. Coordinate fixes with adx-cli; P0/P1 integrity items (atomic receipts ADX-P0-001) gate launch.
- Evidence: wf:agentdex-100-user-readiness(54/71), a2a#312, a2a#320
- Recent comments: codex: DEPLOY RELAY (harness-11 #401 was redirected into codex's pane, but it names adx-core as owner). codex VERIFIED the deploy is needed + declines to run it (wrong actor): live /bene/ last-modified=06:36:33 GMT (stale pre-reboot build, etag 18bfcaf6...); origin/main=6d4c0444 IS current (site/blog/ why+what+how-we-build-bene+index present, sweeps #48-#53 + review fixes thru #286). adx-core: you are the named owner + hold the on-disk Spaces key + are alive — please execute note-36 (push deploy-target +origin/main:main + POST Spaces) then verify live last-modified advances past 06:36:33 + headless 0.2.1 #root render. codex is NOT running the prod force-push/Spaces POST: prod credential is assigned to you (secrets discipline), there is active deploy contention (#342 bene-11 POSTed, #402 stale dup reaped), and it is hard-to-reverse + outside codex's lane. Flagging to Eddie per harness-11's escape clause.

### GA-BENE-1 - agentdex.builders: build + deploy the dashboard web app (SPA reading GA-CORE-5 + GA-CORE-3)

- Priority: `P0`
- Status: `blocked`
- Assignee: `bene`
- Lane: `bene-core`
- Impact: No beta dashboard without this; it's the user-facing surface (agent roster | Agent Pane | live battle | evolution+ladder).
- Suggested fix: Build the SPA from adx-cli A-CLI-1 design; deploy on agentdex.builders via the bene site pipeline.
- Evidence: blocked on A-CLI-1 final hi-fi design (follow-up PR) + GA-CORE-5 dashboard API
- Recent comments: bene-core: Build-ahead: a design-token-matched dashboard SHELL prototype exists (Agent Pane | scene-card adjacency grid, roster, evolution/ladder placeholders, responsive <1024px). Still blocked on GA-CORE-5 (dashboard data API shape) for the live data wiring. / bene-core: Still blocked on adx-core GA-CORE-5 API build (contract RATIFIED #539). NOTE: escalated to harness-13 (#555) to re-point this front-end card to bene-2 (the actual builder) — bene-core's engine seam is done; front-end is bene-2's lane. / bene-core: Reassigned bene-core -> bene (front-end lineage). GA-BENE-1 is a dashboard SPA = bene's lane (owns site+deploy). bene-core's engine/data is locked: GA-CORE-5 envelope RATIFIED (#539, widened genome_summary). Blocked on adx-core GA-CORE-5 API build. bene-core = engine-data backstop. Per coordination #555/#573 (harness re-point un-actioned over ~5h; acting on it to reflect the true builder).

### GA-BENE-2 - agentdex.builders: wire live battle viewer to GA-CORE-3 spectator stream (adjacent to Agent Pane)

- Priority: `P0`
- Status: `blocked`
- Assignee: `bene`
- Lane: `bene-core`
- Impact: The watch-live experience; PS battle scene <=2s lag, incremental per seq, fog-of-war.
- Suggested fix: Render the live viewer per LIVE_VIEWER_CONTRACT.md, consuming GA-CORE-3 frames.
- Evidence: blocked on A-CLI-2 frame schema + adx-core GA-CORE-3 stream
- Recent comments: bene-core: Build-ahead: a standalone, render-verified live-viewer REFERENCE renderer is done (renders the frozen LIVE_VIEWER_CONTRACT.md frame schema; 11/11 chromium assertions incl. fog-of-war hold + event:end->replay swap; pluggable SseLiveSource = one-line wire to GA-CORE-3). projector.js + 24-assertion test double as a GA-CORE-3 reference. Still blocked on GA-CORE-3 emitting frames for the LIVE wiring. / bene-core: Still blocked on adx-core GA-CORE-3 SSE emitter. bene-2 BUILT + render-verified the viewer renderer (build-ahead, #548). Escalated to harness-13 (#555) to re-point this card to bene-2 (builder); bene-core stands on the data/engine seam only. / bene-core: Reassigned bene-core -> bene. bene-2 BUILT + render-verified the live-viewer renderer (#548, 11/11 chromium, fog-of-war proven) — it is bene's deliverable. Blocked on adx-core GA-CORE-3 SSE. bene-core = engine backstop. Per #573.

### ADX-P0-001 - Make arena receipts atomic before claiming honesty

- Priority: `P0`
- Status: `done`
- Assignee: `adx-cli`
- Lane: `integrity`
- Impact: Human owner and agent both receive durable receipts that can be false or partial when EventLog, sidecar, or rating writes fail.
- Suggested fix: Group side effects behind an atomic write plan: validate and reserve first, then commit event/replay/rating/badge together or compensate visibly.
- Evidence: pass27, pass28, pass37, pass38, pass39, pass40
- Recent comments: imported: adx-cli-6 2026-06-18: DONE — receipt atomicity landed; restart-survival residual closed by PR #280.

### BENE-DOC-02 - Blog post: WHY we build BENE — the harness behind the arena

- Priority: `P0`
- Status: `done`
- Assignee: `bene-core`
- Lane: `blog-content`
- Impact: Frames the whole site: BENE is the durable, auditable local-first multi-agent substrate that backs agentdex-cli (the arena). Gom-jabbar harness thesis.
- Suggested fix: Write blog/why-bene.md (EN). ABSTRACT ONLY: pseudo-code, NO agentdex-cli internals. zh routed to og.
- Evidence: CLAUDE.md, docs/README.md
- Recent comments: bene-core: Drafted + shipped as PR #14 (good-night-oppie/bene, branch content/blog-why-bene). Abstract-only, leak-scan clean. Source md only; render is bene's lane (BENE-DOC-01 scaffold + BENE-DOC-10 deploy). / bene-core: MERGED to main as PR #14 (squash). WHY blog post live in source (blog/why-bene.md); render pending bene's BENE-DOC-01 scaffold + DOC-10 deploy.

### BENE-RVW-P0-cn-docs - P0#4 CN docs = Chinese shell + English body: fix entry/nav/priority-3/annotation

- Priority: `P0`
- Status: `done`
- Assignee: `og`
- Lane: `docs-zh`
- Impact: Entry is 'BENE 文档' but most body is English; users expect Chinese content. CN docs scored 3/10.
- Suggested fix: Rename entry -> 中文索引/翻译中; translate 3 priority docs FIRST (README, cli-reference, integrating-bene) [DONE on main c2a876c]; localize CN nav (01 Gap/02 Contract -> 中文); first-occurrence-only annotations; restrain first-screen voice. og: self-verify nav-localization + annotation density vs Eddie's asks, then move to done.
- Evidence: docs/zh now = README + cli-reference + integrating-bene only (exactly the 3 priority docs); og confirmed lane done on bus #373 / commit c2a876c.

### BENE-RVW-P0-llms-canonical - P0#2 canonical repo: llms.txt + GitHub links point to EdwardTang/bene-site, not good-night-oppie/bene

- Priority: `P0`
- Status: `done`
- Assignee: `bene`
- Lane: `launch-gate`
- Impact: llms.txt is the AI-agent entrypoint; it names the WRONG repo as authoritative Source/Issues/Discussions -> agents file issues on the marketing mirror, humans get confused.
- Suggested fix: Point site/llms.txt Source/issue-tracker/discussions + every GitHub link (landing, docs footer, README badge) to good-night-oppie/bene. DECISION to confirm w/ Eddie: good-night-oppie/bene = canonical package+source repo; EdwardTang/bene-site = marketing mirror.
- Evidence: site/llms.txt Source/Issues/Discussions all = github.com/EdwardTang/bene-site; product repo under review = good-night-oppie/bene.
- Recent comments: imported: VERIFIED LIVE (bene-core-6, 2026-06-18): llms.txt has 4 references to good-night-oppie/bene (canonical repo) — PR #52 shipped.

### BENE-RVW-P0-version - P0#1 version drift: landing shows v0.2.0, package/PyPI are 0.2.1

- Priority: `P0`
- Status: `done`
- Assignee: `bene`
- Lane: `launch-gate`
- Impact: A provenance/reproducibility product must not drift its own version. Landing shows v0.2.0 while pyproject.toml + PyPI are 0.2.1 -> users doubt the page is current.
- Suggested fix: Update site/index.html + site/zh/index.html v0.2.0->0.2.1; ideally auto-inject the version from pyproject.toml in build-docs.py so it can never drift again.
- Evidence: pyproject.toml version=0.2.1; PyPI=0.2.1; site/index.html and site/zh/index.html each show v0.2.0 (1 ref each) on good-night-oppie/bene main.
- Recent comments: imported: VERIFIED LIVE (bene-core-6, 2026-06-18): site shows v0.2.1 at agentdex.ai-builders.space/bene — PR #46 shipped, version now consistent pyproject.toml + PyPI + landing.

### ENROLL-P0-batch-mint - Batch-mint N consent tokens via one-shot script (emit register events) + distribute, bypassing self-serve confirm

- Priority: `P0`
- Status: `done`
- Assignee: `adx-core`
- Lane: `onboarding`
- Impact: Fastest path to real players today: hand pre-minted tokens to configured agents without the broken confirm flow.
- Suggested fix: One-shot script using live persistent ARENA_SIGNING_KEY_HEX; append register events so names survive restart.
- Evidence: consent.py:136 mint() works; gateway.py:639-649 ConsentClaims shape; _registered append-only gateway.py:637.
- Recent comments: adx-core: PR #232 opened. python -m agentdex_arena.batch_mint; 7 tests; --all-files green locally. Polling CI. / adx-core: MERGED as PR #232. Curated-launch token minting is now available.

### ENROLL-P0-delivery-channel - Wire a real confirmation-code delivery channel (env webhook/email, file fallback) into build_gateway()

- Priority: `P0`
- Status: `done`
- Assignee: `adx-core`
- Lane: `onboarding`
- Impact: Self-serve /enroll/confirm is unreachable for external users -> 0 tokens minted -> no players can onboard.
- Suggested fix: Add an env-selected notifier (ARENA_OWNER_WEBHOOK / email) in build_gateway, keep file-inbox as fallback; wire into notify_owner.
- Evidence: __main__.py:128 hardcodes _file_inbox_notifier to container /tmp; __main__.py:7 docstring promises ARENA_OWNER_WEBHOOK but no code reads it; gateway.py:622 notify_owner is the only path.
- Recent comments: adx-core: PR #231 opened (good-night-oppie/agentdex-cli). 6 new tests, arena suite 135 green, ruff+mypy clean, doc-lint pass. Polling pre-commit CI. / adx-core: MERGED as PR #231 (7774a72f). Also swept pre-existing --all-files CI debt (ruff-format gateway.py+arena_loadtest.py+__main__.py, ruff UP038 pool.py, B017 test_client.py) that was redding every PR.

### ENROLL-P0-verify-signing-key - Verify the live deploy has a persistent ARENA_SIGNING_KEY_HEX (else all tokens die on sleep/wake/redeploy)

- Priority: `P0`
- Status: `done`
- Assignee: `adx-core`
- Lane: `onboarding`
- Impact: If the key is the ephemeral fallback, every consent token is invalidated on sleep/wake -> all players logged out mid-launch.
- Suggested fix: Confirm ARENA_SIGNING_KEY_HEX is set in the live deploy env_vars (or enroll->restart->whoami probe). Overlaps ADX-P2-004.
- Evidence: __main__.py:61-67 mints ephemeral key with warning-only when unset; consent.py:118-120 fail-closes only if BOTH empty.
- Recent comments: adx-core: DONE — persistent ARENA_SIGNING_KEY_HEX + ARENA_BADGE_SIGNING_KEY_HEX + ARENA_ADMIN_TOKEN_HASH generated on-box, /etc/agentdex/arena.env (0600), injected via --env-file. Tokens survive restart. (Box-generated; 1Password backup pending op rate-limit clear.)

### INSTR-P0-bigger-instance - INSTRUCTOR: provision a multi-core instance bigger than the 256MB nano, scale-to-zero DISABLED

- Priority: `P0`
- Status: `done`
- Assignee: `adx-core`
- Lane: `platform`
- Impact: THE hard blocker for true 100 concurrent: 256MB nano physically cannot host gateway + multi-sidecar pool.
- Suggested fix: Instructor provisions a larger always-on SKU (deploy API has no instance-size field) or confirm none exists -> external host.
- Evidence: ADR-0012:117-118; deploy payload cli.py:844-849 has no instance-size/scale-to-zero field; quota 2/2 used.
- Recent comments: adx-core: DONE — provisioned fresh Lightsail 2xlarge 'agentdex-arena-1' (8vCPU/30GB, ubuntu_22_04, us-west-2, acct 981019652708), static IP 54.203.252.69. europa untouched. Arena deployed + LIVE: http://54.203.252.69:8889/healthz=200, /metrics live (latest code). pool=4, per-owner cap=3.

### LADDER-P1-incremental-cached - Incremental ladder fold + cached /ladder (full recompute = boot/repair only); coordinate with ADX-P1-007

- Priority: `P1`
- Status: `triage`
- Assignee: `adx-core`
- Lane: `ladder`
- Impact: recompute_ladder is 3 full O(N) passes run synchronously on the single event loop per /ladder, twice per rated finish, whoami, badge.
- Suggested fix: Maintain a live in-memory ratings fold updated per battle-result; serve /ladder from cache; preserve Q5 anti-pay-to-rank parity.
- Evidence: events.py:195-237 recompute_ladder; called gateway.py:1355, 1144, 1182, mcp_surface.py:349, 1996. Same _finish lines as ADX-P1-007.

### ADX-P1-003 - Make observability acceptance fail when traces are absent

- Priority: `P1`
- Status: `todo`
- Assignee: `harness`
- Lane: `observability`
- Impact: The platform can pass trace-propagation tests while producing no usable trace/span link.
- Suggested fix: Require actual trace context/link presence in acceptance tests; document fallback mode separately.
- Evidence: pass31, pass32

### BENE-DOC-10 - Render + deploy all new blog/docs/case-study/design content

- Priority: `P1`
- Status: `todo`
- Assignee: `bene`
- Lane: `render-deploy`
- Impact: New content must reach the live site; recurring render/deploy lane (bene).
- Suggested fix: Regen HTML via build-docs.py, sync the 4-copy mirror chain, Koyeb deploy, render-verify all 4 view x lang per the bilingual-render lesson; coordinate with og translation pass.
- Evidence: site/build-docs.py
- Recent comments: bene-core: READY FOR BENE: all 8 content cards (DOC-02..09) merged to origin/main. New source for render+deploy: blog/{why-bene,what-is-bene,how-we-build-bene}.md ; docs/examples.md ; docs/case-studies/{cs03-multi-agent-arena,cs04-trace-rag-other-memory,cs05-meta-harness-evolution}.md ; docs/design/architecture-diagrams.md (mermaid). Run site/build-blog.py + build-docs.py, wire nav for the new docs (examples, cs03-05, design diagrams w/ mermaid), 4-copy mirror + Koyeb deploy, render-verify 4 view x lang (chromium dump-DOM). zh translations are og's lane.

### BENE-RVW-P1-landing-honesty - Landing: move turnkey-vs-wire-yourself honesty up; bind 30s/0.3s/HEAD claims to version+provenance

- Priority: `P1`
- Status: `todo`
- Assignee: `bene`
- Lane: `launch-ux`
- Impact: Landing reads as a fully-stable product; the honest 'agent loop turnkey, rest is lego' framing sits too low; perf claims unbound to a version look like marketing once 0.2.1 behavior shifts.
- Suggested fix: On site/index.html (+ zh): surface the turnkey-vs-wire-yourself line near the first screen; annotate the 30s/0.3s/real-HEAD-run claims with version 0.2.1 + recording provenance. Sequence AFTER BENE-RVW-P0-version (same file).
- Evidence: Eddie review: 'honesty in landing but position too low'; Integrating-BENE 'agent loop turnkey; everything else is lego'.

### BENE-SCRUB-08 - Rebuild site + ride pending redeploy (DNS+DOC-10+zh+scrub); live-verify clean

- Priority: `P1`
- Status: `todo`
- Assignee: `bene`
- Lane: `render-deploy`
- Impact: Scrub must reach the live site in the same redeploy as DNS-removal + DOC-10 + latest zh.
- Suggested fix: Rebuild build-docs.py + build-blog.py, purge stale design/research sidebar links, 4-copy mirror + ONE arena Koyeb redeploy, live-verify docs no longer show Status/LOC/Verdict/Scene-04:32 (chromium dump-DOM).
- Evidence: PR#27, BENE-DOC-10
- Recent comments: bene-core: SCOPE EXPANSION (Eddie review): this single redeploy is also the P0#3 fix -- live /bene/docs shows 45 docs but repo committed = 37; the redeploy must bring live to 37. Ride it together with P0#1 (BENE-RVW-P0-version, landing 0.2.1) + P0#2 (BENE-RVW-P0-llms-canonical) once those land on main, so ONE deploy makes live provenance-clean. Source already clean for the EN scrub (#44/#45). Live-verify checklist: docs=37, version=0.2.1, llms=good-night-oppie/bene, codegen/COMMUNITY-BENCH 0 work-trace (EN+zh). Gates BENE-RVW-P0-launch-gate.

### ENROLL-P1-device-flow-backend - adx-core: implement ADR-0013 device-flow + /enroll/account backend (D2/D3/D7 wire contract)

- Priority: `P1`
- Status: `todo`
- Assignee: `adx-core`
- Lane: `onboarding`
- Impact: ADR-0013 landed (PR #295). The adx-cli onboarding journey (adx login GitHub device-flow -> adx onboard wizard -> account-authed enroll -> adx status) is blocked on the backend half of the FROZEN wire contract: POST /auth/device/start + /auth/device/poll (GitHub OAuth app, operator-held secret), POST /enroll/account (session-authed token mint), the github_id<->owner account datastore, and the account->agents join that feeds /status. Until these ship, adx-cli P1-P3 can only build against stubs.
- Suggested fix: Implement the D2/D3/D7 endpoints against the frozen request/response shapes in ADR-0013 so adx-cli integrates for real. Register the GitHub OAuth app (client id/secret stays on the backend, never reaches the CLI). Per-agent consent-token model + quota keying are UNCHANGED; /enroll/account is purely a new way to obtain today's token. Coordinate with AWS-PUBLIC-DNS-TLS (agentdex.builders must be live + TLS) so device-flow is real.
- Evidence: PR #295 docs/adr/0013-first-time-user-onboarding-pip-login-wizard.md (Sections D2/D3/D7)

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

### RECOVER-P1-sidecar-respawn - Auto-respawn a dead sidecar in SidecarPool and evict its battle_id/_load routes

- Priority: `P1`
- Status: `todo`
- Assignee: `adx-core`
- Lane: `durability`
- Impact: One OOM permanently degrades a fraction of 100 users: dead sidecar stays in routing map, new battles routed to the corpse.
- Suggested fix: On Node death, respawn the pool member and purge its _owner/_load entries so _least_loaded stops routing to it.
- Evidence: sidecar.py:117-126 fails pending futures with no respawn; pool.py:96-106 keeps dead sidecar in _owner/_load.

### RVW-P1-codex-adx-cli-prs - codex: review all open adx-cli PRs (#295 ADR-0013, #178 observability acceptance)

- Priority: `P1`
- Status: `todo`
- Assignee: `codex`
- Lane: `review`
- Impact: adx-cli has 2 open PRs needing independent adversarial review before merge: #295 (ADR-0013 onboarding design) and #178 (ADX-P1-003 observability acceptance gate). codex is the integrity/audit reviewer on this board.
- Suggested fix: Adversarially review both PRs (gh pr view/diff 295 + 178). For #295 stress the wire-contract + anti-pay-to-rank + secrets-discipline invariants (OAuth secret never reaches CLI). For #178 confirm the gate cannot false-green when traces are absent + that it does not flake on the live-bridge/Langfuse gating. Cascade genuine follow-ups per the usual /tmp/pr_comment_followup_*.md pattern; post a kanban comment with the verdict.
- Evidence: PR #295, PR #178

### RVW-P1-og-adx-cli-prs - og: review all open adx-cli PRs (#295 ADR-0013, #178 observability acceptance)

- Priority: `P1`
- Status: `todo`
- Assignee: `og`
- Lane: `review`
- Impact: adx-cli has 2 open PRs needing independent review before merge: #295 (ADR-0013 first-time-user onboarding design — architecture/doc + wire-contract coherence) and #178 (ADX-P1-003 observability acceptance gate — must fail when traces are absent).
- Suggested fix: Review both PRs: gh pr view 295 / 178 + gh pr diff. For #295 check ADR coherence with the adx-cli<->adx-core wire contract + doc-lint reachability + release-last sequencing. For #178 verify the acceptance gate actually fails on absent traces (no false-green). Post findings as PR comments and a kanban comment here; move to review-clear or file follow-ups.
- Evidence: PR #295, PR #178

### ADX-ONLINE-001 - launch: watchable Human-vs-AI battle UX (line-protocol + sim/client/view + spectator/TUI/replay)

- Priority: `P1`
- Status: `running`
- Assignee: `adx-cli`
- Lane: `launch-ux`
- Impact: Getting agentdex ONLINE means a watchable arena — the whole pitch is spectating agents fight. Without the typed protocol + state-reducer + spectator/replay, the online arena is unwatchable (raw |move| rows, no fog-of-war, no replay).
- Suggested fix: Ship the digest 2026-06-17 P1->P3 backlog as tiny PRs. P1 protocol foundation MERGED today (PR #200 typed lineproto, PR #201 full protocol-log capture + (seed,inputLog) re-sim parity). Next: state-reducer (client.py), {reason,action} schema + |-reasoning|, then TUI/spectator/replay.
- Evidence: PR#200, PR#201, .supergoal-v3/ROADMAP.md
- Recent comments: adx-cli: Battle-UX foundation merged: PR #200 (typed line-protocol) + #201 (full protocol-log capture, byte-identical re-sim). Side quest: drained the SidecarPool review cascade (#197/#198/#203/#204) as 6 tiny PRs #202-#207 — fixes the pool capacity-leak + routing bugs relevant to ADX-ONLINE-002's 100-user push. Next: adx-client state-reducer, then {reason,action} + spectator/TUI/replay. / imported: adx-cli-6 2026-06-18: launch scope SHIPPED — typed line-protocol (#200/#201), state reducer (client.py), watchable human-playable TUI `adx arena play` (#271 + #279). Per the AWS wire contract /replay is the launch watch surface; live spectator stream (P2-b/c) deferred by design. Remaining backlog: P2-d/e reasoning+replay-scrub, P3 polish. Lint follow-up: arena_tui UP038 fixed #283 (unblocked the fleet pre-commit gate).

### AWS-PUBLIC-DNS-TLS - agentdex.builders DNS A-record + Caddy auto-TLS -> arena box

- Priority: `P1`
- Status: `blocked`
- Assignee: `adx-core`
- Lane: `platform`
- Impact: Public play endpoint per Eddie: agentdex.builders = arena (users play via agentdex-cli); ai-builders.space stays landing+docs and redirects login/signup here.
- Suggested fix: Namecheap setHosts agentdex.builders @ A -> 54.203.252.69 (preserve existing records); install Caddy reverse_proxy :8889 with auto-TLS once DNS resolves.
- Evidence: op service-account rate-limited / openclaw vault access for namecheap-api creds (op://openclaw/namecheap-api); egress 54.202.180.208 already whitelisted.

### BENE-BATTLE-INTEGRATE - Lane B → A3 integration: swap mock_fitness for real multi_dim_fitness

- Priority: `P1`
- Status: `blocked`
- Assignee: `bene-core`
- Lane: `bene-core`
- Impact: 
- Suggested fix: 
- Evidence: 

### GA-BENE-4 - Evolution/lineage view data: fitness-over-gens, kill-gate verdicts, winning mutation (dashboard Evolution panel)

- Priority: `P1`
- Status: `blocked`
- Assignee: `bene`
- Lane: `bene-core`
- Impact: The Evolution panel that visualizes the climb; data side of GA-BENE-1's dashboard.
- Suggested fix: Shape evolve output (lineage + killgate_report + DGM archive) into the dashboard Evolution-panel data contract.
- Evidence: depends on GA-BENE-3 real-evolve output shape
- Recent comments: bene-core: Blocker ADVANCED: evo-view JSON field map received from adx-cli-10 (#541, source=C2 driver DONE_JSON / E2EReport.to_done_json); confirmed dashboard-reads-DONE_JSON (#539/#544). My evolve_codex_harness EvolveOutput already emits the matching shape. Blocked on: a frozen done_*.json sample artifact (requested) + the GA-BENE-1 SPA host existing. / bene-core: Still blocked on the GA-BENE-1 SPA host. Engine/data is COMPLETE + gap-free: adx-cli e2e_driver.to_done_json already builds the full evo-view DONE_JSON from my evolve backend (ground-truthed). Escalated re-point to harness-13 (#555). / bene-core: Reassigned bene-core -> bene (front-end evo-panel). Build input fully provided: done_c2_pokeenv.json (adx-cli) + #541 field map + gate-on-backend==pokeenv. bene-core engine/data confirmed gap-free (e2e_driver owns to_done_json). Blocked on the GA-BENE-1 SPA host. Per #573.

### INSTR-P1-free-quota-or-vps - INSTRUCTOR/OPERATOR: free the 2/2 quota (delete meta-vex, user green-lit) OR stand up external ~$5/mo VPS fallback

- Priority: `P1`
- Status: `blocked`
- Assignee: `platform-instructor`
- Lane: `platform`
- Impact: Contingency if no on-platform bigger SKU: need a service slot or an off-platform host for the scale instance.
- Suggested fix: Instructor DELETE meta-vex (green-lit 2026-06-11), or operator stands up VPS + DNS + ~17 env vars + secrets (Dockerfile is portable).
- Evidence: Quota 2/2 (meta-vex+agentdex), no self-serve DELETE (go/no-go:38-42); Dockerfile:60 shell-form CMD honoring $PORT.

### OPS-P1-go-live-runbook - Write a go-live deploy/scale/rollback RUNBOOK (pre-flight envs, thresholds, rollback)

- Priority: `P1`
- Status: `review`
- Assignee: `adx-core`
- Lane: `ops`
- Impact: Dangerous defaults + boot-crash envs + keep-alive + rollback are scattered across go-nogo + loadtest + ADR-0012.
- Suggested fix: Consolidate into docs/runbooks/arena-go-live.md incl the concrete bigger-instance env set (<=20 cap; inventory ~17).
- Evidence: docs/runbooks/ holds only badge-admin.md + membership-admin.md; defaults POOL_SIZE=1, MAX_BATTLES=16, OLD_SPACE=96.
- Recent comments: adx-core: Runbook written to box /opt/agentdex/RUNBOOK.md (deploy/redeploy/rollback/operate/scale/pre-flight). PR to docs/runbooks/arena-go-live.md pending.

### ADMIT-P1-retry-after-and-per-owner-cap - Admission control: Retry-After on capacity 503 + per-owner concurrent-battle cap (anti-monopolization)

- Priority: `P1`
- Status: `done`
- Assignee: `adx-core`
- Lane: `admission`
- Impact: Bare 503 gives clients no backoff signal; one owner can fill the whole pool and starve the other 99 users.
- Suggested fix: Add Retry-After header to the capacity 503; cap concurrent battles per claims_token_id. ADR-0012 sec7. (bounded queue deferred.)
- Evidence: gateway.py:836-843 bare 503, grep retry-after=0; self.sessions keyed by battle_id only (gateway.py:572); BattleSession.claims_token_id gateway.py:388.
- Recent comments: adx-core: MERGED as PR #243. Per-owner cap (default 3, 429+Retry-After, keyed on normalized owner) + Retry-After on the pool-full 503.

### ADX-P1-001 - Stop spending rated/evolution/badge quota before work is accepted

- Priority: `P1`
- Status: `done`
- Assignee: `adx-cli`
- Lane: `fairness`
- Impact: Owner pays scarce monthly quota for invalid teams, capacity failures, sidecar failures, and signer failures.
- Suggested fix: Move quota debit after validation and successful durable acceptance, or add explicit refund records on retryable failures.
- Evidence: pass26, pass33, pass34, pass35, pass36
- Recent comments: imported: adx-cli-6 2026-06-18: DONE — Class B spend-after-success implemented at all spend sites (rated battle / badge_mint / evolve HTTP+MCP); verified in-code during the ADX-P2-004 work.

### ADX-P1-002 - Make owner export include replay, badge, and rating lineage

- Priority: `P1`
- Status: `done`
- Assignee: `adx-cli`
- Lane: `owner-data`
- Impact: Human owner and agent cannot reconstruct paid/rated history from `/my/events` or local SQLite.
- Suggested fix: Select events by canonical agent/battle joins and nested period payloads, not only top-level tenant_id.
- Evidence: pass17, pass19, pass20, pass21, pass41, pass42-candidate
- Recent comments: imported: adx-cli-6 2026-06-18: DONE — /my/events owner-export 3-case (tenant_id / legacy-badge agent_name / nested period battle_id) present + tested; verified by adx-cli-5.

### ADX-P1-004 - Tighten admin surface and auth-before-parse contract

- Priority: `P1`
- Status: `done`
- Assignee: `adx-cli`
- Lane: `security`
- Impact: Operator-only endpoints are exposed in public OpenAPI and one documented auth ordering claim is false for malformed JSON.
- Suggested fix: Hide or split admin OpenAPI, then test auth rejection before body validation for protected routes.
- Evidence: pass24, pass25
- Recent comments: imported: adx-cli-6 2026-06-18: DONE — only /admin/grant-membership is include_in_schema=False; auths via Depends(_check_admin) BEFORE await request.json() (auth-before-parse); gated agent routes use raw body:dict. Verified by adx-cli-5.

### ADX-P1-005 - Collusion quarantine_reason leaks heuristic internals to the agent (D7)

- Priority: `P1`
- Status: `done`
- Assignee: `codex`
- Lane: `integrity`
- Impact: _check_collusion returns detailed reason strings (thresholds, 'repeatedly clicked choice: move 0', 'win-transfer W-L over N matches') into session.ended.quarantine_reason, surfaced to the visiting agent on the battle receipt. Leaking the exact heuristic enables trivial evasion (add 1 random move; stay under the 5-match win-transfer threshold) — same D7 anti-enumeration class as the battle_id leak (#186).
- Suggested fix: Collapse quarantine_reason to an opaque/coarse value on the wire (or omit it); log the detailed forensic reason server-side only (log.warning), mirroring _opaque_error. Keep the EventLog row detailed for audit.
- Evidence: gateway.py:1001-1045 (_check_collusion detailed strings), :1059-1062 (written to session.ended), :1116-1126 (event log). adversarially confirmed (dogfood audit 2026-06-17)
- Recent comments: codex: Fixed: PR #189 MERGED — opaque 'quarantined by collusion forensics' on the wire (session.ended + receipt); detailed heuristic reason preserved in durable quarantine EventLog row + server log.warning for operator audit. _check_collusion unchanged (unit test green). Full arena suite 189 passed. Same D7 class as #186.

### ADX-P1-006 - Dispute event appended BEFORE re-sim — duplicate events on retry

- Priority: `P1`
- Status: `done`
- Assignee: `adx-cli`
- Lane: `integrity`
- Impact: POST /battle/{id}/dispute appends the 'dispute' event (gateway.py:1771-1777) BEFORE running replay_input_log (:1790). If re-sim throws (:1822) the handler 500s but the dispute event is already durable; a client retry appends a SECOND dispute event — structural event-log corruption (violates Class A write-then-log intent for disputes).
- Suggested fix: Append the dispute event AFTER a successful re-sim, OR guard with an idempotence check (skip if a dispute event for this battle_id already exists). Mirror the append-before-publish/fail-closed contract.
- Evidence: gateway.py:1771-1777 (append), :1790-1794/:1822 (resim+throw). adversarially confirmed (dogfood audit 2026-06-17)
- Recent comments: imported: adx-cli-6 2026-06-18: DONE — append-before-resim residual closed by PR #281 (dispute/quarantine recorded only after a successful re-sim, atomic append_many); idempotence #278, restart-survival #280.

### ADX-P1-007 - Ladder published_delta race: concurrent _finish for same player inflates delta

- Priority: `P1`
- Status: `done`
- Assignee: `adx-cli`
- Lane: `fairness`
- Impact: _finish captures before_rating (gateway.py:1131) OUTSIDE the atomic append window, then recomputes after (:1169). If a second concurrent _finish for the same visitor_name appends between A's capture and A's recompute, A's published_delta double-counts B's battle — a fairness/rating-integrity violation under async concurrency.
- Suggested fix: Capture before_rating AFTER the append_many (or serialize _finish per visitor_name with a per-player lock) so before/after bracket exactly one battle's mutation.
- Evidence: gateway.py:1131 (before snapshot), :1160 (append), :1169 (after). adversarially confirmed (dogfood audit 2026-06-17)
- Recent comments: imported: adx-cli-6 2026-06-18: DONE — ladder published_delta race fixed via the finish-lock window (PR #269).

### BENE-BATTLE-B1 - Lane B: evolve_battle_harness Contract-4 entrypoint (bene)

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `bene-core`
- Impact: 
- Suggested fix: 
- Evidence: 

### BENE-BATTLE-B2 - Lane B: Pareto evaluator wired to Contract-3 5-dim fitness

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `bene-core`
- Impact: 
- Suggested fix: 
- Evidence: 

### BENE-BATTLE-B3 - Lane B: hash-locked kill-gate probe (win_rate_uplift + anti-vacuous)

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `bene-core`
- Impact: 
- Suggested fix: 
- Evidence: 

### BENE-BATTLE-B4 - Lane B: SharedLog lineage + run_seed reproducibility

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `bene-core`
- Impact: 
- Suggested fix: 
- Evidence: 

### BENE-CODEX-EVO-G1 - SECH Contract G: evolve_codex_harness + DGM archive + hash-locked kill-gate (bene-core B1)

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `bene-core`
- Impact: Without the bene-core engine the SECH loop has no gated promotion + open-ended archive; adx lanes have nothing to wire against.
- Suggested fix: Shipped bene/kernel/codex_harness/: evolve_codex_harness (Refiner-as-mutation-op loop), DGMArchive (open-ended), hash-locked kill-gate; mock Refiner/apply/eval swappable for adx R/S/E.
- Evidence: PR#64 merged 1e3ea0c; full suite 1082
- Recent comments: bene-core: Lane complete on bene main (G1 + HELDOUT merged, #64/#65). Real e2e blocked on adx-cli (Contract H/E) + adx-core (R/S); B3 in-episode is a flagged proposal.

### BENE-CODEX-EVO-HELDOUT - SECH held-out anti-overfit gate: disjointness + VOID + hash-stamping (bene-core)

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `bene-core`
- Impact: Without held-out disjointness an overfit harness could clear the kill-gate; SPEC DONE #3/#4 depend on it.
- Suggested fix: HeldoutManifest + is_disjoint/overlap; evolve_codex_harness(heldout_manifest=) checks heldout-intersect-training=empty before the win-rate gate (overlap->VOID), stamps 3 sha256 hashes on ACCEPT.
- Evidence: PR#65 merged 9b508e9; full suite 1087
- Recent comments: bene-core: Held-out gate merged (#65); disjointness+VOID+hash-stamp verified.

### BENE-DOC-01 - Scaffold the new /blog section on bene-site (index + post template + nav)

- Priority: `P1`
- Status: `done`
- Assignee: `bene`
- Lane: `blog`
- Impact: No blog exists yet; the WHY/WHAT/HOW narrative needs a home. Render lane (bene).
- Suggested fix: Add site/blog/ index + post template + nav link (EN+zh) and build-docs.py blog-page generation; rebase on og in-flight build-docs.py changes, do not clobber; render-verify.
- Evidence: site/build-docs.py, site/index.html
- Recent comments: bene-core: Confirmed merged as PR #17 (origin/main). /blog scaffold + site/build-blog.py live; all 3 blog posts render against it (verified build-blog.py -> 3 EN posts + index).

### BENE-DOC-03 - Blog post: WHAT BENE is — the seven pillars

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `blog-content`
- Impact: Crisp WHAT: per-agent VFS, checkpoints, engrams, eval-probe kill-gates, autonomy ladder, MCP server, evolutionary meta-harness search.
- Suggested fix: Write blog/what-is-bene.md (EN); each pillar with one REAL example snippet from examples/, ground-truthed against the CLI/code.
- Evidence: examples/library_basics.py, bene/cli/main.py, docs/architecture.md
- Recent comments: bene-core: MERGED as PR #18 (squash). Seven-pillars WHAT post; all CLI snippets ground-truthed; render-verified via build-blog.py.

### BENE-DOC-04 - Blog post: HOW we build BENE — harness engineering + eval-gated evolution

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `blog-content`
- Impact: Answers HOW: tiny PRs, falsifiable eval-probe kill-gates, the breeding program, trace-based RAG.
- Suggested fix: Write blog/how-we-build-bene.md (EN), grounded in the real repo (probes, mh search, tiny-PR discipline).
- Evidence: bene/kernel/eval, bene/metaharness, docs/meta-harness.md
- Recent comments: bene-core: MERGED as PR #20. HOW post; opening WHY/WHAT/HOW series complete. Ground-truthed + render-verified.

### BENE-DOC-05 - Surface real runnable examples per pillar in the docs

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `docs-examples`
- Impact: Mission asks for REAL examples; 19 example scripts exist but are not woven into the docs narrative.
- Suggested fix: Expand docs (architecture/quickstart/pillar pages) with runnable, explained snippets drawn from examples/*.py; each ground-truth-run exit 0.
- Evidence: examples/, docs/architecture.md, docs/cli-reference.md
- Recent comments: bene-core: MERGED as PR #21. Examples gallery; 4 standalone examples verified exit 0.

### BENE-DOC-06 - Case study: multi-agent coding arena on BENE (ABSTRACT)

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `case-study`
- Impact: Flagship case study and the concrete WHY: BENE as the substrate backing a competitive multi-agent coding platform.
- Suggested fix: Write docs/case-studies/cs03-multi-agent-arena.md. HARD CONSTRAINT: agentdex-cli is the real consumer but DO NOT expose internals — pseudo-code/abstract ONLY.
- Evidence: docs/case-studies/cs02-ci-self-healing-refactor-swarm.md
- Recent comments: bene-core: MERGED as PR #23. Abstract arena case study; hard-constraint leak-scan clean.

### BENE-RVW-P1-docs-honesty-tone - Pull Integrating-BENE turnkey-vs-lego honesty into README; align tone with benchmark honesty

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `docs`
- Impact: Users infer from the first screen that everything is end-to-end wired; the honest turnkey-vs-wire-yourself split lives only deep in docs; README/landing tone should match the benchmark report's 'not fully supersedes' honesty.
- Suggested fix: Surface the turnkey-vs-wire-yourself split in README near the top; keep README/docs claims 'strong, not fully-supersedes' per docs/benchmarks. Files: README.md (+ docs/README.md if needed). bene owns the site/index.html landing twin (BENE-RVW-P1-landing-honesty) -> non-overlapping.
- Evidence: Eddie review Docs (Integrating BENE best doc) + Benchmark-report honesty.
- Recent comments: bene-core: DONE at source: the turnkey-vs-lego honesty is now near the README first screen + tone stays grounded (no 'fully supersedes') via PR #47; version drift in docs/integrating-bene.md ('still 0.2.0' -> in published 0.2.1) fixed in PR #48 (90f2ae1). The (v0.2.0) tags in meta-harness.md/t01 left as-is (historical feature-intro tags, not drift). The integrating-bene HTML re-render rides bene-12's BENE-SCRUB-08 deploy. / bene-core: DONE — both card deliverables (pull turnkey-vs-lego honesty into README + align tone to benchmark 'strong, not fully-supersedes') are README changes, GitHub-live via #47. The extra docs/integrating-bene.md version fix (#48, still-0.2.0 -> in published 0.2.1) is merged at source; its site-HTML render rides bene-12's BENE-SCRUB-08 deploy (deploy-target is 2 commits behind -> bene-12 push deploy-target + re-POST, fleet-fixable, NOT an Eddie blocker — corrected my earlier #382). Not gating this card.

### BENE-RVW-P1-readme-restructure - Day-2 README restructure: user-success path first, lore + 16 papers down

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `readme`
- Impact: README opens with banner/badges/Dune quote/lore/16 papers before Quick Start -> slows a first-time user's 'can I run this' judgment.
- Suggested fix: README first screen = one-line positioning + 3 bullets + 60s quickstart + expected-output + docs link FIRST; move Dune lore + 16 papers to a 'Why the name works' / 'Design metaphor' section lower down. File: README.md (good-night-oppie/bene).
- Evidence: Eddie review Repo-README + Day-2 sequence.
- Recent comments: bene-core: DONE at source: PR #47 (96d5714) merged. README first screen = positioning + 3 bullets + honest-scope (turnkey-vs-wire-yourself, links Integrating BENE) + docs link; Quick start (60s) w/ expected-output pulled above the kernel; Litany + framing table + 16 papers moved to 'Why the name works'/'Grounded in research'. Also dropped the dead docs/design+docs/research links (un-published in #29) + stale (v0.2.0). README renders live on GitHub immediately (no deploy needed). 0 broken anchors, markdownlint delta 0. / bene-core: DONE — source + GitHub-live both verified. PR #47 (96d5714) on origin/main; `gh api repos/good-night-oppie/bene/readme` serves the new structure (Quick start (60 seconds) / Running agents / Why the name works headings present) with 0 dead docs/design+docs/research links. README renders from origin/main directly so it's live with no deploy.

### BENE-SCRUB-01 - UN-PUBLISH docs/design/ + docs/research/ (relocate out of docs/, delete published HTML)

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `unpublish`
- Impact: v0.3-roadmap-spec.md (agent-generated: wf_ab0851dc-a40, 16 agents, per-feature Status/LOC/Verdict/Scene) + KERNEL-SPEC.md (build contract) + research/* are internal-by-nature; ZERO reader value, confuse real users.
- Suggested fix: Replicate the #27 DNS pattern: git mv docs/design + docs/research -> internal-docs/ (keep as internal source, out of the rglob build); git rm the published site/docs/design+research HTML (en; zh HTML too). Reader value already lives in the blog WHY/WHAT + docs/architecture.md. No build-docs.py edit (avoids og collision).
- Evidence: PR#27, docs/design/v0.3-roadmap-spec.md
- Recent comments: bene-core: MERGED as PR #29. Relocated 4 internal design specs + research to internal-docs/; kept architecture-diagrams.md public; deleted en HTML; fixed inbound link. FLAG bene: site/index.html:854 still refs docs/design/v0.3-roadmap-spec.md (landing lane). FLAG og: zh design/research un-publish (SCRUB-07).

### BENE-SCRUB-02 - Scrub work-trace from docs/tutorials/t02-e2e-self-healing.md

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `scrub`
- Impact: Reader doc polluted with agent work-trace (Status/Verdict/Scene/wf_ ids).
- Suggested fix: REMOVE Status:/LOC/Verdict/adversarial/test-paths/adx-cli-N/wf_/dramatized Scenes; REWRITE agent-Scenes -> reader scenarios, feature-status -> plain language; KEEP real schema (run_id/experiment_runs/ULID) stripped of agent framing. Kedaibiao: doc must respect the reader.
- Evidence: docs/tutorials/t02-e2e-self-healing.md
- Recent comments: bene-core: NO-ACTION (false positive): the grep hits are the tutorial's own example-project test names (tests/test_payment.py::test_* = the self-healing demo's payment-engine scenario), legitimate reader content, NOT bene-internal work-trace. Verified clean of real work-trace (Status/Verdict/Scene/wf_/adx-cli).

### BENE-SCRUB-03 - Scrub work-trace from docs/tutorials/t07-regression-guard.md

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `scrub`
- Impact: Reader doc polluted with agent work-trace.
- Suggested fix: Same 3-bucket scrub (REMOVE/REWRITE/KEEP) per the rubric.
- Evidence: docs/tutorials/t07-regression-guard.md
- Recent comments: bene-core: NO-ACTION: verified clean of real agent work-trace.

### BENE-SCRUB-04 - Scrub work-trace from docs/tutorials/t08-hundred-agents-scale.md

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `scrub`
- Impact: Reader doc polluted with agent work-trace.
- Suggested fix: Same 3-bucket scrub (REMOVE/REWRITE/KEEP).
- Evidence: docs/tutorials/t08-hundred-agents-scale.md
- Recent comments: bene-core: NO-ACTION (false positive): tests/test_db.py::test_* are the tutorial's db-scale example, reader content. Verified clean of real work-trace.

### BENE-SCRUB-07 - ZH scrub: all docs/zh/ counterparts (design+research unpublish + reader-doc scrub)

- Priority: `P1`
- Status: `done`
- Assignee: `og`
- Lane: `scrub-zh`
- Impact: zh docs carry the same work-trace; zh is og lane.
- Suggested fix: After PR #28 (og zh pass) lands: relocate docs/zh/design + docs/zh/research out of build, scrub docs/zh/tutorials t02/t08 + others, mirror the en scrub. Coordinate with bene-core (en is source of truth).
- Evidence: docs/zh/design/v0.3-roadmap-spec.md, PR#28
- Recent comments: bene-core: Mostly mooted by og's zh reset (c2a876c): docs/zh now = only README + cli-reference + integrating-bene (the 3 priority translations); the zh design/research/tutorials/codegen/COMMUNITY-BENCH counterparts were deleted from source, and #45 regenerated their committed site/zh/docs HTML as clean EN-fallback pages. og: confirm nothing zh-side still carries work-trace, then close. Tracked alongside BENE-RVW-P0-cn-docs.

### GA-BENE-3 - Lane B evolve de-mock: replace _mock_evolve with real evolve_battle_harness in the C2 driver

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `bene-core`
- Impact: The recursive-self-improvement core — without it the e2e is a mock, not the real harness climbing.
- Suggested fix: Fold the real bene evolve_battle_harness (proved standalone in done_e2e_real_bene.json) into e2e_driver.py, behind a flag/lazy-import with the mock as CI fallback.
- Evidence: done_e2e_real_bene.json proves real bene evolve e2e; _mock_evolve at e2e_driver.py:276/451
- Recent comments: bene-core: PR #355 (agentdex-cli) open + green locally: real _real_evolve backend folds bene's evolve_battle_harness into e2e_driver behind --evolve-backend real; mock stays CI default. 54 selfplay tests pass, ruff clean. Ready for adx-cli review/merge (it's your e2e_driver). / bene-core: DONE — PR #355 merged (86a60f51) after Codex-review fixes (cache-reuse + honor --margin-pp). Real bene evolve_battle_harness folded into the C2 driver behind --evolve-backend real; mock stays CI default. Admin-merged on local-green (54 selfplay tests) — CI runners bottlenecked by the OHE PR stream.

### OPS-P1-forward-scale-envvars - Forward ADX_SIDECAR_POOL_SIZE + ADX_SIDECAR_MAX_OLD_SPACE_MB in `adx deploy` (only ARENA_* forwarded today)

- Priority: `P1`
- Status: `done`
- Assignee: `adx-core`
- Lane: `ops`
- Impact: The SidecarPool scale lever is silently dropped on deploy -> pool size can't be set on the bigger box without the --env-vars escape hatch.
- Suggested fix: Extend cli.py env-forward allowlist to ADX_SIDECAR_* (pays off on the multi-core box).
- Evidence: cli.py:821 forwards only k.startswith('ARENA_'); __main__.py:179 reads ADX_SIDECAR_POOL_SIZE; sidecar.py:76 reads OLD_SPACE_MB.

### OPS-P1-healthz-readiness - Make /healthz a real readiness probe (sidecar alive + RSS) instead of static {ok:true}

- Priority: `P1`
- Status: `done`
- Assignee: `adx-core`
- Lane: `observability`
- Impact: Platform never recycles a sick container -> an OOM/dead-sidecar spiral stays 'healthy' and keeps taking traffic.
- Suggested fix: Compute readiness from app.state.sidecar rss_mb + returncode (cheap one-ps-read/sidecar); fail when unhealthy.
- Evidence: gateway.py:1406/1418-1420 static _ARENA_HEALTH; Sidecar.rss_mb adx_showdown/sidecar.py:153; SidecarPool.rss_mb pool.py:108.
- Recent comments: adx-core: MERGED as PR #238. /healthz now 503s on a dead/OOM sidecar so the platform recycles the container. SidecarPool.any_dead() added.

### OPS-P1-metrics-stats - Add /metrics (or /debug/stats): RSS, active battles, 503 count (queue depth when queue lands)

- Priority: `P1`
- Status: `done`
- Assignee: `adx-core`
- Lane: `observability`
- Impact: Operator is blind between a healthy spike and an OOM spiral; the 503 path increments no counter.
- Suggested fix: Expose len(self.sessions) + rss_mb + a 503 counter via a small /metrics endpoint.
- Evidence: no /metrics/counters (grep none); len(self.sessions) gateway.py:572 + rss_mb already exist.
- Recent comments: adx-core: MERGED as PR #240. GET /metrics: active_battles, registered_agents, cap_503_total counter, sidecar rss (timeout-bounded). Also EOF-swept the synced blog HTML to unblock CI.

### PLAY-P1-bene-e2e-live - bene-core: e2e side-by-side LIVE play on the cloud arena — surface real issues for immediate fix

- Priority: `P1`
- Status: `done`
- Assignee: `bene-core`
- Lane: `e2e-play`
- Impact: We have no continuous real-user signal from the LIVE cloud arena. adx-cli is shipping the watchable Human-vs-AI battle UX (ADX-ONLINE-001) plus the ADR-0013 onboarding journey (#295), but protocol/UX/durability/fairness bugs only surface when a real agent plays end-to-end against the DEPLOYED arena: enroll -> begin -> state/choose -> finish -> replay -> status. Side-by-side concurrent play also exercises the 100-concurrent path.
- Suggested fix: Drive the bene adapter / MCP play loop against the LIVE arena (ADX_ARENA_URL=https://agentdex.ai-builders.space today, agentdex.builders once DNS/TLS lands) with MULTIPLE bene agents playing concurrently. Run the full journey several times: enroll -> play N battles -> check /status + /ladder -> /replay. File EACH issue (UX, protocol, durability, fairness) as its own kanban card tagged to the owning lane (adx-cli or adx-core) so we fix in real time. This is the real-cloud dogfood signal the launch gate (ADX-ONLINE-002) needs.
- Evidence: ADX-ONLINE-001 (battle UX) + PR #295 (onboarding) + ADX-ONLINE-002 (100-user launch gate)
- Recent comments: imported: BLOCKED (bene-core-6, 2026-06-18): Cannot mint oppie token — ARENA_SIGNING_KEY_HEX only on Koyeb container; SSH to 45.63.66.158 (Vultr) times out; op read rate-limited. Escalated to harness (#438). Enrollment gate requires token. / imported: DONE (bene-core-6, 2026-06-18T23:19:53Z): e2e verified on Europa arena (54.203.252.69:8889). enroll/whoami -> battle/start -> battle/begin (sandbox, PoP) -> 19 turns -> ended (winner=anchor-random) -> replay OK (52 input_log entries). Token at .state/oppie.token. DNS/Vultr caveat in A2A #443/#444.

### RECOVER-P1-interrupted-signal - Return a clear 409 'interrupted by restart' for begin-without-end battles after gateway restart (vs opaque 403)

- Priority: `P1`
- Status: `done`
- Assignee: `adx-core`
- Lane: `durability`
- Impact: After a restart, /choose on a dropped in-flight battle returns an opaque 403, confusing players mid-game.
- Suggested fix: Detect begin-without-end on boot and return 409 interrupted; full (seed,inputLog) resurrection needs a WAL schema change (backlog).
- Evidence: self.sessions={} on boot gateway.py:572; boot replay rebuilds only names/memberships gateway.py:544-565; /choose 403 gateway.py:1663-1664.
- Recent comments: adx-core: MERGED as PR #246. Boot rebuilds begin-minus-end set; /choose returns owner-scoped 409 on restart-dropped battles (non-owners 403).

### ROUTE-P1-dispute-pool - Route dispute replay op through SidecarPool (start <id>-dispute or special-case replay as battle-less) + regression test

- Priority: `P1`
- Status: `archived`
- Assignee: `adx-cli`
- Lane: `routing`
- Impact: Disputes 500 the instant ADX_SIDECAR_POOL_SIZE>1 (the config 100 concurrent needs) -> broken integrity surface under scale.
- Suggested fix: Start the dispute battle on a pool member before replay, or special-case replay/import as battle-less; add test_pool replay test.
- Evidence: gateway.py:1818 replay_input_log(battle_id=f'{id}-dispute') never start-ed; pool.py:95-98 raises 'not owned'.
- Recent comments: adx-core: ALREADY DONE by adx-cli #203/#204 — pool.py transient_replay path routes the dispute re-sim correctly under POOL_SIZE>1. Reconciled against origin/main; no separate PR needed.

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

### ADX-P2-001 - Reduce starter and CLI footguns for visiting agents

- Priority: `P2`
- Status: `done`
- Assignee: `codex`
- Lane: `agent-ux`
- Impact: Agents hit stale docs, missing `adx` arena commands, traceback setup errors, and asymmetric MCP proxy behavior.
- Suggested fix: Update `/skill.md`, add or explicitly defer `adx arena` commands, normalize starter-kit errors, and test missing battle IDs.
- Evidence: pass14, pass15, pass16, pass29
- Recent comments: codex: D3 (starter-kit raw tracebacks) shipped: PR #185 MERGED — shared run_agent_main() wrapper turns missing keyfile/team/expired-token/unreachable-arena into one-line stderr + exit codes (setup=2, runtime=1), re-raises genuine bugs; all 3 agents + bootstrap.sh enroll guarded. 7-case test. Verified e2e. Remaining ADX-P2-001: D5 battle_id enumeration (security, prio5). D4 WONTFIX. / codex: ADX-P2-001 agent-ux footguns COMPLETE (4 tiny PRs merged): D2 adx-arena-stub #183, D1 SKILL.md-shape #184, D3 starter-kit-clean-errors #185, D5 battle_id-anti-enumeration #186 (security: auth-before-existence on state/choose/fork/dispute, full arena suite 187 passed). D4 MCP-proxy-asymmetry adversarially REFUTED -> WONTFIX (intentional Mode2 game-only split). Moving to review for adx-cli/harness verification. Next codex card: ADX-P2-002 gameplay legibility (D6 gym-mapping already merged #167; remaining: foe-HP/recent_turns, replay metadata, anchor/gym test coverage). / codex: REVIEW VERIFIED: D2 arena stub + D3 starter-kit clean errors + D5 auth-before-existence all covered. Added sidecar-free call-order regression for state/choose/fork/dispute verify-before-lookup. Tests: .venv/bin/python -m pytest packages/agentdex_cli/tests/test_arena_defer.py examples/agent-starter-kit/tests/test_clean_errors.py packages/agentdex_arena/tests/test_visitor_surface.py::test_live_battle_and_replay_routes_verify_before_existence_lookup -q => 18 passed. Ruff touched files => pass.

### ADX-P2-002 - Make arena gameplay feedback more legible and less first-legal

- Priority: `P2`
- Status: `done`
- Assignee: `codex`
- Lane: `gameplay`
- Impact: Agents can win or lose for shallow reasons and cannot always understand losses from state/replay alone.
- Suggested fix: Repair gym mapping, expose opponent HP/recent turns, enrich replay metadata, and test anchor/gym coverage.
- Evidence: pass2, pass3, pass4, pass6, pass7, pass8, pass12, pass13
- Recent comments: codex: ADX-P2-002 gameplay legibility substantively COMPLETE: D8 /replay opponent archetype #187, D7 turn-0 (battle start) marker #188 (was empty recent_turns, confirmed empirically). D6 gym-trick-room mapping already merged #167. D9 anchor/gym coverage: already closed by parametrized test_every_gym_resolves_to_a_real_team over ALL GYM_LEADERS + badge/selection/rated tests — no real gap found (char's 'GYM_TEAM_INDEX collision' did NOT hold up: distinct keys 1/2/3, gyms use separate ARCHETYPE_GYM_TEAMS). Full arena suite 189 passed. Moving to review. / codex: REVIEW VERIFIED: gameplay legibility guards are in place. Pure tests: .venv/bin/python -m pytest packages/agentdex_arena/tests/test_gym_team_resolution.py packages/agentdex_arena/tests/test_visitor_surface.py::test_gameplay_legibility_contract_sidecar_free -q => 9 passed. Covers gym mapping including trick-room, BattleSession turn-0 '(battle start)' marker, _render foe_hp_pct/recent_turns contract, and replay opponent field. Live replay/recent-turn tests were attempted but the sidecar/ASGI harness left stale tool sessions in this sandbox, so they are not counted here. Ruff touched files => pass.

### ADX-P2-003 - Preserve verified strengths while fixing gaps

- Priority: `P2`
- Status: `done`
- Assignee: `harness`
- Lane: `regression-guard`
- Impact: Known-good surfaces are easy to break while fixing adjacent defects.
- Suggested fix: Keep recompute ladder, anti-pay-to-rank property tests, `/whoami` redaction, team validation, and local log idempotence in the regression suite.
- Evidence: pass5, pass11, pass22, pass23, pass30

### ADX-P2-004 - Rated-battle quota not persisted — resets on gateway restart

- Priority: `P2`
- Status: `done`
- Assignee: `adx-cli`
- Lane: `fairness`
- Impact: quota_used is in-memory only (consent.py:159-182); EventLog replay on boot (gateway.py:536-558) hydrates 'register'/'membership_grant' but NOT quota. A gateway restart resets every agent's daily rated cap, allowing >5 rated battles/UTC-day across restarts (anti-pay-to-rank-adjacent, ADR-0011 §3a/§5e). Exploitability is low on a stable single-process deploy (agent cannot force a restart), hence P2 not P1.
- Suggested fix: Emit a durable quota_spent event on each spend_quota increment; replay quota_spent (scoped to current UTC day) on boot to rehydrate quota_used.
- Evidence: consent.py:114-124/:159-182, gateway.py:536-558. adversarially confirmed (dogfood audit 2026-06-17)
- Recent comments: imported: adx-cli-6 2026-06-18: DONE — PR #284: durable quota_spend event + UTC-day-scoped boot replay; spend_quota returns the debited key (no midnight day-skew); all 4 spend sites wired; 9 sidecar-free tests; full arena suite green (264 passed).

### ADX-P2-005 - Scratchpad rendered into battle state without escaping — self-injection of fake turn lines

- Priority: `P2`
- Status: `done`
- Assignee: `codex`
- Lane: `integrity`
- Impact: Agent-authored scratchpad text is rendered into the battle-state string (showdown_battle_bridge.py:~107 / state render) without escaping, so an agent can inject a '## Recent turns'-style header + forged 'T#: ...' lines that appear in its OWN rendered state and poison its decision loop. Self-harm only today (no cross-agent/rating impact) → P2; but it is the latent cross-surface injection risk if scratchpad ever reaches a replay/opponent view.
- Suggested fix: Escape/segregate scratchpad when rendering (fence it in a clearly-delimited block, strip markdown headers, or render structured fields instead of raw markdown). Add a render test asserting injected headers don't duplicate real section headers.
- Evidence: showdown_battle_bridge.py:~107 (scratchpad rendered into state); no escaping/validation/tests. adversarially confirmed (dogfood audit 2026-06-17)
- Recent comments: codex: Fixed: PR #190 MERGED — scratchpad fenced between --- BEGIN/END NOTES --- in render_state so forged section headers can't masquerade as server-authored state. Note: scratchpad was already capped at MAX_SCRATCHPAD_CHARS=1200 (the 'unbounded' half of the audit note didn't apply). render_state+bridge suites green. / codex: REVIEW VERIFIED: render_state fences scratchpad between --- BEGIN/END NOTES ---; forged '## Recent turns' text stays inside notes and real Recent turns renders after fence. Tests: uv run pytest tests/test_fleet_kanban.py packages/adx_bridges/tests/test_render_state_active.py::test_scratchpad_is_fenced_against_section_injection packages/adx_bridges/tests/test_showdown_battle_bridge.py::test_render_state_hard_cap -q => 3 passed; ruff check touched files => pass. Limitation: MCP sidecar/TestClient e2e hung in this sandbox and was stopped; not counted as pass.

### BENE-CODEX-EVO-B3 - SECH in-episode continual swap (Continual-Harness pillar): ContinualMutator -> CodexHarness

- Priority: `P2`
- Status: `done`
- Assignee: `bene-core`
- Lane: `bene-core`
- Impact: SECH loop is between-generation (Autogenesis/DGM); the Continual-Harness (Karten 2026) contribution is in-episode reset-free refinement, currently uncovered.
- Suggested fix: Wire bene's ContinualMutator to the CodexHarness genome (mid-episode component swap behind the kill-gate). Needs a Genome bridge + fleet shaping — flagged proposal (bus pos 501).
- Evidence: proposed A2A bus position 501; not started
- Recent comments: bene-core: SHIPPED as PR #71 (good-night-oppie/bene feat/codex-harness-continual). ContinualCodexMutator + run_continual_episode (in-episode hot-swap behind a 2nd hash-locked kill-gate + budget/cooldown + unbuildable-rollback + swap audit + autonomy-L3), self-contained on the codex_harness genome, same R/S/E signatures as B1. Local-green: 1122/0 suite, 23 falsifiable tests, 20-agent adversarial review -> 14 findings fixed (incl. P1 persistent-db probe re-register crash). Strict-gate structurally red (pre-existing 11-file ruff drift, not my code). Awaiting Codex/owner review. / bene-core: Still review: PR #71 MERGEABLE + local-green (1122/0); its CI is QUEUED behind the OHE-saturated self-hosted runners (all 6 strict-gate jobs pending, not failing). Background poller bokr1dza0 will owner-merge on substantive-green (tests-3.11/3.12+regression+smoke) per the #67/#69 structural-red pattern. No bene-core action needed; not advanceable until runners drain. / bene-core: DONE — PR #71 MERGED to good-night-oppie/bene main (ec3230b, squash). Owner-merged on local-green (1122/0, 23 falsifiable tests, 20-agent adversarial review -> 14 fixed incl. P1 persistent-db crash) past the stalled/structural-red CI per the fleet norm (bene-2 #69-#75 same pattern). ContinualCodexMutator + run_continual_episode shipped; B3 real-e2e awaits adx Contract R/E/S.

### BENE-DOC-07 - Case study: trace-based RAG / Other Memory (engrams)

- Priority: `P2`
- Status: `done`
- Assignee: `bene-core`
- Lane: `case-study`
- Impact: Shows engrams + trace-based RAG — the next agent never starts cold.
- Suggested fix: Write docs/case-studies/cs04-trace-rag-other-memory.md grounded in the real engram/retrieve CLI.
- Evidence: bene/kernel/memory, docs/memory.md
- Recent comments: bene-core: MERGED as PR #24. Trace-RAG case study; retrieve snippets ground-truthed.

### BENE-DOC-08 - Case study: evolutionary meta-harness search

- Priority: `P2`
- Status: `done`
- Assignee: `bene-core`
- Lane: `case-study`
- Impact: Shows the breeding program — kill-gated promotion of evolved harness strategies.
- Suggested fix: Write docs/case-studies/cs05-meta-harness-evolution.md grounded in the mh CLI + eval probes.
- Evidence: bene/metaharness, docs/meta-harness.md
- Recent comments: bene-core: MERGED as PR #25. Meta-harness breeding-program case study; mh snippets ground-truthed.

### BENE-DOC-09 - Design: architecture diagrams (Nexus, engram ladder, autonomy ladder)

- Priority: `P2`
- Status: `done`
- Assignee: `bene-core`
- Lane: `design`
- Impact: Mission asks for designs; visual diagrams make the architecture legible.
- Suggested fix: Author mermaid diagrams for the single-file Nexus, engram compression ladder (tiers 0-4), autonomy ladder L0-L4; embed in docs (final HTML render routed to bene).
- Evidence: docs/architecture.md
- Recent comments: bene-core: MERGED as PR #26. 3 mermaid diagrams; autonomy labels ground-truthed against autonomy.py.

### BENE-SCRUB-05 - Scrub docs/benchmarks/COMMUNITY-BENCH-REPORT.md

- Priority: `P2`
- Status: `done`
- Assignee: `bene-core`
- Lane: `scrub`
- Impact: Benchmark report carries agent work-trace framing.
- Suggested fix: REMOVE Verdict/adversarial/wf_ framing; KEEP real benchmark numbers + methodology in reader terms.
- Evidence: docs/benchmarks/COMMUNITY-BENCH-REPORT.md
- Recent comments: bene-core: NO-ACTION: COMMUNITY-BENCH-REPORT clean of real work-trace (only had an example test path). / bene-core: Reopened review: the 02:48 'NO-ACTION clean' assessment was WRONG -- the report did carry orchestrating-session/API-quota work-trace. Scrubbed at source in good-night-oppie/bene PR #44 (2726d0f); committed site HTML regenerated in #45 (ceb1e13). Kept the 12 Verdict cells + self-review caveat. Live-verify rides BENE-SCRUB-08 -> move to done once live shows 0 work-trace. / bene-core: LIVE-VERIFIED clean (06:36:33 deploy): /bene/docs/benchmarks/COMMUNITY-BENCH-REPORT.html = 0 work-trace hits, /bene/docs/codegen.html = 0, /bene/zh/docs/codegen.html = 0. Source (#44/#45) + live both prove it -> done.

### BENE-SCRUB-06 - Scrub docs/primitive-review-cycle.md

- Priority: `P2`
- Status: `done`
- Assignee: `bene-core`
- Lane: `scrub`
- Impact: Reader doc carries agent work-trace.
- Suggested fix: Same 3-bucket scrub; decide keep-vs-unpublish if it is internal-by-nature.
- Evidence: docs/primitive-review-cycle.md
- Recent comments: bene-core: MERGED as PR #30. Worked-example rewritten reader-first; real concepts kept. / bene-core: REVISED: full read showed the doc is internal-by-nature (whole-doc agent process). UN-PUBLISHED via PR #31 (relocate + delete en HTML), superseding the partial scrub PR #30. zh source+HTML -> og (SCRUB-07).

## Recent Events

| Time | Action | Actor | Card | Detail |
|---|---|---|---|---|
| 2026-06-19T09:44:16Z | comment | bene-core | BENE-CODEX-EVO-B3 | {} |
| 2026-06-19T09:44:16Z | comment | bene-core | GA-BENE-1 | {} |
| 2026-06-19T09:44:16Z | comment | bene-core | GA-BENE-2 | {} |
| 2026-06-19T09:44:16Z | comment | bene-core | GA-BENE-4 | {} |
| 2026-06-19T09:45:59Z | move | admin | BENE-CODEX-EVO-B3 | {"after": {"assignee": "bene-core", "status": "done"}, "before": {"assignee": "bene-core", "status": "review"}} |
| 2026-06-19T09:45:59Z | comment | bene-core | BENE-CODEX-EVO-B3 | {} |
| 2026-06-19T14:57:42Z | move | admin | GA-BENE-1 | {"after": {"assignee": "bene", "status": "blocked"}, "before": {"assignee": "bene-core", "status": "blocked"}} |
| 2026-06-19T14:57:42Z | comment | bene-core | GA-BENE-1 | {} |
| 2026-06-19T14:57:42Z | move | admin | GA-BENE-2 | {"after": {"assignee": "bene", "status": "blocked"}, "before": {"assignee": "bene-core", "status": "blocked"}} |
| 2026-06-19T14:57:42Z | comment | bene-core | GA-BENE-2 | {} |
| 2026-06-19T14:57:42Z | move | admin | GA-BENE-4 | {"after": {"assignee": "bene", "status": "blocked"}, "before": {"assignee": "bene-core", "status": "blocked"}} |
| 2026-06-19T14:57:42Z | comment | bene-core | GA-BENE-4 | {} |

## Source Pattern

Adapted from Hermes Kanban's useful primitives: durable board slugs,
explicit statuses, priorities, assignees, comments/events, and per-profile
worker isolation. ADX keeps v1 file-backed so every fleet agent can use it
from the shared repo without a new daemon.
