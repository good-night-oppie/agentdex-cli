"""Step-5 GA-ENROLL invariant: ARENA_INVITE_REQUIRED enforcement on every
enrollment surface (GA-CORE-1 beta gate). Lives in its OWN named module so
the north-star probe's ``ga_enroll_ci_attest.sh`` can flip
``arena_invite_required_gate`` from UNVERIFIED → ATTESTED when this file
appears in ``ga-enroll-invariants.yml``'s module list.

Gate contract (per gateway.py + invite.py):
  - Flag OFF (``ARENA_INVITE_REQUIRED`` unset): every enroll surface stays
    open; existing behaviour is unaffected (the optional-at-boot posture).
  - Flag ON: ``/enroll/account`` (session-authed) and ``/enroll/confirm``
    (OOB-authed) require the owner to hold a redeemed invite — without it
    they fail closed with an opaque ``403``.
  - The OOB ``/enroll/confirm`` accepts an ``invite_code`` carried in the
    original ``/enroll/request`` and redeems it after the OOB code proves
    ownership of the email — so a brand-new invited owner can enroll in
    one round-trip, never with a client-supplied owner key.
  - Re-enroll for an already-admitted owner is a no-op success: no second
    code is burned (mirrors membership: 100 invited HUMANS, not tokens).
  - ``/enroll/redeem-invite`` (the redemption surface itself) is NEVER
    blocked by the gate — that would be a deadlock.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from adx_showdown.sidecar import Sidecar
from agentdex_arena.admin_auth import AdminAuthority
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

_ADMIN_TOKEN = "operator-secret-token"  # pragma: allowlist secret
_ADMIN_HASH = hashlib.sha256(_ADMIN_TOKEN.encode()).hexdigest()
_PUBKEY = (
    "428e0c24a1a650dd33fe5948adf6634ff78da809d11912a4d27023d65f81c5f6"  # pragma: allowlist secret
)


def _gateway(tmp_path: Path):
    """Live gateway w/ session-auth + admin-auth + invite-store, the same
    constructor shape test_invite_flow uses (PR #362 hardening posture)."""
    sent: list[tuple[str, str]] = []
    gw = ArenaGateway(
        authority=ConsentAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        # Capture the OOB code so the test can confirm without a real email channel.
        notify_owner=lambda owner, code: sent.append((owner, code)),
        session_authority=SessionAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
        admin_authority=AdminAuthority(token_hash_hex=_ADMIN_HASH),
    )
    return gw, sent


def _client(gw):
    return TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)


def _sess(gw, owner="alice@x.com", gh="111"):
    return {"Authorization": f"Bearer {gw.session_auth.mint_session(owner, gh)}"}


def _admin():
    return {"X-Admin-Token": _ADMIN_TOKEN}


# ---- Flag OFF: open enroll (optional-at-boot posture) ----------------------


def test_gate_off_session_enroll_proceeds_without_invite(tmp_path, monkeypatch):
    """``/enroll/account`` is open when ``ARENA_INVITE_REQUIRED`` is unset."""
    # Hermetic: clear an inherited flag (e.g. a beta-gated probe shell exports
    # ARENA_INVITE_REQUIRED=1) so this proves the UNSET/default behavior (#585 review).
    monkeypatch.delenv("ARENA_INVITE_REQUIRED", raising=False)
    gw, _sent = _gateway(tmp_path)
    with _client(gw) as c:
        r = c.post(
            "/enroll/account",
            json={
                "agent_name": "garchomp",
                "agent_pubkey_hex": _PUBKEY,
                "agent_source": "openai/codex",
            },
            headers=_sess(gw),
        )
    assert r.status_code == 200, r.text


def test_gate_off_oob_confirm_proceeds_without_invite(tmp_path, monkeypatch):
    """``/enroll/confirm`` is open when ``ARENA_INVITE_REQUIRED`` is unset —
    the OOB code proves ownership of the email, no extra gate."""
    # Hermetic: clear an inherited ARENA_INVITE_REQUIRED so this proves the
    # unset/default path even under a beta-gated shell (#585 review).
    monkeypatch.delenv("ARENA_INVITE_REQUIRED", raising=False)
    gw, sent = _gateway(tmp_path)
    with _client(gw) as c:
        c.post(
            "/enroll/request",
            json={
                "owner": "bob@x.com",
                "agent_name": "ralts",
                "agent_pubkey_hex": _PUBKEY,
            },
        )
        oob = sent[-1][1]
        r = c.post(f"/enroll/confirm/{oob}")
    assert r.status_code == 200, r.text


