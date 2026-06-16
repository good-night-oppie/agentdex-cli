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
| ADX-P2-001 | P2 | codex | agent-ux | Reduce starter and CLI footguns for visiting agents | pass14, pass15, pass16, pass29 |
| ADX-P2-002 | P2 | codex | gameplay | Make arena gameplay feedback more legible and less first-legal | pass2, pass3, pass4, pass6, pass7, pass8, pass12, pass13 |

### todo

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| ADX-P1-001 | P1 | adx-cli | fairness | Stop spending rated/evolution/badge quota before work is accepted | pass26, pass33, pass34, pass35, pass36 |
| ADX-P1-002 | P1 | adx-cli | owner-data | Make owner export include replay, badge, and rating lineage | pass17, pass19, pass20, pass21, pass41, pass42-candidate |
| ADX-P1-003 | P1 | harness | observability | Make observability acceptance fail when traces are absent | pass31, pass32 |
| ADX-P1-004 | P1 | adx-cli | security | Tighten admin surface and auth-before-parse contract | pass24, pass25 |

### ready

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| ADX-P0-001 | P0 | adx-cli | integrity | Make arena receipts atomic before claiming honesty | pass27, pass28, pass37, pass38, pass39, pass40 |

### done

| ID | Pri | Assignee | Lane | Title | Evidence |
|---|---|---|---|---|---|
| ADX-P2-003 | P2 | harness | regression-guard | Preserve verified strengths while fixing gaps | pass5, pass11, pass22, pass23, pass30 |

## Card Detail

### ADX-P0-001 - Make arena receipts atomic before claiming honesty

- Priority: `P0`
- Status: `ready`
- Assignee: `adx-cli`
- Lane: `integrity`
- Impact: Human owner and agent both receive durable receipts that can be false or partial when EventLog, sidecar, or rating writes fail.
- Suggested fix: Group side effects behind an atomic write plan: validate and reserve first, then commit event/replay/rating/badge together or compensate visibly.
- Evidence: pass27, pass28, pass37, pass38, pass39, pass40

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

### ADX-P2-001 - Reduce starter and CLI footguns for visiting agents

- Priority: `P2`
- Status: `triage`
- Assignee: `codex`
- Lane: `agent-ux`
- Impact: Agents hit stale docs, missing `adx` arena commands, traceback setup errors, and asymmetric MCP proxy behavior.
- Suggested fix: Update `/skill.md`, add or explicitly defer `adx arena` commands, normalize starter-kit errors, and test missing battle IDs.
- Evidence: pass14, pass15, pass16, pass29

### ADX-P2-002 - Make arena gameplay feedback more legible and less first-legal

- Priority: `P2`
- Status: `triage`
- Assignee: `codex`
- Lane: `gameplay`
- Impact: Agents can win or lose for shallow reasons and cannot always understand losses from state/replay alone.
- Suggested fix: Repair gym mapping, expose opponent HP/recent turns, enrich replay metadata, and test anchor/gym coverage.
- Evidence: pass2, pass3, pass4, pass6, pass7, pass8, pass12, pass13

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
| 2026-06-16T20:14:58Z | seed | codex |  | {"cards": 8} |
| 2026-06-16T20:14:58Z | init | codex |  | {"force": true} |

## Source Pattern

Adapted from Hermes Kanban's useful primitives: durable board slugs,
explicit statuses, priorities, assignees, comments/events, and per-profile
worker isolation. ADX keeps v1 file-backed so every fleet agent can use it
from the shared repo without a new daemon.
