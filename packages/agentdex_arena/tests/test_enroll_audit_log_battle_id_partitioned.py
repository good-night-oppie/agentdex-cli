"""GA-ENROLL Step-5 invariant: audit rows are owner-partitioned.

Account enrollment appends durable audit rows. A user's `/my/events` pull must
return their own account enrollment receipt without leaking another owner's
receipt from the same event log.
"""

from __future__ import annotations

from pathlib import Path

from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

_GH_ID = "12345678"
_PUBKEY = "428e0c24a1a650dd33fe5948adf6634ff78da809d11912a4d27023d65f81c5f6"  # pragma: allowlist secret  # ed25519 PUBLIC key


def _gateway(tmp_path: Path) -> ArenaGateway:
    return ArenaGateway(
        authority=ConsentAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
        session_authority=SessionAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
    )


def _client(gw: ArenaGateway) -> TestClient:
    return TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)


def _bearer(gw: ArenaGateway, owner: str) -> dict[str, str]:
    assert gw.session_auth is not None
    return {"Authorization": f"Bearer {gw.session_auth.mint_session(owner, _GH_ID)}"}


def _enroll_account(c: TestClient, gw: ArenaGateway, *, owner: str, agent_name: str) -> str:
    r = c.post(
        "/enroll/account",
        json={"agent_name": agent_name, "agent_pubkey_hex": _PUBKEY},
        headers=_bearer(gw, owner),
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_account_enroll_audit_receipt_is_owner_partitioned(tmp_path: Path):
    gw = _gateway(tmp_path)

    with _client(gw) as c:
        alice_token = _enroll_account(c, gw, owner="alice@oppie.xyz", agent_name="AliceBot")
        _ = _enroll_account(c, gw, owner="bob@oppie.xyz", agent_name="BobBot")

        alice_claims = gw.authority.verify(alice_token, scope="battle")
        r = c.post("/my/events", json={"token": alice_token, "since_seq": -1})

    assert r.status_code == 200, r.text
    account_rows = [e for e in r.json()["events"] if e["type"] == "account_enroll"]
    assert len(account_rows) == 1
    payload = account_rows[0]["payload"]
    assert payload["tenant_id"] == alice_claims.token_id
    assert payload["owner"] == "alice@oppie.xyz"
    assert payload["agent_name"] == "AliceBot"
    assert payload["agent_source"] == "openai/codex"
    assert all(e["payload"].get("agent_name") != "BobBot" for e in r.json()["events"])