# ---- Flag ON: surfaces fail closed without a redeemed invite ---------------


def test_gate_on_session_enroll_403_when_owner_not_admitted(tmp_path, monkeypatch):
    """Flag ON + owner has not redeemed an invite → opaque 403 (no leak of
    "no invite vs no agent vs already enrolled"). The session is otherwise
    valid; the only block is the beta gate."""
    monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
    gw, _sent = _gateway(tmp_path)
    with _client(gw) as c:
        r = c.post(
            "/enroll/account",
            json={
                "agent_name": "garchomp",
                "agent_pubkey_hex": _PUBKEY,
                "agent_source": "openai/codex",
            },
            headers=_sess(gw),
        )
    assert r.status_code == 403
    # Lock the no-enumeration invariant: the body must be the GENERIC opaque shape,
    # not "invite code is invalid" vs "an invitation code is required" (which would let a
    # regression leak the gate reason while this attestation still passes) (#585 review).
    assert r.json().get("detail", "").startswith("arena error (ref:"), r.text


def test_gate_on_session_enroll_succeeds_after_redeem(tmp_path, monkeypatch):
    """Flag ON + redeem an invite → the gate now passes; subsequent
    ``/enroll/account`` succeeds with the same session. Locks the
    redeem → admit → enroll sequence end-to-end."""
    monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
    gw, _sent = _gateway(tmp_path)
    with _client(gw) as c:
        code = c.post("/admin/mint-invites", json={"count": 1}, headers=_admin()).json()["codes"][0]
        assert (
            c.post(
                "/enroll/redeem-invite",
                json={"invite_code": code},
                headers=_sess(gw),
            ).status_code
            == 200
        )
        r = c.post(
            "/enroll/account",
            json={
                "agent_name": "garchomp",
                "agent_pubkey_hex": _PUBKEY,
                "agent_source": "openai/codex",
            },
            headers=_sess(gw),
        )
    assert r.status_code == 200, r.text


def test_gate_on_oob_confirm_403_when_no_invite_code_carried(tmp_path, monkeypatch):
    """Flag ON + OOB ``/enroll/request`` carries no ``invite_code`` → the
    later ``/enroll/confirm`` fails closed with opaque 403. Critically the
    pending enrollment is NOT consumed (so a caller who learns of the gate
    can re-confirm with a freshly-redeemed invite)."""
    monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
    gw, sent = _gateway(tmp_path)
    with _client(gw) as c:
        c.post(
            "/enroll/request",
            json={
                "owner": "bob@x.com",
                "agent_name": "ralts",
                "agent_pubkey_hex": _PUBKEY,
            },
        )
        oob = sent[-1][1]
        r = c.post(f"/enroll/confirm/{oob}")
    assert r.status_code == 403
    # No-enumeration: generic opaque body, not invite-specific text (#585 review).
    assert r.json().get("detail", "").startswith("arena error (ref:"), r.text
    # The pending code is preserved — invariant from the gateway docstring
    # ("Peek (not pop) first so a rejected confirm does not consume").
    assert oob in gw.pending_enrollments


def test_gate_on_oob_confirm_redeems_carried_invite_code(tmp_path, monkeypatch):
    """Flag ON + OOB ``/enroll/request`` carries a valid ``invite_code`` →
    the OOB confirm redeems it (the OOB code itself is the ownership proof
    for the email), no second session-side redeem required. The invite gets
    burned + the owner is now admitted."""
    monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
    gw, sent = _gateway(tmp_path)
    with _client(gw) as c:
        code = c.post("/admin/mint-invites", json={"count": 1}, headers=_admin()).json()["codes"][0]
        c.post(
            "/enroll/request",
            json={
                "owner": "bob@x.com",
                "agent_name": "ralts",
                "agent_pubkey_hex": _PUBKEY,
                "invite_code": code,
            },
        )
        # The carried code must NOT be redeemed by the UNAUTHENTICATED /enroll/request —
        # only the OOB /enroll/confirm (which proves control of bob@x.com) may burn it.
        # Without this, a regression that redeems on the request would pass because the
        # final admitted/burned state is identical (#585 review).
        assert not gw.invites.is_admitted("bob@x.com")
        assert gw.invites.redeemable(code) is True
        oob = sent[-1][1]
        r = c.post(f"/enroll/confirm/{oob}")
    assert r.status_code == 200, r.text
    assert gw.invites.is_admitted("bob@x.com")  # redeemed only now, after OOB proof
    assert gw.invites.redeemable(code) is False  # burned by the OOB confirm


