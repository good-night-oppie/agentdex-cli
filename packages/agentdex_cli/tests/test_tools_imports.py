"""Smoke test — tools/ modules import cleanly post flat-layout rewire (PR-A).

The M2 workspace restructure moved `registry.registry` →
`agentdex_cli.registry.registry`. The tools/ modules kept the flat-layout
imports and were dead code until phase-9 PR-A. This smoke guards the rewire:
every schema + handler must be importable, schemas must carry the OpenAI
tool-schema shape `register(ctx)` will forward to Hermes (PR-C).
"""

from __future__ import annotations


def test_register_subagent_module_imports() -> None:
    from agentdex_cli.tools.register_subagent import (
        AGENTDEX_LIST_SUBAGENTS_SCHEMA,
        AGENTDEX_REGISTER_SUBAGENT_SCHEMA,
        handle_list_subagents,
        handle_register_subagent,
    )

    assert AGENTDEX_REGISTER_SUBAGENT_SCHEMA["name"] == "agentdex_register_subagent"
    assert AGENTDEX_LIST_SUBAGENTS_SCHEMA["name"] == "agentdex_list_subagents"
    assert callable(handle_register_subagent)
    assert callable(handle_list_subagents)


def test_route_to_subagent_module_imports() -> None:
    from agentdex_cli.tools.route_to_subagent import (
        AGENTDEX_ROUTE_TO_CLI_SCHEMA,
        AGENTDEX_ROUTE_TO_SUBAGENT_SCHEMA,
        handle_route_to_cli,
        handle_route_to_subagent,
    )

    assert AGENTDEX_ROUTE_TO_SUBAGENT_SCHEMA["name"] == "agentdex_route_to_subagent"
    assert AGENTDEX_ROUTE_TO_CLI_SCHEMA["name"] == "agentdex_route_to_cli"
    assert callable(handle_route_to_subagent)
    assert callable(handle_route_to_cli)


def test_schemas_carry_openai_tool_shape() -> None:
    """register(ctx) (PR-C) forwards these dicts as Hermes tool schemas."""
    from agentdex_cli.tools import register_subagent, route_to_subagent

    schemas = [
        register_subagent.AGENTDEX_REGISTER_SUBAGENT_SCHEMA,
        register_subagent.AGENTDEX_LIST_SUBAGENTS_SCHEMA,
        route_to_subagent.AGENTDEX_ROUTE_TO_SUBAGENT_SCHEMA,
        route_to_subagent.AGENTDEX_ROUTE_TO_CLI_SCHEMA,
    ]
    for schema in schemas:
        assert isinstance(schema["name"], str) and schema["name"]
        assert isinstance(schema["description"], str) and schema["description"]
        assert schema["parameters"]["type"] == "object"


def test_handlers_roundtrip_against_tmp_registry(tmp_path) -> None:
    from agentdex_cli.registry.registry import AgentsRegistry
    from agentdex_cli.tools.register_subagent import (
        handle_list_subagents,
        handle_register_subagent,
    )

    registry = AgentsRegistry(path=tmp_path / "registry.json")
    out = handle_register_subagent(
        registry,
        {
            "name": "claude-bridge",
            "kind": "cli",
            "capabilities": ["coding"],
            "bridge_port": 49801,
            "session_token": "sk-secret",  # pragma: allowlist secret
        },
    )
    assert out["ok"] is True
    assert out["agent"]["session_token"] == "***"  # masked

    listed = handle_list_subagents(registry, {})
    assert [a["name"] for a in listed["agents"]] == ["claude-bridge"]
    listed_cap = handle_list_subagents(registry, {"capability": "coding"})
    assert len(listed_cap["agents"]) == 1
