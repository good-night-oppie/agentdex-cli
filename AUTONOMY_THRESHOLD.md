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
