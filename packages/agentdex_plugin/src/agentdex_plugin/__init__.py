"""agentdex_plugin — Hermes plugin entry-point.

Per ADR-0008 §Amendment-2026-06-08 (single-gateway embedded mode) + co-opetition
reframe 2026-06-08 (battle framing dropped per user direction; system is
co-opetition 合作竞争 of subscription-CLI baselines, not adversarial battle).

This plugin loads ONCE into the long-lived Hermes process via entry-point
group `hermes_agent.plugins`. Phase-9 PR-C wires the real tool surface:
`register(ctx)` forwards 5 tools to `ctx.register_tool` under
`toolset="agentdex"`, flipping `milestone_status` from
`M2-stub-discovery-only` to `M5-tools-wired`. The autonomous-driver
surface is `hermes chat -t agentdex --yolo` (the pre-0.16
`hermes gateway --profile agentdex` framing was vapor — see HANDOFF.md
doctrine-drift #1, queued for PR-D).

When `ctx` is None (entry-point discovery, `hermes plugins list`),
`register` stays side-effect-free and just returns the manifest.
"""

from __future__ import annotations

from functools import partial
from typing import Any


def register(ctx: Any = None) -> dict[str, Any]:
    """Register agentdex_plugin into a Hermes PluginContext.

    Args:
        ctx: hermes_cli.plugins.PluginContext instance. May be None during
            entry-point discovery (no PluginContext provided) — in that case
            no tool registration happens and only the manifest is returned.

    Returns:
        Registration manifest dict with plugin name, kind, version, and
        feature-list. Used by Hermes for plugin-list rendering.
    """
    manifest: dict[str, Any] = {
        "name": "agentdex",
        "kind": "standalone",
        "version": "0.2.0",
        "description": (
            "agentdex-cli plugin: Card pipeline + bridge tools + KAOS memory "
            "provider (co-opetition framing per ADR-0009)"
        ),
        "tools": [
            "agentdex_run_expedition",  # M5 chain (PR-B)
            "agentdex_register_subagent",  # registry (PR-A rewire)
            "agentdex_list_subagents",
            "agentdex_route_to_subagent",
            "agentdex_route_to_cli",
        ],
        "commands": [
            "/events",  # M6+
            "/expedition",  # M6+
        ],
        "hooks": [
            "on_session_end",  # M6+ Kanban poller (declared, not yet wired — PR-D honesty)
        ],
        "memory_provider": "kaos_exclusive",  # M6+
        "milestone_status": "M5-tools-wired",
    }

    if ctx is None or not hasattr(ctx, "register_tool"):
        return manifest

    from agentdex_cli.registry.registry import AgentsRegistry
    from agentdex_cli.tools.register_subagent import (
        AGENTDEX_LIST_SUBAGENTS_SCHEMA,
        AGENTDEX_REGISTER_SUBAGENT_SCHEMA,
        handle_list_subagents,
        handle_register_subagent,
    )
    from agentdex_cli.tools.route_to_subagent import (
        AGENTDEX_ROUTE_TO_CLI_SCHEMA,
        AGENTDEX_ROUTE_TO_SUBAGENT_SCHEMA,
        handle_route_to_cli,
        handle_route_to_subagent,
    )

    from agentdex_plugin.tools import (
        AGENTDEX_RUN_EXPEDITION_SCHEMA,
        handle_run_expedition,
    )

    registry = AgentsRegistry()  # honors HERMES_HOME; one instance shared by handlers

    sync_tools = [
        (AGENTDEX_REGISTER_SUBAGENT_SCHEMA, partial(handle_register_subagent, registry)),
        (AGENTDEX_LIST_SUBAGENTS_SCHEMA, partial(handle_list_subagents, registry)),
        (AGENTDEX_ROUTE_TO_SUBAGENT_SCHEMA, partial(handle_route_to_subagent, registry)),
        (AGENTDEX_ROUTE_TO_CLI_SCHEMA, partial(handle_route_to_cli, registry)),
    ]
    for schema, handler in sync_tools:
        ctx.register_tool(
            name=schema["name"],
            toolset="agentdex",
            schema=schema,
            handler=handler,
            is_async=False,
            description=schema["description"],
        )

    ctx.register_tool(
        name=AGENTDEX_RUN_EXPEDITION_SCHEMA["name"],
        toolset="agentdex",
        schema=AGENTDEX_RUN_EXPEDITION_SCHEMA,
        handler=handle_run_expedition,
        is_async=True,  # full Expedition awaits bridges sequentially
        description=AGENTDEX_RUN_EXPEDITION_SCHEMA["description"],
    )

    return manifest


def on_session_end(_session_meta: dict) -> None:
    """Hermes hook — declared in plugin.yaml provides_hooks. M6+ wires Kanban poller."""
    pass


__all__ = ["register", "on_session_end"]
