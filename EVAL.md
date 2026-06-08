# EVAL — agentdex-cli

> LangChain G13: eval signal design is the hardest part of harness engineering. Bad signal → automated optimization amplifies error. Every criterion below MUST trace to a line in `IDEAL_EXPERIENCE.md`.

## Ground-truth dataset
- Location: `tests/golden/` (TODO: populate)
- Curation policy: human-labeled, versioned, append-only
- Size target: ≥10 cases for smoke, ≥100 for confidence

## Eval criteria
| Criterion | Anchor (IDEAL_EXPERIENCE.md line) | Signal | GT source |
|-----------|-----------------------------------|--------|-----------|
| TODO      | TODO                              | TODO   | TODO      |

## Self-judge guardrails (G13)
- NO LLM-judges-LLM without ground-truth anchor
- Inter-rater agreement > 0.7 required before promoting eval to gate

## Eval gating
- PR cannot auto-merge if eval score drops on golden set
- See `agents/review/AGENTS.md` for merge policy

## Ablation evidence (G9 Anthropic Prithvi)
Every harness component must have ablation justification — "if we remove X, eval Y drops by Z". Components without ablation evidence are candidates for pruning.
| Component | Ablation result | Keep? |
|-----------|-----------------|-------|
| TODO      | TODO            | TODO  |
