"""GA-ENROLL Step-5 invariant: the unauthenticated ``/enroll/request`` surface.

``/enroll/request`` is the email-OOB enrollment entrypoint: it takes NO session
token, mints a one-time confirmation code, and fans out an out-of-band
``notify_owner`` (an email send in production). Two invariants protect it, both
asserted here behaviorally (the probe ``ga_enroll_ci_attest.sh`` reports
``enroll_request_invariants`` as the gated name):

  1. RATE-LIMIT — it sits behind the SAME per-IP volumetric guard as the other
     unauthenticated flood surfaces (``/auth/device/*``, ``/auth/email/start``),
     so an unauthenticated flood cannot drive unbounded code-generation +
     outbound-email cost. Inert unless ``ARENA_RATE_LIMIT_ENABLED`` (mirrors the
     auth surface; see test_ga_auth_rate_limit.py).

  2. AUDIT-LOG EMIT — every accepted request appends a durable ``enroll_request``
     event (owner + agent_name + an ``invited`` bool) for operator reconciliation
     of the OOB funnel. The confirmation ``code`` is a bearer secret and is NEVER
     written to the log — exactly like invite codes are hashed-only
     (test_invite_codes_are_hashed_in_event_log).
"""

from __future__ import annotations

import json

from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

# A syntactically valid agent_pubkey_hex (64 lowercase hex); the value is never
# checked against a real keypair on the request path.
_PUBKEY = (
    "428e0c24a1a650dd33fe5948adf6634ff78da809d11912a4d27023d65f81c5f6"  # pragma: allowlist secret
)


def _gw(tmp_path):
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


def _body(owner="alice@x.com", agent_name="garchomp", invite_code=None):
    b = {"owner": owner, "agent_name": agent_name, "agent_pubkey_hex": _PUBKEY}
    if invite_code is not None:
        b["invite_code"] = invite_code
    return b


def _events(tmp_path):
    path = tmp_path / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---- invariant 1: rate-limit on the unauthenticated flood surface ----


def test_enroll_request_is_rate_limited(tmp_path, monkeypatch):
    # Per-IP volumetric bucket of 2 → the 3rd unauthenticated /enroll/request from
    # the same IP is 429'd by the pre-parse middleware, capping the OOB-code +
    # email-send fanout. The first two reach the handler (200, pending).
    monkeypatch.setenv("ARENA_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("ARENA_AUTH_IP_MAX_TOKENS", "2")
    client = _client(_gw(tmp_path))
    codes = [
        client.post("/enroll/request", json=_body(agent_name=f"a{i}")).status_code for i in range(3)
    ]
    assert codes[:2] == [200, 200]
    assert codes[2] == 429


def test_enroll_request_not_rate_limited_when_disabled(tmp_path, monkeypatch):
    # Default-off posture: with the limiter disabled the newly-guarded path must
    # NEVER 429 — proves adding /enroll/request to the guard map did not make it
    # fire when rate-limiting is off (byte-identical to the pre-change behavior).
    monkeypatch.delenv("ARENA_RATE_LIMIT_ENABLED", raising=False)
    client = _client(_gw(tmp_path))
    codes = {
        client.post("/enroll/request", json=_body(agent_name=f"a{i}")).status_code for i in range(8)
    }
    assert codes == {200}


# ---- invariant 2: audit-log emit (without leaking the OOB secret) ----


def test_enroll_request_emits_audit_event(tmp_path):
    client = _client(_gw(tmp_path))
    r = client.post("/enroll/request", json=_body(owner="alice@x.com", agent_name="garchomp"))
    assert r.status_code == 200
    matched = [
        e
        for e in _events(tmp_path)
        if e["type"] == "enroll_request"
        and e["payload"]["owner"] == "alice@x.com"
        and e["payload"]["agent_name"] == "garchomp"
    ]
    assert len(matched) == 1
    assert matched[0]["payload"]["invited"] is False


def test_enroll_request_audit_records_invite_flag_not_the_code(tmp_path):
    # An invite-mode request records invited=True — but the invite_code VALUE
    # (a claimable beta seat) never lands in the durable log.
    client = _client(_gw(tmp_path))
    secret_invite = "beta-seat-9f3a2c"  # pragma: allowlist secret
    r = client.post(
        "/enroll/request",
        json=_body(owner="bob@x.com", agent_name="lucario", invite_code=secret_invite),
    )
    assert r.status_code == 200
    matched = [e for e in _events(tmp_path) if e["type"] == "enroll_request"]
    assert len(matched) == 1 and matched[0]["payload"]["invited"] is True
    raw = (tmp_path / "events.jsonl").read_text()
    assert secret_invite not in raw  # the invite code is a bearer secret


def test_enroll_request_audit_never_logs_the_oob_confirmation_code(tmp_path, monkeypatch):
    # The OOB confirmation code is a bearer secret (holding it lets you confirm the
    # enrollment). Capture it via the playtest echo and prove it is NOT in the log.
    monkeypatch.setenv("ARENA_ENROLL_RETURN_CODE", "1")
    client = _client(_gw(tmp_path))
    r = client.post("/enroll/request", json=_body(owner="carol@x.com", agent_name="zapdos"))
    assert r.status_code == 200
    code = r.json()["confirmation_code"]
    raw = (tmp_path / "events.jsonl").read_text()
    assert code not in raw  # the OOB confirmation code never lands in the durable log
