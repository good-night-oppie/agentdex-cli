# agents/review — agentdex-cli

## Merge philosophy (G2 ep5+7 — async, not sync-block)
- Lint + test gates are MANDATORY but run async — agent can open PR before human looks.
- Canary deploy / preview env runs on every PR; agent watches its own canary metrics.
- Human review is HIGH-LEVERAGE checkpoints (research, plan) not every commit.

## Auto-merge criteria
- All required CI checks green
- No HIGH-severity `agentlint scan` findings
- Coverage delta >= 0
- TODO: project-specific

## Escalation path
- TODO: when does agent stop + ping human?
