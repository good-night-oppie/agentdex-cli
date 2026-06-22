"""Integration tests for POST /enroll/account (ADR-0013 D3).

The account-authed enroll: a logged-in human mints a per-agent consent token
using the session token as proof (no email-OOB code). Covers the happy path
(consent token works, owner = verified email, account->agents join recorded +
durable), the LOAD-BEARING shared-validator invariant (account-enroll and
email-OOB enroll compete for the SAME global agent-name namespace), auth
failures (401/403), 503-when-unconfigured, reserved/duplicate/bad-pubkey
rejection, and that the email-OOB path still round-trips after the refactor."""

from __future__ import annotations

from pathlib import Path

from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, EnrollRequest, create_app
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

_OWNER = "eddie@oppie.xyz"
_GH_ID = "12345678"
_PUBKEY = "428e0c24a1a650dd33fe5948adf6634ff78da809d11912a4d27023d65f81c5f6"  # pragma: allowlist secret  # ed25519 PUBLIC key
_PUBKEY2 = "0" * 64


def _gateway(tmp_path: Path, *, with_session=True) -> ArenaGateway:
    authority = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
    )
    session = (
        SessionAuthority(signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex())
        if with_session
        else None
    )
    return ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
        session_authority=session,
    )


def _client(gw):
    return TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)


def _session_token(gw, owner=_OWNER, github_id=_GH_ID):
    return gw.session_auth.mint_session(owner, github_id)


def _bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---- happy path ----


def test_account_enroll_mints_working_consent_token(tmp_path):
    gw = _gateway(tmp_path)
    tok = _session_token(gw)
    with _client(gw) as c:
        r = c.post(
            "/enroll/account",
            json={"agent_name": "oppie", "agent_pubkey_hex": _PUBKEY},
            headers=_bearer(tok),
        )
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"token", "expires_at"}
    # the minted consent token verifies + carries the session's verified email
    claims = gw.authority.verify(body["token"], scope="battle")
    assert claims.owner == _OWNER
    assert claims.agent_name == "oppie"
    assert claims.agent_pubkey_hex == _PUBKEY


def test_account_enroll_records_account_to_agents_join_durably(tmp_path):
    gw = _gateway(tmp_path)
    tok = _session_token(gw)
    with _client(gw) as c:
        c.post(
            "/enroll/account",
            json={"agent_name": "oppie", "agent_pubkey_hex": _PUBKEY},
            headers=_bearer(tok),
        )
    assert gw.accounts.agents_for(_OWNER) == ["oppie"]
    # durable: a fresh gateway over the same log rehydrates the join + the name
    gw2 = _gateway(tmp_path)
    assert gw2.accounts.agents_for(_OWNER) == ["oppie"]
    assert "oppie" in gw2._registered  # the register event replayed too


# ---- the load-bearing shared-validator invariant ----


def test_account_enroll_name_blocks_email_oob_enroll(tmp_path):
    """Global agent-name uniqueness spans BOTH paths: a name claimed by account-
    enroll must be rejected by the email-OOB path (and the reverse) — else two
    owners collapse onto one ladder identity (D3 anti-impersonation)."""
    gw = _gateway(tmp_path)
    tok = _session_token(gw)
    with _client(gw) as c:
        first = c.post(
            "/enroll/account",
            json={"agent_name": "oppie", "agent_pubkey_hex": _PUBKEY},
            headers=_bearer(tok),
        )
        assert first.status_code == 200
        # email-OOB request for the SAME name is now a duplicate
        oob = c.post(
            "/enroll/request",
            json={"owner": "other@x.com", "agent_name": "oppie", "agent_pubkey_hex": _PUBKEY2},
        )
    assert oob.status_code == 409


def test_email_oob_name_blocks_account_enroll(tmp_path):
    gw = _gateway(tmp_path)
    tok = _session_token(gw)
    with _client(gw) as c:
        # claim via email-OOB (request + confirm) — need the code from the notifier
        codes = []
        gw.notify_owner = lambda owner, code: codes.append(code)
        req = c.post(
            "/enroll/request",
            json={"owner": "first@x.com", "agent_name": "scout", "agent_pubkey_hex": _PUBKEY2},
        )
        assert req.status_code == 200
        confirm = c.post(f"/enroll/confirm/{codes[0]}")
        assert confirm.status_code == 200
        # account-enroll for the SAME name is now a duplicate
        acct = c.post(
            "/enroll/account",
            json={"agent_name": "scout", "agent_pubkey_hex": _PUBKEY},
            headers=_bearer(tok),
        )
    assert acct.status_code == 409


