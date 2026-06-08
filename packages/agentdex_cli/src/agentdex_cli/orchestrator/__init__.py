"""orchestrator — gateway lifecycle + Expedition driver.

Public surface:
- ensure_gateway, discover_gateway, GatewayHandle from `orchestrator.gateway`
- run_expedition_orchestrator from `orchestrator.expedition` (post-M5)
"""

from agentdex_cli.orchestrator.gateway import GatewayHandle, discover_gateway, ensure_gateway

__all__ = ["GatewayHandle", "discover_gateway", "ensure_gateway"]
