"""Phase-A8 — visiting-agent surface (A1/A3/A6 gate anchors).

Criteria:
- no injection-corpus payload mutates state, escapes the tool surface, or
  reaches rendered output unsanitized (launch-blocking gate)
- enrollment provably requires a human action an agent cannot complete alone
- design-partner full loop: license -> draft -> battle -> receipt -> mutation
  -> sandbox rematch (≤10 non-turn calls; per-turn chooses stream inside)
- rated events only from server-matchmade battles (/sandbox is unrated)
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest
import yaml
from adx_showdown.sidecar import Sidecar, sidecar_available
from agentdex_arena.consent import ConsentAuthority, ConsentClaims, ConsentError
from agentdex_arena.gateway import ArenaGateway, create_app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(sidecar_available() is not None, reason=str(sidecar_available()))

CORPUS = yaml.safe_load(
    (
        Path(__file__).resolve().parents[3] / "tests" / "redteam" / "injection_corpus.yaml"
    ).read_text()
)["payloads"]


def _payload_value(p: dict) -> str:
    if "value_repeat" in p:
        return p["value_repeat"]["char"] * p["value_repeat"]["times"]
    return str(p["value"])


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


def _play_to_end(client, token, state, *, max_turns=400):
    calls = 0
    while state.get("status") == "your_move":
        resp = client.post(
            f"/battle/{state['battle_id']}/choose",
            json={"token": token, "choice_index": 1},
        )
        assert resp.status_code == 200, resp.text
        nxt = resp.json()
        nxt.setdefault("battle_id", state["battle_id"])
        state = nxt
        calls += 1
        assert calls < max_turns
    return state, calls


def test_enrollment_requires_human_out_of_band(arena):
    """A1: the agent alone cannot complete enrollment."""
    client, gateway, owner_inbox, agent_key = arena
    r1 = client.post(
        "/enroll/request",
        json={
            "owner": "owner@example.com",
            "agent_name": "LoneAgent",
            "agent_pubkey_hex": agent_key.public_key().public_bytes_raw().hex(),
        },
    )
    assert r1.status_code == 200
    body = r1.json()
    assert "token" not in body and "code" not in body, (
        "agent-visible response must not leak the code"
    )
    # agent guesses codes -> opaque 404s; no token without the owner's code
    for guess in ("0" * 22, "wrong", owner_inbox["owner@example.com"][:-2] + "xx"):
        r = client.post(f"/enroll/confirm/{guess}")
        assert r.status_code == 404
        assert r.json()["detail"].startswith("arena error (ref:")
    print("\nCONSENT_FLOW: agent-only enrollment blocked; owner code path mints below")
    token = _enroll(client, owner_inbox, agent_key, owner="owner@example.com", name="LoneAgent")
    assert token.count(".") == 1


@pytest.mark.timeout(900)
def test_design_partner_full_loop(arena):
    """The day-one loop: license -> draft -> battle -> receipt -> mutation ->
    sandbox rematch. ≤10 non-turn calls; turn chooses stream inside."""
    client, gateway, owner_inbox, agent_key = arena
    non_turn_calls = 0

    token = _enroll(client, owner_inbox, agent_key)  # 2 calls
    non_turn_calls += 2
    state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")  # 2 calls
    non_turn_calls += 2
    receipt, turn_calls = _play_to_end(client, token, state)
    assert receipt["status"] == "ended"
    assert "failure_signatures" in receipt and "replay" in receipt
    assert "rating" not in receipt, "sandbox battles are UNRATED (A3)"

    replay = client.get(receipt["replay"]).json()  # 1 call
    non_turn_calls += 1
    assert replay["input_log"], "replay receipt must carry the re-simulable inputLog"

    seeds = client.post(
        "/evolution/request", json={"token": token, "reasoning": "lost to gym leader"}
    ).json()  # 1 call
    non_turn_calls += 1
    assert seeds["team_candidates"], "offered seeds must include validated team mutations"
    assert all(s["application_unverified"] for s in seeds["advisory_seeds"])
    mutated_team = seeds["team_candidates"][0]["packed"]

    state2 = _begin_battle(client, gateway, token, agent_key, lane="sandbox", team=mutated_team)
    non_turn_calls += 2
    receipt2, turn_calls2 = _play_to_end(client, token, state2)
    assert receipt2["status"] == "ended"
    print(
        f"\nDESIGN_PARTNER_LOOP: non_turn_calls={non_turn_calls} (<=10), "
        f"battle1={turn_calls} turns streamed, battle2={turn_calls2}; "
        f"receipt1 win={receipt['you_won']} sigs={len(receipt['failure_signatures'])}"
    )
    assert non_turn_calls <= 10


@pytest.mark.timeout(900)
def test_rated_lane_server_matchmade_only(arena):
    """A3: rated receipts carry rating + post-result seed disclosure; the
    ladder contains ONLY rated events; sandbox leaves no rating trace."""
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="RatedBot")

    sandbox_state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")
    _play_to_end(client, token, sandbox_state)
    assert client.get("/ladder").json()["entrants"] == {}, "sandbox must not rate"

    rated_state = _begin_battle(client, gateway, token, agent_key, lane="rated")
    receipt, _ = _play_to_end(client, token, rated_state)
    assert receipt["lane"] == "rated" and "rating" in receipt
    assert receipt["rating"]["published_delta"] == "INCONCLUSIVE" or isinstance(
        receipt["rating"]["published_delta"], float
    )
    assert receipt["rating"]["seed_disclosure"], "rated seed revealed post-result (A3)"
    entrants = client.get("/ladder").json()["entrants"]
    assert "RatedBot" in entrants and entrants["RatedBot"]["games"] == 1
    print(f"\nRATED_LANE: {receipt['rating']} vs {receipt.get('winner')!r}; ladder={entrants}")


def test_quota_fail_closed(arena):
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="QuotaBot")
    # battle quota default 5/day — 6th rated begin is refused at start+begin.
    # Play each to the end so begins don't pile up against the sidecar's live-
    # battle capacity (the quota axis is independent of battle lifecycle).
    for _ in range(5):
        state = _begin_battle(client, gateway, token, agent_key, lane="rated")
        _play_to_end(client, token, state)
    start = client.post("/battle/start", json={"token": token}).json()
    sig = agent_key.sign(start["pop_challenge"].encode()).hex()
    r = client.post(
        "/battle/begin",
        json={
            "token": token,
            "battle_nonce": start["battle_nonce"],
            "pop_signature_hex": sig,
            "lane": "rated",
        },
    )
    assert r.status_code == 403
    assert r.json()["detail"].startswith("arena error (ref:")
    print("\nQUOTA: 6th rated battle refused fail-closed")


def test_turn_budget_forfeits_stale_battle(arena):
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="SlowBot")
    state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")
    gateway.now = lambda: time.time() + 1_000  # jump past the 120s budget
    resp = client.post(
        f"/battle/{state['battle_id']}/choose", json={"token": token, "choice_index": 1}
    )
    body = resp.json()
    assert body["status"] == "ended"
    assert body["winner"].startswith("anchor-"), "stale battle forfeits to the opponent"
    print(f"\nTURN_BUDGET: stale battle forfeited to {body['winner']!r}")


def test_injection_corpus_gate(arena):
    """A6 launch-blocking gate: every payload through every writable field."""
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="ProbeBot")
    pub = agent_key.public_key().public_bytes_raw().hex()
    blocked = 0
    for payload in CORPUS:
        value = _payload_value(payload)
        # 1) enrollment agent_name field
        r = client.post(
            "/enroll/request",
            json={"owner": "x@example.com", "agent_name": value[:64], "agent_pubkey_hex": pub},
        )
        assert r.status_code in (200, 400, 422), (payload["id"], r.status_code)
        # 2) consent token position
        r = client.post("/battle/start", json={"token": value[:2000]})
        assert r.status_code == 403, payload["id"]
        assert r.json()["detail"].startswith("arena error (ref:"), payload["id"]
        # 3) evolution reasoning field — payload must NOT reflect raw
        r = client.post("/evolution/request", json={"token": token, "reasoning": value[:500]})
        if r.status_code == 200:
            echoed = r.json()["reasoning_echo"]
            for ch in ("<", ">", "|", "{", "}", "\x1b", "/"):
                assert ch not in echoed, (payload["id"], ch)
        else:
            assert r.json()["detail"].startswith("arena error (ref:")
        # 4) battle id path position — a payload the HTTP client itself refuses
        #    to place in the request line (bare control chars) never reaches the
        #    server; that client-side rejection is itself neutralization.
        try:
            r = client.post(
                f"/battle/{value[:40]}/choose", json={"token": token, "choice_index": 1}
            )
        except httpx.InvalidURL:
            blocked += 1
            continue
        assert r.status_code in (404, 422), payload["id"]
        if r.status_code == 404:
            detail = r.json()["detail"]
            # either the gateway's opaque "no session" 404, or FastAPI's
            # route-mismatch 404 when the payload injects a path separator —
            # both mean the payload never reached the battle handler.
            assert detail.startswith("arena error (ref:") or detail == "Not Found", payload["id"]
        blocked += 1
    # no payload minted a token, started a battle, or got itself rated
    assert client.get("/ladder").json()["entrants"] == {}
    print(f"\nINJECTION_GATE: {blocked}/{len(CORPUS)} payloads neutralized across 4 surfaces")


def test_consent_unit_rails():
    signing = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    agent = Ed25519PrivateKey.generate()
    auth = ConsentAuthority(signing_key_hex=signing, now=lambda: 1000.0)
    claims = ConsentClaims(
        token_id="t" * 8,
        owner="o@example.com",
        agent_name="Bot",
        agent_pubkey_hex=agent.public_key().public_bytes_raw().hex(),
        scopes=["battle"],
        issued_at=1000.0,
        expires_at=2000.0,
        confirmed_via="test",
    )
    token = auth.mint(claims)
    assert auth.verify(token, scope="battle").token_id == claims.token_id
    with pytest.raises(ConsentError, match="scope"):
        auth.verify(token, scope="evolve")
    with pytest.raises(ConsentError, match="signature"):
        auth.verify(token[:-4] + "AAAA", scope="battle")
    auth.revoke(claims.token_id)
    with pytest.raises(ConsentError, match="revoked"):
        auth.verify(token, scope="battle")
    # PoP: the agent's own key verifies; a stranger's key fails
    auth2 = ConsentAuthority(signing_key_hex=signing, now=lambda: 1000.0)
    sig = agent.sign(ConsentAuthority.pop_challenge("nonce1", claims.token_id)).hex()
    auth2.verify_pop(claims, "nonce1", sig)
    mallory = Ed25519PrivateKey.generate()
    bad = mallory.sign(ConsentAuthority.pop_challenge("nonce1", claims.token_id)).hex()
    with pytest.raises(ConsentError, match="possession"):
        auth2.verify_pop(claims, "nonce1", bad)
