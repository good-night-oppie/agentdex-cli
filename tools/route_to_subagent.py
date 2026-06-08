"""Tool: route a prompt to a registered sub-agent (Hermes HTTP) or CLI bridge (TCP JSON-RPC).

Records latency + success into the registry so the main agent learns which
target excels at which capability over time.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

import urllib.request

from registry.registry import AgentsRegistry, SubAgent

log = logging.getLogger(__name__)


AGENTDEX_ROUTE_TO_SUBAGENT_SCHEMA = {
    "name": "agentdex_route_to_subagent",
    "description": (
        "Send a prompt to a registered Hermes sub-agent via its dashboard HTTP API "
        "(OpenAI-compatible /v1/chat/completions). Returns the assistant text and "
        "a session_id you can pass back for multi-turn continuity."
    ),
    "parameters": {
        "type": "object",
        "required": ["target", "prompt"],
        "properties": {
            "target":     {"type": "string", "description": "registered agent name"},
            "prompt":     {"type": "string"},
            "session_id": {"type": "string"},
            "extra":      {"type": "object"},
        },
    },
}

AGENTDEX_ROUTE_TO_CLI_SCHEMA = {
    "name": "agentdex_route_to_cli",
    "description": (
        "Send a prompt to a long-lived CLI bridge (claude/codex/gemini) via its TCP "
        "JSON-RPC port. Bridge handles session continuity natively."
    ),
    "parameters": {
        "type": "object",
        "required": ["target", "prompt"],
        "properties": {
            "target":     {"type": "string"},
            "prompt":     {"type": "string"},
            "session_id": {"type": "string"},
            "extra":      {"type": "object"},
        },
    },
}


# ---------------------------------------------------------------------------
# HTTP call to a Hermes sub-agent's dashboard /v1/chat/completions
# ---------------------------------------------------------------------------

async def _call_hermes_agent(agent: SubAgent, prompt: str,
                             session_id: Optional[str], extra: dict) -> dict:
    """Hit the target Hermes' OpenAI-compatible gateway API server.

    Endpoint: gateway/platforms/api_server.py:4121 → POST /v1/chat/completions
    Session continuity headers (api_server.py:1739-1748):
      X-Hermes-Session-Id  — continue an existing session/transcript
      X-Hermes-Session-Key — scope long-term memory (e.g. Honcho) per channel
    """
    if not agent.base_url or not agent.session_token:
        raise ValueError(f"agent {agent.name!r} missing base_url or session_token")
    url = agent.base_url.rstrip("/") + "/v1/chat/completions"
    body = {
        "model": extra.get("model", "hermes"),
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {agent.session_token}",
    }
    if session_id:
        headers["X-Hermes-Session-Id"] = session_id
    if (session_key := extra.get("session_key")):
        headers["X-Hermes-Session-Key"] = session_key

    def _do_post() -> dict:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=extra.get("timeout_sec", 300)) as resp:
            return json.loads(resp.read()), resp.headers.get("X-Hermes-Session-Id")

    raw, next_sid = await asyncio.to_thread(_do_post)
    choice = (raw.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or ""
    return {
        "ok": True,
        "text": text,
        "session_id": next_sid or session_id,
        "raw": raw,
    }


# ---------------------------------------------------------------------------
# TCP JSON-RPC call to a CLI bridge (matches bridges/base.py protocol)
# ---------------------------------------------------------------------------

async def _call_cli_bridge(agent: SubAgent, prompt: str,
                           session_id: Optional[str], extra: dict) -> dict:
    if not agent.bridge_port:
        raise ValueError(f"agent {agent.name!r} missing bridge_port")
    reader, writer = await asyncio.open_connection(agent.bridge_host, agent.bridge_port)
    try:
        req = {
            "id": int(time.time() * 1000) & 0x7fffffff,
            "method": "chat",
            "params": {"prompt": prompt, "session_id": session_id, "extra": extra},
        }
        writer.write((json.dumps(req) + "\n").encode())
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=extra.get("timeout_sec", 300))
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
    if not line:
        raise ConnectionError(f"empty response from bridge {agent.bridge_port}")
    resp = json.loads(line)
    if "error" in resp:
        raise RuntimeError(f"bridge error: {resp['error']}")
    return resp.get("result") or {}


# ---------------------------------------------------------------------------
# Hermes tool entry points (sync-friendly wrappers)
# ---------------------------------------------------------------------------

def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    return loop.run_until_complete(coro)


def handle_route_to_subagent(registry: AgentsRegistry, args: dict) -> dict:
    target = registry.get(args["target"])
    if not target:
        return {"ok": False, "error": f"unknown target {args['target']!r}"}
    if target.kind != "hermes-agent":
        return {"ok": False, "error": f"target {target.name!r} kind={target.kind}; use agentdex_route_to_cli"}
    t0 = time.time()
    ok = False
    try:
        result = _run_async(_call_hermes_agent(target, args["prompt"], args.get("session_id"), args.get("extra") or {}))
        ok = bool(result.get("ok"))
        return result
    finally:
        registry.record_call(target.name, latency_ms=(time.time() - t0) * 1000.0, ok=ok)


def handle_route_to_cli(registry: AgentsRegistry, args: dict) -> dict:
    target = registry.get(args["target"])
    if not target:
        return {"ok": False, "error": f"unknown target {args['target']!r}"}
    if target.kind != "cli":
        return {"ok": False, "error": f"target {target.name!r} kind={target.kind}; use agentdex_route_to_subagent"}
    t0 = time.time()
    ok = False
    try:
        result = _run_async(_call_cli_bridge(target, args["prompt"], args.get("session_id"), args.get("extra") or {}))
        ok = bool(result.get("ok"))
        return {"ok": True, **result}
    finally:
        registry.record_call(target.name, latency_ms=(time.time() - t0) * 1000.0, ok=ok)