# ---- Admitted-owner re-enroll: no second code burned -----------------------


def test_gate_on_re_enroll_does_not_burn_a_second_code(tmp_path, monkeypatch):
    """Flag ON + owner already admitted → re-running redeem-invite with a
    NEW unrelated code is a no-op success (the new code stays redeemable
    for another HUMAN). Survives the 7-day token rotation: a returning
    human re-enrolls without burning a beta seat."""
    monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
    gw, _sent = _gateway(tmp_path)
    with _client(gw) as c:
        codes = c.post("/admin/mint-invites", json={"count": 2}, headers=_admin()).json()["codes"]
        # Owner redeems codes[0] first.
        c.post(
            "/enroll/redeem-invite",
            json={"invite_code": codes[0]},
            headers=_sess(gw),
        )
        # Same owner "redeems" codes[1] in a later session — must NOT burn it.
        assert (
            c.post(
                "/enroll/redeem-invite",
                json={"invite_code": codes[1]},
                headers=_sess(gw),
            ).status_code
            == 200
        )
    assert gw.invites.redeemable(codes[0]) is False  # burned (first redeem)
    assert gw.invites.redeemable(codes[1]) is True  # NOT burned (no-op for admitted owner)


# ---- Redemption surface is never itself gated ------------------------------


def test_gate_on_redeem_invite_path_is_not_self_gated(tmp_path, monkeypatch):
    """Flag ON + un-invited owner POSTs ``/enroll/redeem-invite`` with a
    valid code → the redemption itself must succeed (gating the redemption
    path would make the beta gate a deadlock — no owner could ever become
    admitted). The gate enforces on the consumer surfaces, not on the
    primitive that grants admission."""
    monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
    gw, _sent = _gateway(tmp_path)
    with _client(gw) as c:
        code = c.post("/admin/mint-invites", json={"count": 1}, headers=_admin()).json()["codes"][0]
        r = c.post(
            "/enroll/redeem-invite",
            json={"invite_code": code},
            headers=_sess(gw),
        )
    assert r.status_code == 200, r.text
    assert gw.invites.is_admitted("alice@x.com")


def test_gate_on_unknown_code_redeem_is_opaque_403(tmp_path, monkeypatch):
    """Flag ON + un-invited owner POSTs ``/enroll/redeem-invite`` with an
    unknown code → opaque 403 (no "code does not exist" leak). The opaque
    posture mirrors ConsentError — never let a probing client distinguish
    unknown / used / wrong-owner."""
    monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
    gw, _sent = _gateway(tmp_path)
    with _client(gw) as c:
        r = c.post(
            "/enroll/redeem-invite",
            json={"invite_code": "never-minted-code"},
            headers=_sess(gw),
        )
    assert r.status_code == 403


@pytest.mark.parametrize("blank", [" ", "  ", "\t\n"])
def test_gate_on_blank_invite_code_redeem_is_opaque_403(tmp_path, monkeypatch, blank):
    """Flag ON + whitespace-only ``invite_code`` → opaque 403 (no 500). The
    pydantic ``min_length=1`` admits the whitespace string, then InviteStore
    hashing must NOT raise out as a 500 (PR #363 hardening). Locks the
    fail-closed shape of every gate path."""
    monkeypatch.setenv("ARENA_INVITE_REQUIRED", "1")
    gw, _sent = _gateway(tmp_path)
    with _client(gw) as c:
        r = c.post(
            "/enroll/redeem-invite",
            json={"invite_code": blank},
            headers=_sess(gw),
        )
    assert r.status_code == 403
