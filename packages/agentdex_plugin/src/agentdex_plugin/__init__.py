"""agentdex_plugin — Hermes plugin entry-point.

Per ADR-0008 §Amendment-2026-06-08 (single-gateway embedded mode) + co-opetition
reframe 2026-06-08 (battle framing dropped per user direction; system is
co-opetition 合作竞争 of subscription-CLI baselines, not adversarial battle).

This plugin loads ONCE into the long-lived `hermes gateway --profile agentdex`
subprocess via entry-point group `hermes_agent.plugins`. M2 phase-4 ships the
entry-point + register() surface so plugin discovery via `hermes plugins list`
(or entry-points fallback) returns 'agentdex'. The full tool/command/hook
implementations land at M3-M5.

Legacy PHASE-3.0 scaffold (full tool wiring against registry.registry +
tools.register_subagent + tools.route_to_subagent) was scoped to the pre-M2
flat-layout. With the M2 workspace restructure those imports moved to
`agentdex_cli.{registry,tools}`. M3 phase-5 rewires the tool handlers
against the new package paths. M2 ships the minimal discoverable surface.
"""

from __future__ import annotations

from typing import Any


def register(ctx: Any = None) -> dict[str, Any]:
    """Register agentdex_plugin into a Hermes PluginContext.

    M2 stub: returns the registration manifest so the plugin appears in
    `hermes plugins list`. Tool/command/hook registrations land at M3-M5.

    Args:
        ctx: hermes_cli.plugins.PluginContext instance. May be None during
            entry-point discovery (no PluginContext provided).

    Returns:
        Registration manifest dict with plugin name, kind, version, and
        feature-list. Used by Hermes for plugin-list rendering.
    """
    return {
        "name": "agentdex",
        "kind": "standalone",
        "version": "0.1.0",
        "description": "agentdex-cli plugin: Card pipeline + bridge tools + KAOS memory provider (co-opetition framing per ADR-0009)",
        "tools": [
            "agentdex_run_expedition",      # M5
            "agentdex_route_to_subagent",   # M3
            "agentdex_list_subagents",      # M3
            "agentdex_register_subagent",   # M3
        ],
        "commands": [
            "/events",       # M5
            "/expedition",   # M5
        ],
        "hooks": [
            "on_session_end",        # M5 Kanban poller
            "on_request_received",   # M4 R3 spike trace-propagation hook
        ],
        "memory_provider": "kaos_exclusive",  # M5
        "milestone_status": "M2-stub-discovery-only",
    }


def on_session_end(_session_meta: dict) -> None:
    """Hermes hook — declared in plugin.yaml provides_hooks. M5 wires Kanban poller."""
    pass


__all__ = ["register", "on_session_end"]
