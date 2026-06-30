"""GA-ENROLL Step-5 invariant: per-owner agent-mint cap on POST /enroll/account.

/enroll/account is session-authed (a logged-in human mints a per-agent consent
token). Without a cap, one owner can POST unboundedly to mint unlimited agents
(200 each), squatting the global agent-name space and appending unbounded
`account_enroll` rows. The cap is a per-`_normalize_owner(claims.owner)` token
bucket: POST N+1 with the same bearer -> the (N+1)th returns 429.

KEYING (load-bearing): the cap keys on the VERIFIED OWNER, not the session token,
so it survives the 7-day session rotation (re-login is not a reset) and matches
the membership/quota single-owner-key discipline. Inert unless
ARENA_RATE_LIMIT_ENABLED (default-off path is byte-identical). The probe
`ga_enroll_ci_attest.sh` reports `enroll_account_rate_limit_429` as the gated name.
"""

from __future__ import annotations

from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

_PUBKEY = (
    "428e0c24a1a650dd33fe5948adf6634ff78da809d11912a4d27023d65f81c5f6"  # pragma: allowlist secret
)


def _gateway(tmp_path):
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


def _client(gw):
    return TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)


def _mint(client, tok, name):
    return client.post(
        "/enroll/account",
        json={"agent_name": name, "agent_pubkey_hex": _PUBKEY},
        headers={"Authorization": f"Bearer {tok}"},
    ).status_code


def test_enroll_account_rate_limited_per_owner(tmp_path, monkeypatch):
    # Token bucket of 3 -> the 4th mint by the SAME bearer is 429'd; the first three
    # (distinct names -> no 409) reach the mint and return 200.
    monkeypatch.setenv("ARENA_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("ARENA_ENROLL_ACCOUNT_MAX_TOKENS", "3")
    gw = _gateway(tmp_path)
    tok = gw.session_auth.mint_session("alice@x.com", "gh-alice")
    client = _client(gw)
    codes = [_mint(client, tok, f"agent{i}") for i in range(4)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


def test_enroll_account_not_rate_limited_when_disabled(tmp_path, monkeypatch):
    # Default-off posture: with the limiter disabled the mint path must NEVER 429 —
    # proves the new limiter is byte-identical to the pre-change behavior when off.
    monkeypatch.delenv("ARENA_RATE_LIMIT_ENABLED", raising=False)
    gw = _gateway(tmp_path)
    tok = gw.session_auth.mint_session("alice@x.com", "gh-alice")
    client = _client(gw)
    codes = {_mint(client, tok, f"agent{i}") for i in range(8)}
    assert codes == {200}


def test_enroll_account_rate_limit_isolated_per_owner(tmp_path, monkeypatch):
    # Alice draining her bucket must NOT 429 Bob: the cap keys on the verified owner,
    # so a noisy owner cannot deny enrollment to everyone else.
    monkeypatch.setenv("ARENA_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("ARENA_ENROLL_ACCOUNT_MAX_TOKENS", "2")
    gw = _gateway(tmp_path)
    alice = gw.session_auth.mint_session("alice@x.com", "gh-alice")
    bob = gw.session_auth.mint_session("bob@x.com", "gh-bob")
    client = _client(gw)
    assert [_mint(client, alice, f"a{i}") for i in range(3)] == [200, 200, 429]
    assert _mint(client, bob, "b0") == 200  # Bob's own bucket is untouched


def test_enroll_account_rate_limit_survives_session_rotation(tmp_path, monkeypatch):
    # The cap keys on the OWNER, not the bearer: a fresh session token for the SAME
    # owner shares the already-drained bucket — re-logging-in is not a cap reset.
    monkeypatch.setenv("ARENA_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("ARENA_ENROLL_ACCOUNT_MAX_TOKENS", "2")
    gw = _gateway(tmp_path)
    tok1 = gw.session_auth.mint_session("alice@x.com", "gh-alice")
    client = _client(gw)
    assert [_mint(client, tok1, f"a{i}") for i in range(3)] == [200, 200, 429]
    tok2 = gw.session_auth.mint_session("alice@x.com", "gh-alice")  # brand-new session
    assert _mint(client, tok2, "a-new") == 429  # same owner -> same drained bucket
