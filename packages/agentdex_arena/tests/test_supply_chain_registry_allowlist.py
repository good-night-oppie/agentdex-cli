"""GA-ENROLL Step-5 invariant: coding-agent source allowlist.

The self-serve enrollment UI may only mint an Arena consent token for the
three documented open-source coding-agent sources from SPEC §2:
``openai/codex``, ``opencode``, and ``ultraworkers/claw-code``. Anything else
must fail closed before a global agent name is reserved or an account_enroll
receipt is written.

Threat-model scope: the allowlist gates the SELF-SERVE lane
(``/enroll/account``, session-authed) only. The operator-mediated OOB lane
(``/enroll/request`` → ``/enroll/confirm``) deliberately carries no
``agent_source`` and no allowlist check: the operator who relays the OOB code
(or wires the owner channel) is the trust gate there, and that lane is the
curated batch-mint path for agents outside the self-serve list. The exemption
is pinned by ``test_oob_enroll_lane_is_exempt_from_source_allowlist`` so the
asymmetry stays intentional-and-tested; if SPEC §2 is later ratified to cover
every consent-mint site, gate the OOB lane and update that pin.
"""

from __future__ import annotations

from pathlib import Path

from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ALLOWED_AGENT_SOURCES, ArenaGateway, create_app
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

_OWNER = "eddie@oppie.xyz"
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


def _bearer(gw: ArenaGateway, owner: str = _OWNER) -> dict[str, str]:
    assert gw.session_auth is not None
    return {"Authorization": f"Bearer {gw.session_auth.mint_session(owner, _GH_ID)}"}


def _body(agent_name: str, agent_source: str | None = None) -> dict[str, str]:
    body = {"agent_name": agent_name, "agent_pubkey_hex": _PUBKEY}
    if agent_source is not None:
        body["agent_source"] = agent_source
    return body


def _account_enroll_events(gw: ArenaGateway) -> list[dict]:
    return [e for e in gw.events.iter_events() if e.get("type") == "account_enroll"]


def test_enroll_account_allows_exact_documented_agent_sources(tmp_path):
    assert ALLOWED_AGENT_SOURCES == ("openai/codex", "opencode", "ultraworkers/claw-code")
    gw = _gateway(tmp_path)

    with _client(gw) as c:
        for idx, source in enumerate(ALLOWED_AGENT_SOURCES):
            r = c.post(
                "/enroll/account",
                json=_body(f"oppie-{idx}", source),
                headers=_bearer(gw, owner=f"owner-{idx}@oppie.xyz"),
            )
            assert r.status_code == 200, r.text

    events = _account_enroll_events(gw)
    assert [e["payload"]["agent_source"] for e in events] == list(ALLOWED_AGENT_SOURCES)
    assert gw.accounts.agents_for("owner-0@oppie.xyz") == ["oppie-0"]


def test_enroll_account_missing_agent_source_fails_closed(tmp_path):
    """Omitting ``agent_source`` must NOT default into the allowlist: a
    defaulted value would let any legacy/malicious client bypass the
    supply-chain floor and stamp the account_enroll receipt as a source it
    never declared (#636 review 3518557570). Absence is a 422 before any
    name is reserved or a receipt is written."""

    gw = _gateway(tmp_path)

    with _client(gw) as c:
        r = c.post("/enroll/account", json=_body("legacy"), headers=_bearer(gw))

    assert r.status_code == 422, r.text
    assert "legacy" not in gw._registered
    assert gw.accounts.agents_for(_OWNER) == []
    assert _account_enroll_events(gw) == []


def test_enroll_account_rejects_non_allowlisted_agent_source_before_publish(tmp_path):
    gw = _gateway(tmp_path)

    with _client(gw) as c:
        r = c.post(
            "/enroll/account",
            json=_body("evil", "curl-piped-from-random-gist"),
            headers=_bearer(gw),
        )

    assert r.status_code == 403
    assert r.json().get("detail", "").startswith("arena error (ref:"), r.text
    assert "evil" not in gw._registered
    assert gw.accounts.agents_for(_OWNER) == []
    assert _account_enroll_events(gw) == []


def test_oob_enroll_lane_is_exempt_from_source_allowlist(tmp_path):
    """PINS the deliberate exemption described in the module docstring: the
    operator-mediated ``/enroll/request`` → ``/enroll/confirm`` lane mints
    without any ``agent_source`` and without an allowlist check — the operator
    relaying the OOB code is the trust gate on that lane. If this test starts
    failing because the OOB lane grew a source gate, that is a deliberate
    SPEC §2 ratification: update the module docstring and this pin together
    (and migrate the in-repo OOB clients: CLI arena_client + starter kit)."""

    sent: list[tuple[str, str]] = []
    gw = ArenaGateway(
        authority=ConsentAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        # capture the OOB code so the test can confirm without a real channel
        notify_owner=lambda owner, code: sent.append((owner, code)),
        session_authority=SessionAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
    )

    with _client(gw) as c:
        r = c.post(
            "/enroll/request",
            json={"owner": _OWNER, "agent_name": "oob-lane", "agent_pubkey_hex": _PUBKEY},
        )
        assert r.status_code == 200, r.text
        assert sent, "OOB code was not delivered to the owner channel"
        r = c.post(f"/enroll/confirm/{sent[-1][1]}")

    # Minted with no declared source, no allowlist involvement.
    assert r.status_code == 200, r.text
    assert r.json()["token"]
    assert "oob-lane" in gw._registered
    # The OOB lane's receipt is the bare register event — no agent_source key
    # (so an agent_source census over events under-counts OOB enrollments by
    # design; they are operator-vouched, not self-declared).
    register_events = [e for e in gw.events.iter_events() if e.get("type") == "register"]
    assert register_events, "OOB enroll wrote no register receipt"
    assert all("agent_source" not in e.get("payload", {}) for e in register_events)
    assert _account_enroll_events(gw) == []
