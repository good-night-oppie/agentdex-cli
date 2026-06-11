"""Phase-A2 — dashboard /route returns opaque error ids, never exception internals.

IDEAL_EXPERIENCE §Arena A6: visitor-facing errors are opaque ids; details are
logged server-side only. The fixture exception carries a sentinel secret that
must NOT appear in any HTTP-visible field.

Also covers the dashboard import-rot fix (flat `registry.registry` /
`tools.route_to_subagent` → `agentdex_cli.*`), which previously made this
module unimportable outside a Hermes plugin dir.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

SENTINEL = "secret-token-do-not-leak-9f2c"


def _api(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))  # registry file lands in tmp
    from agentdex_plugin.dashboard import plugin_api

    return plugin_api


def test_module_importable_and_routes_mounted(monkeypatch, tmp_path):
    api = _api(monkeypatch, tmp_path)
    paths = {r.path for r in api.router.routes}
    assert {"/agents", "/route", "/health"} <= paths


def test_route_failure_returns_opaque_ref_not_internals(monkeypatch, tmp_path):
    api = _api(monkeypatch, tmp_path)

    class _Target:
        kind = "cli"
        name = "boom"

    class _Registry:
        def get(self, name):
            return _Target()

    async def _boom(*a, **k):
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(api, "_registry", _Registry())
    import agentdex_cli.tools.route_to_subagent as rts

    monkeypatch.setattr(rts, "_call_cli_bridge", _boom)

    req = api.RouteIn(target="boom", prompt="hi")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(api.route(req))

    exc = exc_info.value
    assert exc.status_code == 502
    detail = str(exc.detail)
    assert SENTINEL not in detail, "exception internals leaked to HTTP client"
    assert "RuntimeError" not in detail
    assert detail.startswith("upstream error (ref: ")
    ref = detail.split("ref: ")[1].rstrip(")")
    assert len(ref) == 12 and all(c in "0123456789abcdef" for c in ref)


def test_route_unknown_target_is_404_without_internals(monkeypatch, tmp_path):
    api = _api(monkeypatch, tmp_path)

    class _Registry:
        def get(self, name):
            return None

    monkeypatch.setattr(api, "_registry", _Registry())
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(api.route(api.RouteIn(target="ghost", prompt="hi")))
    assert exc_info.value.status_code == 404
