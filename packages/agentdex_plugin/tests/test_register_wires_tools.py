"""PR-C — register(ctx) forwards the 5-tool surface to ctx.register_tool."""

from __future__ import annotations

import asyncio


class _StubCtx:
    """Captures register_tool calls the way hermes_cli.plugins.PluginContext would."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def register_tool(self, **kwargs) -> None:
        self.calls.append(kwargs)


EXPECTED_TOOLS = {
    "agentdex_run_expedition",
    "agentdex_register_subagent",
    "agentdex_list_subagents",
    "agentdex_route_to_subagent",
    "agentdex_route_to_cli",
}


def _registered_ctx(monkeypatch, tmp_path) -> _StubCtx:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))  # registry file lands in tmp
    from agentdex_plugin import register

    ctx = _StubCtx()
    manifest = register(ctx)
    assert manifest["milestone_status"] == "M5-tools-wired"
    return ctx


def test_register_none_ctx_is_pure_manifest() -> None:
    from agentdex_plugin import register

    manifest = register(None)
    assert manifest["name"] == "agentdex"
    assert set(manifest["tools"]) == EXPECTED_TOOLS
    assert manifest["milestone_status"] == "M5-tools-wired"


def test_register_wires_five_tools(monkeypatch, tmp_path) -> None:
    ctx = _registered_ctx(monkeypatch, tmp_path)
    assert {c["name"] for c in ctx.calls} == EXPECTED_TOOLS
    assert all(c["toolset"] == "agentdex" for c in ctx.calls)
    assert all(c["description"] for c in ctx.calls)


def test_async_and_sync_tool_flags(monkeypatch, tmp_path) -> None:
    ctx = _registered_ctx(monkeypatch, tmp_path)
    async_flags = {c["name"]: c["is_async"] for c in ctx.calls}
    assert async_flags["agentdex_run_expedition"] is True
    assert async_flags["agentdex_route_to_subagent"] is True
    assert async_flags["agentdex_route_to_cli"] is True
    assert async_flags["agentdex_register_subagent"] is False
    assert async_flags["agentdex_list_subagents"] is False

    for name in ["agentdex_run_expedition", "agentdex_route_to_subagent", "agentdex_route_to_cli"]:
        handler = next(c["handler"] for c in ctx.calls if c["name"] == name)
        assert asyncio.iscoroutinefunction(handler)


def test_registry_handlers_share_one_registry(monkeypatch, tmp_path) -> None:
    import json

    ctx = _registered_ctx(monkeypatch, tmp_path)
    by_name = {c["name"]: c["handler"] for c in ctx.calls}

    out_raw = by_name["agentdex_register_subagent"](
        {"name": "probe", "kind": "cli", "bridge_port": 49999}
    )
    out = json.loads(out_raw)
    assert out["ok"] is True

    listed_raw = by_name["agentdex_list_subagents"]({})
    listed = json.loads(listed_raw)
    assert [a["name"] for a in listed["agents"]] == ["probe"]
