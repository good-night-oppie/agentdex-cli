"""Tool: register a sub-agent (Hermes profile) or CLI bridge in the registry."""

from __future__ import annotations

from agentdex_cli.registry.registry import AgentsRegistry, SubAgent

AGENTDEX_REGISTER_SUBAGENT_SCHEMA = {
    "name": "agentdex_register_subagent",
    "description": (
        "Register a sub-agent or CLI bridge so the main agent can @-route tasks to it. "
        "Use kind='hermes-agent' for another Hermes profile reachable over its dashboard HTTP API. "
        "Use kind='cli' for a long-lived CLI bridge (e.g. claude/codex/gemini bridges)."
    ),
    "parameters": {
        "type": "object",
        "required": ["name", "kind"],
        "properties": {
            "name": {"type": "string"},
            "kind": {"type": "string", "enum": ["hermes-agent", "cli"]},
            "description": {"type": "string"},
            "capabilities": {"type": "array", "items": {"type": "string"}},
            "base_url": {"type": "string"},
            "session_token": {"type": "string"},
            "bridge_host": {"type": "string"},
            "bridge_port": {"type": "integer"},
            "workdir": {"type": "string"},
        },
    },
}

AGENTDEX_LIST_SUBAGENTS_SCHEMA = {
    "name": "agentdex_list_subagents",
    "description": "List every registered sub-agent and CLI bridge with capabilities and stats.",
    "parameters": {
        "type": "object",
        "properties": {
            "capability": {
                "type": "string",
                "description": "optional filter — only return agents tagged with this capability",
            },
        },
    },
}


def handle_register_subagent(registry: AgentsRegistry, args: dict) -> dict:
    sub = SubAgent(
        name=args["name"],
        kind=args["kind"],
        description=args.get("description", ""),
        capabilities=args.get("capabilities") or [],
        base_url=args.get("base_url"),
        session_token=args.get("session_token"),
        bridge_host=args.get("bridge_host", "127.0.0.1"),
        bridge_port=args.get("bridge_port"),
        workdir=args.get("workdir"),
    )
    registry.upsert(sub)
    masked = sub.to_dict()
    if masked.get("session_token"):
        masked["session_token"] = "***"
    return {"ok": True, "agent": masked}


def handle_list_subagents(registry: AgentsRegistry, args: dict) -> dict:
    cap = args.get("capability")
    pool = registry.filter_by_capability([cap]) if cap else registry.list_all()
    out = []
    for a in pool:
        d = a.to_dict()
        if d.get("session_token"):
            d["session_token"] = "***"
        out.append(d)
    return {"agents": out}
