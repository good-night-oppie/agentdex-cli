"""agentdex_cli — adx CLI shell + orchestrator (drives 1 hermes gateway via HTTP).

Per ADR-0008 §Amendment-2026-06-08 (single-gateway embedded mode) + ADR-0009 §D3
(retrofit framing on Hermes 0.15.1), this package ships:
- adx CLI entry-point (cli.py::main; post-M5)
- orchestrator/gateway.py (ensure_gateway + discover_gateway + GatewayHandle; M2)
- orchestrator/expedition.py (run_expedition_orchestrator; M5)
- observe/ (trace tail panel + /events command; post-M5)
- release/ (helios seed → KAOS promotion; post-M6)
"""

from __future__ import annotations

__version__ = "0.1.0"
