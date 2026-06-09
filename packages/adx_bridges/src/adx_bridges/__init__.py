"""adx_bridges — long-lived subscription-CLI bridges (Claude Code, Codex, Manus).

Each bridge exposes the contract from :class:`adx_bridges.base.LongRunningCliBridge`
plus the Phase-5 :meth:`send` wrapper which returns ``(text, langfuse_trace_id|None)``.

Async co-opetition (ADR-0009 §Amendment-2026-06-08): bridges are per-baseline async
actors invoked from the orchestrator's sequential loop — they do NOT race in
real-time against each other.
"""

from adx_bridges.base import (
    BridgeConfig,
    CliDead,
    JsonRpcServer,
    LongRunningCliBridge,
    new_session_id,
    run_bridge,
)

__all__ = [
    "BridgeConfig",
    "CliDead",
    "JsonRpcServer",
    "LongRunningCliBridge",
    "new_session_id",
    "run_bridge",
    "build_bridge",
]


def build_bridge(
    name: str,
    *,
    workdir: str | None = None,
    extra: dict | None = None,
) -> LongRunningCliBridge:
    """Factory: name ∈ {claude, codex, codex-web, manus, gemini}."""
    import os

    workdir = workdir or os.getcwd()
    extra = extra or {}

    if name == "claude":
        from adx_bridges.claude_bridge import ClaudeBridge

        sid = new_session_id()
        cfg = BridgeConfig(
            name="claude",
            workdir=workdir,
            cli_argv=ClaudeBridge.build_argv(sid, extra),
        )
        bridge = ClaudeBridge(cfg)
        bridge.current_session_id = sid
        return bridge
    if name == "codex":
        from adx_bridges.codex_bridge import CodexBridge

        cfg = BridgeConfig(
            name="codex",
            workdir=workdir,
            cli_argv=CodexBridge.build_argv(),
        )
        return CodexBridge(cfg)
    if name in ("codex-web", "codex_web"):
        from adx_bridges.codex_web_bridge import CodexWebBridge

        cfg = BridgeConfig(name="codex-web", workdir=workdir, cli_argv=[])
        return CodexWebBridge(cfg)
    if name == "manus":
        from adx_bridges.manus_bridge import make_manus_bridge

        return make_manus_bridge(BridgeConfig(name="manus", workdir=workdir, cli_argv=[]))
    if name == "gemini":
        from adx_bridges.gemini_bridge import GeminiBridge

        cfg = BridgeConfig(name="gemini", workdir=workdir, cli_argv=[])
        return GeminiBridge(cfg)
    raise ValueError(f"unknown bridge name: {name!r}")
