"""Agentdex dashboard backend — auto-mounted at /api/plugins/agentdex/.

Hermes dashboard scans plugins/<name>/dashboard/plugin_api.py for a
module-level `router = APIRouter()` and includes it. Auth middleware
(session bearer or cookie) gates every request.
"""

from __future__ import annotations

import logging
import uuid

from agentdex_cli.registry.registry import AgentsRegistry, SubAgent, load_default_registry
from fastapi import APIRouter, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)
router = APIRouter()

_registry: AgentsRegistry = load_default_registry()


class SubAgentIn(BaseModel):
    name: str
    kind: str = Field(..., description="hermes-agent | cli")
    base_url: str | None = None
    bridge_port: int | None = None
    session_token: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    description: str = ""


class RouteIn(BaseModel):
    target: str
    prompt: str
    session_id: str | None = None
    extra: dict = Field(default_factory=dict)


@router.get("/agents")
async def list_agents() -> dict:
    return {"agents": [a.to_dict() for a in _registry.list_all()]}


@router.post("/agents", status_code=http_status.HTTP_201_CREATED)
async def register_agent(payload: SubAgentIn) -> dict:
    sub = SubAgent(**payload.model_dump())
    _registry.upsert(sub)
    return sub.to_dict()


@router.delete("/agents/{name}")
async def remove_agent(name: str) -> dict:
    if not _registry.remove(name):
        raise HTTPException(status_code=404, detail=f"agent {name!r} not found")
    return {"removed": name}


@router.post("/route")
async def route(req: RouteIn) -> dict:
    target = _registry.get(req.target)
    if not target:
        raise HTTPException(status_code=404, detail=f"target {req.target!r} not registered")
    try:
        if target.kind == "cli":
            from agentdex_cli.tools.route_to_subagent import _call_cli_bridge

            return await _call_cli_bridge(target, req.prompt, req.session_id, req.extra)
        from agentdex_cli.tools.route_to_subagent import _call_hermes_agent

        return await _call_hermes_agent(target, req.prompt, req.session_id, req.extra)
    except Exception as e:
        # IDEAL_EXPERIENCE §Arena A6: never leak exception internals (tracebacks,
        # repr, upstream payloads) to HTTP clients. Opaque ref id only; details
        # stay server-side in the log line below.
        err_id = uuid.uuid4().hex[:12]
        log.exception("route fail (ref=%s)", err_id)
        raise HTTPException(status_code=502, detail=f"upstream error (ref: {err_id})") from e


@router.get("/health")
async def health() -> dict:
    return {"ok": True, "count": len(_registry.list_all())}
