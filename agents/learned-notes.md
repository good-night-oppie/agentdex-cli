---
title: "Learned user preferences + workspace facts"
status: active
owner: "@EdwardTang"
created: 2026-06-10
updated: 2026-06-10
type: reference
scope: agents
layer: cross-cutting
cross_cutting: true
---

# Learned user preferences + workspace facts

Predecessor-session learnings promoted out of the AGENTS.md index
(DOC-LINT-021 prose budget) into this linked note.

## Learned User Preferences

- MCP config JSON uses `${VAR}` placeholders; load secrets via `~/.cursor/mcp-secrets.sh` sourced from `~/.bashrc` before the interactive-only guard (so non-interactive `bash -lc` MCP spawns receive env).
- Apply the same `${VAR}` + `mcp-secrets.sh` pattern to `~/.cursor/mcp.json`, `~/.claude.json`, and `~/.claude/settings.json`.
- Claude Code requires `CLAUDE_CODE_MCP_ALLOWLIST_ENV=1` in settings for MCP env `${VAR}` flattening.
- Retrieve secrets via the 1Password `op` CLI (vault `openclaw`, service account via `OP_SERVICE_ACCOUNT_TOKEN`) instead of pasting raw keys into configs or chat.
- User communicates bilingually (Chinese/English); for prep or summary docs he sometimes asks for interleaved 中文 + English in one document.
- User delegates long-running work to named tmux sessions (e.g. `harness-3`, `helios-fix`) and asks agents to check or babysit them via the terminals folder.

## Learned Workspace Facts

- `/home/admin/gh` is a multi-repo workspace root (not a single git repo); nested projects each have their own `.git`.
- Root Cursor ignore: only `.cursorindexingignore` (excludes `.specstory/**` from indexing); no root `.cursorignore`.
- Serena MCP binary: `/home/admin/.local/share/uv/tools/serena-agent/bin/serena` (symlink at `/home/admin/gh/bin/serena`); use `--open-web-dashboard false` for headless Cursor.
- User owns the domain `oppie.xyz`; ngrok reserved subdomains (e.g. `cliproxy.oppie.xyz`) front local services such as the CLI proxy API for custom models on `localhost:8317`.
- User identity for resumes/recommendations: Eddie Tang (唐永冰); personal GitHub org `good-night-oppie` (ionq, helios repos).
