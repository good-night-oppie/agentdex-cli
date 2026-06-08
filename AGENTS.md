# AGENTS.md — agentdex-cli

Single-screen index for any AI coding agent (Claude Code / Codex / Cursor / Aider) operating in this repo. **Lazy-load** the modular files in `agents/` for area-specific context. Do NOT paste this file into the agent — it reads it on its own.

> Maintained per OpenAI G2 Harness Engineering pattern (lazy-load > monolith) and Anthropic G9 3-round prune method. See `~/gh/harness-engineering/glossary.md` for source-paper citations.

## Anchor docs (read in order on cold start)
1. `IDEAL_EXPERIENCE.md` — what success looks like for users of agentdex-cli (G14 Cursor anchor)
2. `EVAL.md` — eval signal + ground-truth gate (G13 LangChain)
3. `AUTONOMY_THRESHOLD.md` — when human review drops (G2 ep6)

## Modular agent contexts (lazy-load by area)
- `agents/ops/AGENTS.md` — running, env vars, secrets, ports
- `agents/build/AGENTS.md` — build/test/lint commands, deps
- `agents/review/AGENTS.md` — PR / merge philosophy (async gates, G2 ep5+7)
- `agents/debug/AGENTS.md` — failure modes, log locations, sense tools

## Agent senses (run, don't guess)
```bash
./tools/agent_senses/run_tests.sh          # canonical test command + parse
./tools/agent_senses/tail_logs.sh <area>   # peek recent logs without flooding context
./tools/agent_senses/peek_metrics.sh       # latest perf / coverage / size deltas
```
Per G2 ep4: agents that only write are blind; senses are the read-back loop.

## Hard rails (architecture as code, not docs)
- `ruff` + `mypy --strict` configured in `pyproject.toml`
- Pre-commit hook in `.pre-commit-config.yaml` (when present)
- CI gate: see `.github/workflows/` — async-style (G2 ep7), does not sync-block agent throughput.

## What NOT to do (G2 ep3 failure modes)
- Don't grow this file > 200 lines — split into `agents/<area>/`.
- Don't put architecture rules in prose only — encode in lint/types/tests.
- Don't block agent loop on synchronous human review — use canary + async gate.
- Don't hardcode runtime rules that the agent could learn (G11 Browser Use bitter lesson).

## Provenance
- Pattern source: OpenAI "Harness engineering: leveraging Codex in an agent-first environment" (eps 03-09 in harness-engineering corpus)
- Generated: 2026-06-07 by `scaffold_openai_dev_env.sh`
## Permissions (manifest — agentlint OBS-002)
```yaml
permissions:
  filesystem:
    read:  ["**/*"]
    write: ["src/**", "tests/**", "agents/**", "docs/**", "agentdex-cli/**", "./*.md", ".github/**"]
  shell:
    enabled: true
    allowed_commands:
      - "./tools/agent_senses/run_tests.sh"
      - "./tools/agent_senses/tail_logs.sh"
      - "./tools/agent_senses/peek_metrics.sh"
  network:
    outbound: false
```
