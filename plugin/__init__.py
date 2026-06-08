"""Agentdex Hermes plugin entrypoint.

Hermes plugin lifecycle (hermes_cli/plugins.py):
  1. discover_plugins() walks bundled + ~/.hermes/plugins for plugin.yaml
  2. Imports the package
  3. Calls module.register(ctx: PluginContext) — THIS is where we install tools
  4. Calls hook callables (on_session_end etc) when events fire

`PluginContext.register_tool(name, toolset, schema, handler, ...)` writes into
the global tool registry so the main Hermes agent sees the tools immediately.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from registry.registry import AgentsRegistry, load_default_registry
from tools.register_subagent import (
    AGENTDEX_LIST_SUBAGENTS_SCHEMA,
    AGENTDEX_REGISTER_SUBAGENT_SCHEMA,
    handle_list_subagents,
    handle_register_subagent,
)
from tools.route_to_subagent import (
    AGENTDEX_ROUTE_TO_CLI_SCHEMA,
    AGENTDEX_ROUTE_TO_SUBAGENT_SCHEMA,
    handle_route_to_cli,
    handle_route_to_subagent,
)

log = logging.getLogger(__name__)

_REGISTRY: Optional[AgentsRegistry] = None


def _registry() -> AgentsRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = load_default_registry()
    return _REGISTRY


def register(ctx: Any) -> None:
    """Called once by Hermes after import. `ctx` is a PluginContext.

    See hermes_cli/plugins.py:289 PluginContext for the full surface.
    """
    reg = _registry()

    ctx.register_tool(
        name="agentdex_register_subagent",
        toolset="agentdex",
        schema=AGENTDEX_REGISTER_SUBAGENT_SCHEMA,
        handler=lambda args: handle_register_subagent(reg, args),
        description="Register a sub-agent or CLI bridge for @-routing",
        emoji="📒",
    )
    ctx.register_tool(
        name="agentdex_list_subagents",
        toolset="agentdex",
        schema=AGENTDEX_LIST_SUBAGENTS_SCHEMA,
        handler=lambda args: handle_list_subagents(reg, args),
        description="List registered sub-agents and CLI bridges",
        emoji="📋",
    )
    ctx.register_tool(
        name="agentdex_route_to_subagent",
        toolset="agentdex",
        schema=AGENTDEX_ROUTE_TO_SUBAGENT_SCHEMA,
        handler=lambda args: handle_route_to_subagent(reg, args),
        description="Send a prompt to a Hermes sub-agent via /v1/chat/completions",
        is_async=False,
        emoji="🛰️",
    )
    ctx.register_tool(
        name="agentdex_route_to_cli",
        toolset="agentdex",
        schema=AGENTDEX_ROUTE_TO_CLI_SCHEMA,
        handler=lambda args: handle_route_to_cli(reg, args),
        description="Send a prompt to a long-lived CLI bridge (claude/codex/gemini)",
        is_async=False,
        emoji="⛓️",
    )


def on_session_end(_session_meta: dict) -> None:
    """Hermes hook — declared in plugin.yaml provides_hooks. Persists stats."""
    _registry().flush()
