"""agentdex_plugin.tools — Hermes tool schemas + handlers (phase-9).

PR-B ships ``agentdex_run_expedition``; PR-C forwards these (plus the
``agentdex_cli.tools`` registry handlers) to ``ctx.register_tool``.
"""

from agentdex_plugin.tools.run_expedition import (
    AGENTDEX_RUN_EXPEDITION_SCHEMA,
    handle_run_expedition,
    handle_run_expedition_sync,
)

__all__ = [
    "AGENTDEX_RUN_EXPEDITION_SCHEMA",
    "handle_run_expedition",
    "handle_run_expedition_sync",
]
