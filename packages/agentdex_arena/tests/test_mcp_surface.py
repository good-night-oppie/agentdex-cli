"""Tests for packages/agentdex_arena/src/agentdex_arena/mcp_surface.py."""

from __future__ import annotations

from pathlib import Path

import pytest
from adx_showdown.sidecar import Sidecar, sidecar_available
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(sidecar_available() is not None, reason=str(sidecar_available()))


@pytest.fixture()
def arena(tmp_path: Path):
    signing_key = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    authority = ConsentAuthority(signing_key_hex=signing_key)
    owner_inbox: dict[str, str] = {}
    gateway = ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: owner_inbox.__setitem__(owner, code),
    )
    app = create_app(gateway, sidecar_factory=Sidecar)
    agent_key = Ed25519PrivateKey.generate()
    # Enter the TestClient as a context manager so ALL requests share one
    # persistent event loop (matching uvicorn). The persistent sidecar binds its
    # reader task + futures to that loop; the default per-request-loop TestClient
    # would strand the cached sidecar after the first battle request.
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, gateway, owner_inbox, agent_key


def _enroll(client, owner_inbox, agent_key, *, owner="eddie@oppie.xyz", name="PartnerBot"):
    r1 = client.post(
        "/enroll/request",
        json={
            "owner": owner,
            "agent_name": name,
            "agent_pubkey_hex": agent_key.public_key().public_bytes_raw().hex(),
        },
    )
    assert r1.status_code == 200
    assert "code" not in r1.text.lower() or "confirmation code sent" in r1.text
    code = owner_inbox[owner]  # OUT-OF-BAND: only the owner has this
    r2 = client.post(f"/enroll/confirm/{code}")
    assert r2.status_code == 200
    return r2.json()["token"]


def _begin_battle(client, gateway, token, agent_key, *, lane="sandbox", team=None):
    start = client.post("/battle/start", json={"token": token}).json()
    nonce = start["battle_nonce"]
    sig = agent_key.sign(start["pop_challenge"].encode()).hex()
    body = {"token": token, "battle_nonce": nonce, "pop_signature_hex": sig, "lane": lane}
    if team:
        body["team"] = team
    resp = client.post("/battle/begin", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _call_tool(client, name: str, **kwargs) -> dict:
    resp = client.post(
        "/mcp/",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": kwargs,
            },
            "id": 1,
        },
        headers={"Accept": "application/json"},
    )
    assert resp.status_code == 200, (
        f"Tool {name} HTTP status: {resp.status_code}, response: {resp.text}"
    )
    body = resp.json()
    if "error" in body:
        raise ValueError(body["error"]["message"])

    result = body.get("result", {})
    if result.get("isError"):
        text_content = result.get("content", [{}])[0].get("text", "Unknown tool error")
        raise ValueError(text_content)

    if "structuredContent" in result:
        return result["structuredContent"]

    return result


def test_mcp_surface_tools_e2e(arena):
    client, gateway, owner_inbox, agent_key = arena

    # 1. Enroll the agent
    token = _enroll(client, owner_inbox, agent_key, name="McpBot")

    # 2. Test request_evolution before playing
    evo = _call_tool(
        client, "request_evolution", token=token, team="", reasoning="testing mcp evolve"
    )
    assert "team_candidates" in evo
    assert len(evo["team_candidates"]) > 0
    assert "advisory_seeds" in evo

    # 3. Start a battle
    state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")
    battle_id = state["battle_id"]

    # 4. Read empty scratchpad
    sp = _call_tool(client, "read_scratchpad", token=token, battle_id=battle_id)
    assert sp["scratchpad"] == ""

    # 5. Write to scratchpad
    wsp = _call_tool(
        client, "write_scratchpad", token=token, battle_id=battle_id, text="my test strategy"
    )
    assert wsp["ok"] is True
    assert wsp["scratchpad"] == "my test strategy"

    # 6. Read scratchpad again
    sp = _call_tool(client, "read_scratchpad", token=token, battle_id=battle_id)
    assert sp["scratchpad"] == "my test strategy"

    # 7. Get battle state
    bs = _call_tool(client, "get_battle_state", token=token, battle_id=battle_id)
    assert bs["status"] == "your_move"
    assert "state" in bs
    assert "n_choices" in bs
    # Check that scratchpad is rendered in state
    assert "my test strategy" in bs["state"]

    # 8. Choose action
    res = _call_tool(client, "choose_action", token=token, battle_id=battle_id, choice_index=1)
    assert "status" in res

    # 9. Get my ladder history
    hist = _call_tool(client, "get_my_ladder_history", token=token)
    assert "events" in hist
    assert len(hist["events"]) > 0

    # 10. Play to end to test replay and Glicko delta
    while res.get("status") == "your_move":
        res = _call_tool(client, "choose_action", token=token, battle_id=battle_id, choice_index=1)

    assert res["status"] == "ended"

    # 11. Get battle replay
    rep = _call_tool(client, "get_battle_replay", battle_id=battle_id)
    assert "input_log" in rep
    assert len(rep["input_log"]) > 0

    # 12. Get evolution diff
    diff = _call_tool(client, "get_evolution_diff", token=token)
    assert diff["agent_name"] == "McpBot"
    assert "current_rating" in diff
    assert "rating_diff" in diff


def test_mcp_surface_mount(arena):
    client, gateway, owner_inbox, agent_key = arena
    # Check that the /mcp endpoint exists on the app
    routes = [r.path for r in client.app.routes if hasattr(r, "path")]
    assert any(p.startswith("/mcp") for p in routes)


def test_mcp_surface_opaque_errors(arena):
    client, gateway, owner_inbox, agent_key = arena
    # 1. Invalid token should raise ValueError with generic opaque error
    with pytest.raises(ValueError, match=r"arena error \(ref: [0-9a-f]+\)"):
        _call_tool(client, "get_battle_state", token="invalid-token", battle_id="some-id")


def test_mcp_surface_multi_instance_context(tmp_path: Path):
    # Create two gateways and two apps
    k1 = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    a1 = ConsentAuthority(signing_key_hex=k1)
    inbox1 = {}
    g1 = ArenaGateway(
        authority=a1,
        events_path=tmp_path / "events1.jsonl",
        artifacts_dir=tmp_path / "arena1",
        notify_owner=inbox1.__setitem__,
    )
    app1 = create_app(g1, sidecar_factory=Sidecar)

    k2 = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    a2 = ConsentAuthority(signing_key_hex=k2)
    inbox2 = {}
    g2 = ArenaGateway(
        authority=a2,
        events_path=tmp_path / "events2.jsonl",
        artifacts_dir=tmp_path / "arena2",
        notify_owner=inbox2.__setitem__,
    )
    app2 = create_app(g2, sidecar_factory=Sidecar)

    # They should not interfere because of ContextVar
    with TestClient(app1, raise_server_exceptions=False) as c1:
        with TestClient(app2, raise_server_exceptions=False) as c2:
            key1 = Ed25519PrivateKey.generate()
            t1 = _enroll(c1, inbox1, key1, name="Bot1")

            # Request to app2 using t1 should fail with opaque error since t1 is invalid for app2's authority
            with pytest.raises(ValueError, match=r"arena error \(ref: [0-9a-f]+\)"):
                _call_tool(c2, "get_my_ladder_history", token=t1)
