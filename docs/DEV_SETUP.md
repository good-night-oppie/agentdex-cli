---
title: agentdex-cli developer setup
status: active
owner: etang
created: 2026-06-09
updated: 2026-06-09
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

# DEV_SETUP — agentdex-cli

> Doc-lint baseline (DOC-LINT-005 scaffolding).

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.11.x | `requires-python = ">=3.11,<3.14"` in `pyproject.toml` |
| uv | 0.11.x | workspace package manager (see CI pin in `.github/workflows/lint.yml`) |
| git | 2.39+ | subtree support for vendored `packages/kaos/` |
| claude CLI | latest | required for `adx_bridges.claude_bridge` live runs |
| codex CLI | 0.137.0+ | required for `adx_bridges.codex_bridge` live runs |
| 1Password CLI (`op`) | 2.x | secrets via `op read` per `agents/ops/AGENTS.md` |

Optional (M6+ live-pool):

| Tool | Version | Why |
|---|---|---|
| docker / docker-compose | 24+ | self-hosted Langfuse + helios daemon |
| camoufox python pkg | 0.4.x | `manus_bridge` primary driver; falls back to codex-web if missing |
| `kaos` CLI | 0.9.x | dream-consolidate sandbox + lineage queries |

## First-run setup

```bash
# 1. Clone + workspace install
git clone https://github.com/good-night-oppie/agentdex-cli.git
cd agentdex-cli
uv sync --group dev          # installs ruff + mypy + pre-commit + detect-secrets

# 2. Wire pre-commit hooks (G2 ep6 rails-in-code)
bash scripts/install_hooks.sh             # ruff + mypy + detect-secrets + sync_toc
bash scripts/install_doc_lint_precommit.sh # doc_lint.py --staged

# 3. Verify green tree
./tools/agent_senses/run_tests.sh         # canonical pytest invocation

# 4. Probe system shape
./tools/agent_senses/peek_metrics.sh

# 5. Run a mocked smoke expedition (M5 acceptance gate)
uv run --no-sync pytest packages/agentdex_cli/tests/test_expedition_smoke.py -v
```

## Env vars (declare here per `agents/ops/AGENTS.md`)

### Always required
- `OP_SERVICE_ACCOUNT_TOKEN` — 1Password service account; powers
  `op read` deferred-fetch in `~/.bashrc`.

### GitHub
- `GITHUB_TOKEN` — auto-loaded from 1Password
  `op://openclaw/gh-pat-europa-admin-no-delete/credential`. Bash
  tool inherits stale → prefix `gh` calls per
  `feedback_github_token_deferred_fetch` memory.

### Langfuse (Phase 4+)
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` — required for trace
  ingestion. Decorators no-op when unset (graceful degrade).
- `LANGFUSE_HOST` — defaults `http://localhost:3000` (self-host first
  per ADR-0009 §Amendment-2026-06-08).

### Anthropic / OpenAI (judge LLM)
- `ANTHROPIC_API_KEY` — required for live soft-Oracle judge.
- `OPENAI_API_KEY` — required if any baseline routes through OpenAI SDK.

### CLIProxy pool (optional)
- `CLIPROXY_BASE_URL` — when set, `llm_pool.client_for()` routes
  through the broker.
- `CLIPROXY_API_KEY` — pool auth.

## Common workflows

### Run the M5 smoke gate
```bash
./tools/agent_senses/run_tests.sh packages/agentdex_cli/tests/test_expedition_smoke.py
```

### Run a live Expedition (subscription CLIs required)
```bash
uv run adx expedition \
  --task nvidia-earnings-infographic \
  --baselines claude,codex,manus \
  --judge claude-haiku-4-5 \
  --output expeditions/$(date -u +%Y%m%d-%H%M%S)/
```

### Capture a bridge smoke fixture
```bash
bash tools/agent_senses/capture_bridge_smoke.sh claude
bash tools/agent_senses/capture_bridge_smoke.sh codex
bash tools/agent_senses/capture_bridge_smoke.sh manus
# → writes tests/fixtures/bridges/<bridge>_smoke.json
```

### Re-baseline detect-secrets
```bash
uv tool run --from detect-secrets==1.5.0 detect-secrets scan \
  --exclude-files '^(packages/kaos/|\.secrets\.baseline|expeditions/|\.supergoal/|\.git/|\.venv/|_attic/)' \
  > .secrets.baseline
git add .secrets.baseline
```

### Run the doctrine audit manually
```bash
bash cron/weekly_harness_audit.sh
# → writes sweeps/<DATE>-weekly-harness-audit.md
cat sweeps/$(date -u +%Y-%m-%d)-weekly-harness-audit.md
```

## Common failure modes

See `agents/debug/AGENTS.md` for the full list (7 modes documented).
Short-list:

1. Stale `GITHUB_TOKEN` inherited by Bash tool → inline `op read`.
2. GH007 push-block on `etang@qumulo.com` → use noreply
   `3278807+EdwardTang@users.noreply.github.com`.
3. `uv sync` doesn't install workspace members → use `uv sync
   --all-packages` on first sync.
4. detect-secrets `generated_at` timestamp drift → DEFERRED
   `BASELINE-DRIFT` row.

## Cross-references

- `agents/ops/AGENTS.md` — env vars + secrets + ports detail
- `agents/build/AGENTS.md` — build/test/lint commands
- `agents/debug/AGENTS.md` — failure modes + log locations
- `agents/review/AGENTS.md` — merge philosophy + auto-merge gates
- `IDEAL_EXPERIENCE.md` — what success looks like
- `EVAL.md` — eval gates + ground-truth dataset
