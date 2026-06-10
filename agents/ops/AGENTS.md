---
title: "agents/ops — agentdex-cli"
status: active
owner: "@EdwardTang"
created: 2026-06-08
updated: 2026-06-10
type: reference
scope: agents/ops
layer: cross-cutting
cross_cutting: true
---

# agents/ops — agentdex-cli

## Running

```bash
uv sync                                          # workspace install (post-M2)
uv run adx expedition --task <id> --baselines claude,codex,manus --judge claude-haiku-4.5  # main entry (post-M5)
uv run python -m pytest                          # all tests
uv run python -m pytest packages/agentdex_engine/tests/  # engine-only
uv run python -m pytest cards-mvp/test_schemas.py        # cards-mvp (pre-M2; uses cards-mvp/.venv)
```

Pre-M2 (before uv workspace lands):
```bash
cards-mvp/.venv/bin/python -m pytest cards-mvp/test_schemas.py
```

## Env vars (declare here — agent reads, doesn't grep)

### Always required
- `OP_SERVICE_ACCOUNT_TOKEN` — 1Password service account token. Powers deferred-fetch of `GITHUB_TOKEN` via `~/.bashrc` op-read pattern. **Never echo to transcript.** If unset, `gh` falls back to `hosts.yml` auth (degraded but works).
- `OP_DEFAULT_VAULT` — defaults to `openclaw`. Used by op-secrets-reader skill + bashrc deferred-fetch.

### GitHub
- `GITHUB_TOKEN` — auto-loaded from 1Password via `~/.bashrc`: `timeout 5 op read 'op://openclaw/gh-pat-europa-admin-no-delete/credential'`. Re-fetched per shell start; rotated PATs propagate without bashrc edit. **Non-interactive Bash inherits stale token from Claude Code launcher env — prefix `gh` calls with inline `export GITHUB_TOKEN="$(timeout 5 op read ...)"` (see memory `feedback-github-token-deferred-fetch.md`).**
- `GH_TOKEN` — mirror of `GITHUB_TOKEN`; `gh` checks both.

### Langfuse (observability — Phase 4+)
- `LANGFUSE_PUBLIC_KEY` — `pk-lf-*` form. Required for trace ingestion.
- `LANGFUSE_SECRET_KEY` — `sk-lf-*` form. Required for trace ingestion.
- `LANGFUSE_HOST` — defaults to `https://cloud.langfuse.com`. Override with self-hosted URL (`http://localhost:3000` for `docker run langfuse/langfuse` dev).
- If `LANGFUSE_PUBLIC_KEY` unset, `agentdex_observe` decorators no-op (`@trace_session`, `@trace_turn`) and `current_trace_url()` returns `None`. MVP runs without Langfuse if env unconfigured.

### Anthropic / OpenAI (judge LLM + bridges)
- `ANTHROPIC_API_KEY` — required for soft-Oracle judge call (`agentdex_observe.anthropic_client()`). Read from `op://openclaw/anthropic-api-key/credential` if not preset.
- `OPENAI_API_KEY` — required if any baseline routes through OpenAI SDK (post-MVP).

### Hermes runtime (Phase 4+, reframed phase-9)
- `HERMES_HOME` — defaults to `~/.hermes`. State dir for the Hermes process that loads the agentdex plugin (`hermes chat -t agentdex --yolo`). The `hermes gateway --profile agentdex` per-profile framing was pre-0.16 vapor (ADR-0009 §Amendment-2026-06-10); `AgentsRegistry` honors `HERMES_HOME` for `agents_registry.json`.

## Secrets (manifest, not contents)

| Secret | Source | Fetch pattern |
|---|---|---|
| `GITHUB_TOKEN` | 1Password `openclaw/gh-pat-europa-admin-no-delete` | bashrc deferred-fetch via `op read` |
| `OP_SERVICE_ACCOUNT_TOKEN` | bootstrapped by op-secrets-reader skill; bashrc-exported | `~/.bashrc` static export above non-interactive guard |
| `LANGFUSE_PUBLIC_KEY` / `SECRET_KEY` | 1Password `openclaw/langfuse-{pk,sk}` (TODO: confirm item names exist) | `op read` per-shell (same pattern as GITHUB_TOKEN) |
| `ANTHROPIC_API_KEY` | 1Password `openclaw/anthropic-api-key` | `op read` per-shell |

**Never commit secrets.** `.gitignore` covers `.env`, `.env.local`, `*.db*`. Verify with `git diff --cached` before any commit. See memory `feedback-github-token-deferred-fetch.md` for the inline-export pattern when shelling from Bash tool.

## Ports / endpoints

| Service | Port | Notes |
|---|---|---|
| Hermes chat runtime (`hermes chat -t agentdex`) | n/a (stdio session) | plugin tools registered in-process via `hermes_agent.plugins` entry-points; the pre-0.16 `gateway --profile` PID-file row was vapor (ADR-0009 §Amendment-2026-06-10) |
| Langfuse cloud | 443 (HTTPS) | `cloud.langfuse.com` |
| Langfuse self-hosted (optional) | 3000 | `docker run -p 3000:3000 langfuse/langfuse` |
| KAOS MCP server (optional, dev) | configurable; default 8742 | `kaos serve` — used for `mcp__kaos__*` tool calls in dev sessions |

## Live-run resolved git-author config

Commits to `good-night-oppie/*` must use noreply email format (`gh api users/EdwardTang --jq .id` returns `3278807`):
```bash
git -c user.name='Eddie Tang' -c user.email='3278807+EdwardTang@users.noreply.github.com' commit -m "..."
```
Personal `etang@qumulo.com` triggers GH007 push-block per email-privacy. See memory `feedback-git-email-noreply.md`.

**Do NOT `git config --global` per CLAUDE.md "NEVER update git config."** Use `-c` flags inline per commit.

## Supergoal harness state

- Active phase tracked in `.supergoal/STATE.md`
- Phase specs in `.supergoal/phases/phase-{1..8}.md`
- Plan-of-record: `.supergoal/ROADMAP.md` + `.supergoal/ARCHITECTURE.md` (amended 2026-06-08)
- Cron job `68ba3511` (every 10 min) runs `/harness-praxis` audit of process+progress until MVP done; cancel with `CronDelete 68ba3511` after `SUPERGOAL_RUN_COMPLETE`.
