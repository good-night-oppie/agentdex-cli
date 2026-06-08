# agents/build — agentdex-cli (post-M2 uv workspace)

> Populated 2026-06-08 (Phase 4 M2 fix-S1).

## Commands

### Workspace sync (REQUIRED `--all-packages` on first run)
```bash
uv sync --all-packages
uv sync
```

### Tests
```bash
uv run python -m pytest
uv run python -m pytest packages/agentdex_engine/tests/
uv run python -m pytest packages/agentdex_cli/tests/
```

### Sanity-check imports
```bash
uv run python -c "import kaos, agentdex_engine, agentdex_plugin, adx_bridges, helios_client, agentdex_observe; print("OK")"
uv run python -c "from agentdex_observe import init_langfuse, anthropic_client, openai_client, trace_session, trace_turn, current_trace_url; print("OK")"
uv run python -c "from agentdex_cli.orchestrator.gateway import ensure_gateway, discover_gateway, GatewayHandle; print("OK")"
```

### Hermes plugin discovery
```bash
uv run python -c "from importlib.metadata import entry_points; print("agentdex" in [e.name for e in entry_points(group="hermes_agent.plugins")])"
```

## Dep update policy

- Exact-pin upstream-volatile deps (Langfuse, hermes-agent, OpenAI/Anthropic SDKs)
- Range-pin stable deps (pydantic>=2.0, pyyaml>=6.0, blake3>=0.4)
- KAOS subtree: quarterly pull
- Hermes pin: hermes-agent>=0.15.1
- Langfuse pin: langfuse>=4.7,<5.0

## Build artifacts

- dist/*.whl
- .venv/ (gitignored)
- uv.lock (committed)
