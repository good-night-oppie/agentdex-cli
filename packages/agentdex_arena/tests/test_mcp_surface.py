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


def test_mcp_choose_audit_write_failure_returns_opaque_error(arena):
    """PR #169 review #3423698025: when the audit append fails on the MCP
    choose_action path (disk full / perm error / etc.), the visiting agent
    MUST get the opaque ``arena error (ref: ...)`` shape — NOT the raw
    ``f"... {e!r}"`` that leaks filesystem paths and other exception detail.
    The HTTP /choose path already redacts; this pins parity for MCP."""
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="OpaqueMcpBot")
    state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")
    battle_id = state["battle_id"]

    original_append = gateway.events.append

    def boom(event_type, payload):
        if event_type == "battle":
            # Use an OSError carrying a path-shaped string to make the leak
            # visible: if redaction is missing the test fails with the path
            # appearing in the visitor-facing exception message.
            raise OSError("[Errno 28] No space left on device: '/tmp/leaky-path/events.jsonl'")
        return original_append(event_type, payload)

    gateway.events.append = boom  # type: ignore[method-assign]
    try:
        with pytest.raises(ValueError) as exc:
            _call_tool(client, "choose_action", token=token, battle_id=battle_id, choice_index=1)
    finally:
        gateway.events.append = original_append

    msg = str(exc.value)
    # The opaque ref shape is mandatory — and the leaky path / errno text
    # MUST be redacted to server-side logs.
    import re

    assert re.search(r"arena error \(ref: [0-9a-f]+\)", msg), (
        f"expected opaque arena-error shape, got: {msg!r}"
    )
    assert "/tmp/leaky-path" not in msg, f"filesystem path leaked: {msg!r}"
    assert "Errno 28" not in msg, f"errno detail leaked: {msg!r}"
    # And the audit-failure session-fatal posture from PR #169 is preserved:
    # the session is ended with the fail-closed reason but WITHOUT the leaky
    # exception detail in the publicly-visible reason string.
    session = gateway.sessions[battle_id]
    assert session.ended is not None
    assert "event log write failed" in session.ended.get("reason", "")
    assert "/tmp/leaky-path" not in session.ended.get("reason", "")
    assert "Errno 28" not in session.ended.get("reason", "")


def test_mcp_choose_advance_failure_after_step_fails_closed(arena):
    """PR #169 review #3423698020: when ``_advance()`` fails after the initial
    ``step`` succeeded (opponent-policy / sidecar error during opponent
    auto-advance), the audit row is already durable but ``session.pending``
    was cleared. Without fail-closed cleanup, get_battle_state / choose_action
    would only report 'No pending request' until turn-budget timeout. Mirror
    the audit-append fail-closed posture: end the battle + stop the sidecar
    + opaque visitor error."""
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="AdvanceFailBot")
    state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")
    battle_id = state["battle_id"]
    session = gateway.sessions[battle_id]

    original_advance = gateway._advance
    call_count = {"n": 0}

    async def boom_on_second_advance(*args, **kwargs):
        # The choose flow path is:
        #   - the initial step succeeds
        #   - audit row appends
        #   - gw._advance() is called to render the next request
        # Failing _advance HERE simulates the reviewer's scenario.
        call_count["n"] += 1
        raise RuntimeError("simulated opponent-policy crash mid-advance")

    gateway._advance = boom_on_second_advance  # type: ignore[method-assign]
    try:
        with pytest.raises(ValueError) as exc:
            _call_tool(client, "choose_action", token=token, battle_id=battle_id, choice_index=1)
    finally:
        gateway._advance = original_advance

    msg = str(exc.value)
    import re

    assert re.search(r"arena error \(ref: [0-9a-f]+\)", msg), (
        f"expected opaque arena-error shape, got: {msg!r}"
    )
    assert "opponent-policy crash" not in msg, f"exception detail leaked: {msg!r}"
    # Fail-closed: session is ended-fatal so a follow-up get_battle_state sees
    # the failure instead of reporting "No pending request" until timeout.
    assert session.ended is not None
    assert "battle advance failed" in session.ended.get("reason", "")
    # The audit row IS durable (the move executed); the fail-closed end-marker
    # is in-memory only — distinct from the (1) initial-step-fail (no audit row)
    # and (2) audit-fail (audit row missing) cases.
    types = [e["type"] for e in gateway.events.iter_events()]
    assert types.count("battle") == 1


def test_mcp_evolve_failure_does_not_spend_or_record(arena, monkeypatch):
    """PR #284 review 3435334329: an MCP request_evolution whose offer_seeds
    fails must NOT spend the evolve quota nor write a durable quota_spend row
    (Class B spend-after-success), so a restart cannot replay a failed request
    as a used slot and exhaust the caller's cap for work that produced nothing.
    """
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="EvoFailBot")

    async def _boom(*args, **kwargs):
        raise RuntimeError("seed generation blew up")

    monkeypatch.setattr("agentdex_arena.mcp_surface.offer_seeds", _boom)

    with pytest.raises(ValueError):
        _call_tool(client, "request_evolution", token=token, team="", reasoning="x")

    assert gateway.authority.quota_used == {}, "a failed evolve must not debit quota"
    assert not any(e.get("type") == "quota_spend" for e in gateway.events.iter_events()), (
        "a failed evolve must not durably record a quota_spend"
    )


def test_mcp_evolve_success_spends_and_records(arena):
    """The success path debits exactly one evolve slot AND durably records it,
    so the daily cap survives a restart (ADX-P2-004) — but only after seeds were
    actually produced."""
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="EvoOkBot")

    evo = _call_tool(client, "request_evolution", token=token, team="", reasoning="x")
    assert "team_candidates" in evo

    evolve_keys = [k for k in gateway.authority.quota_used if ":evolve:" in k]
    assert len(evolve_keys) == 1
    assert gateway.authority.quota_used[evolve_keys[0]] == 1
    quota_events = [e for e in gateway.events.iter_events() if e.get("type") == "quota_spend"]
    assert len(quota_events) == 1
    assert quota_events[0]["payload"]["key"] == evolve_keys[0]