def test_duplicate_account_enroll_same_name_409(tmp_path):
    gw = _gateway(tmp_path)
    tok = _session_token(gw)
    with _client(gw) as c:
        c.post(
            "/enroll/account",
            json={"agent_name": "oppie", "agent_pubkey_hex": _PUBKEY},
            headers=_bearer(tok),
        )
        again = c.post(
            "/enroll/account",
            json={"agent_name": "oppie", "agent_pubkey_hex": _PUBKEY},
            headers=_bearer(tok),
        )
    assert again.status_code == 409


# ---- auth failures ----


def test_missing_authorization_is_401(tmp_path):
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        r = c.post("/enroll/account", json={"agent_name": "oppie", "agent_pubkey_hex": _PUBKEY})
    assert r.status_code == 401


def test_bad_session_token_is_403(tmp_path):
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        r = c.post(
            "/enroll/account",
            json={"agent_name": "oppie", "agent_pubkey_hex": _PUBKEY},
            headers=_bearer("not.a.valid.token"),
        )
    assert r.status_code == 403


def test_503_when_session_auth_unconfigured(tmp_path):
    gw = _gateway(tmp_path, with_session=False)
    with _client(gw) as c:
        r = c.post(
            "/enroll/account",
            json={"agent_name": "oppie", "agent_pubkey_hex": _PUBKEY},
            headers=_bearer("whatever"),
        )
    assert r.status_code == 503


# ---- input validation ----


def test_bad_pubkey_is_422(tmp_path):
    gw = _gateway(tmp_path)
    tok = _session_token(gw)
    with _client(gw) as c:
        r = c.post(
            "/enroll/account",
            json={"agent_name": "oppie", "agent_pubkey_hex": "nothex"},
            headers=_bearer(tok),
        )
    assert r.status_code == 422
    # and no name was reserved by the rejected request
    assert "oppie" not in gw._registered


def test_reserved_name_is_400(tmp_path):
    gw = _gateway(tmp_path)
    tok = _session_token(gw)
    with _client(gw) as c:
        r = c.post(
            "/enroll/account",
            json={"agent_name": "visitor", "agent_pubkey_hex": _PUBKEY},
            headers=_bearer(tok),
        )
    assert r.status_code == 400


def test_owner_cannot_be_client_supplied(tmp_path):
    """The owner is the session's verified email; an `owner` field in the body is
    rejected (extra='forbid') so a client can never enroll under someone else."""
    gw = _gateway(tmp_path)
    tok = _session_token(gw)
    with _client(gw) as c:
        r = c.post(
            "/enroll/account",
            json={"agent_name": "oppie", "agent_pubkey_hex": _PUBKEY, "owner": "evil@x.com"},
            headers=_bearer(tok),
        )
    assert r.status_code == 422


# ---- refactor safety: email-OOB still round-trips ----


def test_email_oob_round_trip_unchanged(tmp_path):
    gw = _gateway(tmp_path)
    codes = []
    gw.notify_owner = lambda owner, code: codes.append(code)
    req = gw.enroll_request(
        EnrollRequest(owner="a@x.com", agent_name="legacybot", agent_pubkey_hex=_PUBKEY)
    )
    assert req["status"] == "pending_owner_confirmation"
    out = gw.enroll_confirm(codes[0])
    assert "token" in out and "expires_at" in out
    claims = gw.authority.verify(out["token"], scope="battle")
    assert claims.agent_name == "legacybot"
    assert claims.owner == "a@x.com"


# ---- ENROLL-P1-playtest-return-code: env-gated code return (default OFF) ----


def test_enroll_request_omits_code_by_default(tmp_path, monkeypatch):
    """A1 out-of-band invariant: /enroll/request NEVER echoes the code by default."""
    monkeypatch.delenv("ARENA_ENROLL_RETURN_CODE", raising=False)
    gw = _gateway(tmp_path)
    out = gw.enroll_request(
        EnrollRequest(owner="a@x.com", agent_name="defaultbot", agent_pubkey_hex=_PUBKEY)
    )
    assert out["status"] == "pending_owner_confirmation"
    assert "confirmation_code" not in out


def test_enroll_request_returns_code_when_playtest_flag_on(tmp_path, monkeypatch):
    """ARENA_ENROLL_RETURN_CODE=1 echoes a REAL pending code that confirms end-to-end."""
    monkeypatch.setenv("ARENA_ENROLL_RETURN_CODE", "1")
    gw = _gateway(tmp_path)
    out = gw.enroll_request(
        EnrollRequest(owner="a@x.com", agent_name="playtestbot", agent_pubkey_hex=_PUBKEY)
    )
    assert out["status"] == "pending_owner_confirmation"
    code = out.get("confirmation_code")
    assert isinstance(code, str) and code
    confirmed = gw.enroll_confirm(code)
    assert "token" in confirmed
    claims = gw.authority.verify(confirmed["token"], scope="battle")
    assert claims.agent_name == "playtestbot"
    assert claims.owner == "a@x.com"
