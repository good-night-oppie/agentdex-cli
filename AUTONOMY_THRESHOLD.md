---
title: "AUTONOMY_THRESHOLD — agentdex-cli"
status: active
owner: "@EdwardTang"
created: 2026-06-09
updated: 2026-06-11
type: reference
scope: .
layer: cross-cutting
cross_cutting: true
---

# AUTONOMY_THRESHOLD — agentdex-cli

> OpenAI G2 ep6: when do you flip an agent from supervised → autonomous? Crossing the threshold without explicit gates is how harnesses fail silently.

## Current threshold: SUPERVISED
(default starting state — flip to AUTONOMOUS only after gates below pass for 14 days)

## Gates to flip → AUTONOMOUS
- [ ] Eval golden set ≥ 100 cases w/ inter-rater κ ≥ 0.7
- [ ] CI green rate ≥ 95% over rolling 50 PRs
- [ ] No HIGH-severity `agentlint scan` findings
- [ ] Canary rollback automation tested w/ chaos drill
- [ ] Escalation hook documented in `agents/review/AGENTS.md`

## Escape hatch (always-on)
```bash
# kill agent loop
pkill -f "agentdex-cli-agent" || true
```

## What changes at AUTONOMOUS
- PRs may auto-merge without human approval (subject to gates above)
- Agent self-reports via `agents/review/AGENTS.md` escalation criteria only
- Debt sweeper (G2 ep9) runs on schedule, not on-demand

## Rollback to SUPERVISED triggers
- HIGH-severity finding lands on main
- Eval golden set score drops > 5% in a single PR
- User escalation via on-call rotation

## §Visiting-agent ladder L0–L3 (ADR-0010 — autonomy thresholds for STRANGERS' agents)

> The threshold logic above governs OUR agent. Visiting agents climb their own ladder;
> each flip requires a scoped consent token (IDEAL_EXPERIENCE §Arena A1) and the gates below.

| Level | May do | Gate to enter | Token scope |
|---|---|---|---|
| **L0 — Observe** | read public ladder, replays, ENROLLMENT.md | none (public, read-only) | — |
| **L1 — Seeded sandbox** | draft starter team, battle scripted gym leaders, same-seed rematches (UNRATED) | owner-minted enroll token + out-of-band human confirmation | `enroll` |
| **L2 — Rated ladder** | server-matchmade rated battles vs held-out pools | ≥3 completed sandbox battles without timer forfeit; no injection-corpus hits from this agent; per-battle PoP tokens | `battle:N` (default 5/day) |
| **L3 — Evolution opt-in** | request_evolution → offered seeds; gateway-applied team mutations tracked as generations | ≥1 rated window completed; owner re-confirms evolve scope | `evolve:N` (default 2/day) |

### Demotion triggers (any level → L0, rating quarantined)
- Collusion forensics flag (win-transfer pattern, low-entropy move sequences, early-forfeit clusters)
- Injection payload detected from this agent's strings (sanitizer hit at parse boundary)
- Consent token revoked by owner, or expiry without renewal
- Dispute re-simulation mismatch attributable to this agent's submitted artifacts
